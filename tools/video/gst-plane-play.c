/*
 * gst-plane-play: play a file straight onto the video plane with stock
 * GStreamer (decoder ! kmssink), GPU idle. RUNS ON THE TARGET.
 *
 * WP4 of docs/gpu-fallback-plan.md; tools/video/h713-play decides when to use
 * it. Two routes, both zero-copy into the AFBD video plane, which takes one
 * framebuffer geometry: exactly the panel's 1280x720.
 *
 *   native   content that is already 1280x720, any codec, through the stock
 *            v4l2sl*dec. Nothing here but the plumbing.
 *   scaled   H.264/HEVC larger than the panel, through va*dec and the VE
 *            decode-time scaler. The VA driver (patches/libva-v4l2_request
 *            0005 + 0007) scales while decoding when V4L2_REQUEST_SCALE=WxH
 *            is set and exports surfaces at that size, but GStreamer cannot
 *            know: its caps come from the SPS, and the va decoder stamps every
 *            buffer's GstVideoMeta with the coded picture size. kmssink takes
 *            the framebuffer width from that meta, so a 1280-pitch buffer
 *            described as 1920 wide fails AddFB2 ("bad pitch"). No stock
 *            element rewrites a video meta, so a pad probe after the decoder
 *            makes the CAPS event and each buffer's meta say what the buffer
 *            really holds. The caller sets V4L2_REQUEST_SCALE and
 *            V4L2_REQUEST_CROP and passes the same size here.
 *
 * Audio, when the file has any, goes to PipeWire through its ALSA plugin
 * (alsasink device=pipewire; packages gstreamer1.0-alsa and pipewire-alsa).
 * The pipeline runs on the system clock and the audio sink follows it.
 *
 *   usage: gst-plane-play FILE CODEC DECODER [WxH] [SECONDS]
 *          CODEC   h264 | h265 | vp9 | av1
 *          DECODER the GStreamer element, e.g. v4l2slvp9dec or vah264dec
 *          WxH     the scaled size; omit (or "-") for native content
 *          SECONDS stop after this long (for measurements)
 *
 * Prints the sink's rendered and dropped counts and the stream position at
 * the end; exits 1 on a pipeline error.
 *
 * Build on the board:
 *   gcc -O2 -Wall -o /usr/local/bin/gst-plane-play gst-plane-play.c \
 *       $(pkg-config --cflags --libs gstreamer-1.0 gstreamer-video-1.0)
 */
#include <glib-unix.h>
#include <gst/gst.h>
#include <gst/video/video.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static gint out_w, out_h;

struct player {
	GstElement *pipeline;
	GMainLoop *loop;
	const char *codec;
	const char *decoder;
	gboolean scaled;
	gboolean have_video, have_audio;
	int status;
};

static GstPadProbeReturn fix_geometry(GstPad *pad, GstPadProbeInfo *info,
				      gpointer data)
{
	(void)pad;
	(void)data;

	if (info->type & GST_PAD_PROBE_TYPE_EVENT_DOWNSTREAM) {
		GstEvent *event = GST_PAD_PROBE_INFO_EVENT(info);
		GstCaps *caps;

		if (GST_EVENT_TYPE(event) != GST_EVENT_CAPS)
			return GST_PAD_PROBE_OK;

		gst_event_parse_caps(event, &caps);
		caps = gst_caps_copy(caps);
		/* The scaled size is already aspect-fit by the caller, so the
		 * pixels are square whatever the stream's SAR was. */
		gst_caps_set_simple(caps, "width", G_TYPE_INT, out_w,
				    "height", G_TYPE_INT, out_h,
				    "pixel-aspect-ratio", GST_TYPE_FRACTION, 1, 1,
				    NULL);
		gst_event_unref(event);
		GST_PAD_PROBE_INFO_DATA(info) = gst_event_new_caps(caps);
		gst_caps_unref(caps);
		return GST_PAD_PROBE_OK;
	}

	if (info->type & GST_PAD_PROBE_TYPE_BUFFER) {
		GstVideoMeta *meta =
			gst_buffer_get_video_meta(GST_PAD_PROBE_INFO_BUFFER(info));

		/* Stride and offsets came from the driver's export descriptor
		 * and are already right; only the size is the SPS's. Rewritten
		 * in place: the buffer is a pooled VA surface, which the
		 * decoder stamps again before its next use. */
		if (meta) {
			meta->width = out_w;
			meta->height = out_h;
		}
	}

	return GST_PAD_PROBE_OK;
}

/* Build "description" into a bin with a ghost sink pad, add it to the
 * pipeline, link @pad to it and start it. */
static gboolean attach(struct player *p, GstPad *pad, const char *description)
{
	GError *error = NULL;
	GstElement *bin;
	GstPadLinkReturn ret;
	GstPad *sink;

	bin = gst_parse_bin_from_description(description, TRUE, &error);
	if (!bin) {
		fprintf(stderr, "gst-plane-play: %s: %s\n", description,
			error->message);
		g_clear_error(&error);
		return FALSE;
	}

	/* Started before it is linked: unopened, kmssink and the decoders
	 * answer caps queries with nothing in common with the stream. */
	gst_bin_add(GST_BIN(p->pipeline), bin);
	gst_element_sync_state_with_parent(bin);
	sink = gst_element_get_static_pad(bin, "sink");
	ret = gst_pad_link(pad, sink);
	gst_object_unref(sink);
	if (ret != GST_PAD_LINK_OK) {
		fprintf(stderr, "gst-plane-play: cannot link %s: %s\n",
			description, gst_pad_link_get_name(ret));
		return FALSE;
	}

	if (p->scaled && strstr(description, "name=fix")) {
		GstElement *fix = gst_bin_get_by_name(GST_BIN(bin), "fix");
		GstPad *src = gst_element_get_static_pad(fix, "src");

		gst_pad_add_probe(src, GST_PAD_PROBE_TYPE_BUFFER |
				  GST_PAD_PROBE_TYPE_EVENT_DOWNSTREAM,
				  fix_geometry, NULL, NULL);
		gst_object_unref(src);
		gst_object_unref(fix);
	}

	return TRUE;
}

static void on_pad_added(GstElement *decodebin, GstPad *pad, gpointer data)
{
	struct player *p = data;
	GstCaps *caps = gst_pad_get_current_caps(pad);
	const char *name;
	gchar *description;

	(void)decodebin;

	if (!caps)
		caps = gst_pad_query_caps(pad, NULL);
	name = gst_structure_get_name(gst_caps_get_structure(caps, 0));

	if (g_str_has_prefix(name, "video/") && !p->have_video) {
		/* Pinned to DMABuf NV12 so the decoder exports its surfaces and
		 * kmssink imports them; never a copy. skip-vsync: the plane
		 * commit already waits for the flip, and kmssink's own vblank
		 * wait on top of it made each render last up to a whole 30 fps
		 * frame; lateness built until the decoder's QoS dropped about
		 * one frame a second (30 in 30 s; 0 with it, 2026-10-03). */
		description = g_strdup_printf(
			"%sparse ! %s ! "
			"video/x-raw(memory:DMABuf),format=DMA_DRM,drm-format=NV12 ! "
			"identity name=fix ! "
			"kmssink name=vsink driver-name=sun50i-h713-afbd "
			"skip-vsync=true",
			p->codec, p->decoder);
		p->have_video = attach(p, pad, description);
		g_free(description);
	} else if (g_str_has_prefix(name, "audio/") && !p->have_audio) {
		/* alsasink through PipeWire's ALSA plugin (pipewire-alsa,
		 * gstreamer1.0-alsa), named because the board's default ALSA
		 * device is the hardware. GstAudioBaseSink aligns its ring
		 * buffer against ALSA's delay, which PipeWire's plugin reports
		 * including the sound card's own buffer: -2..+12 ms on
		 * av-sync-probe, where a synced player reads 0..+17. The
		 * alternatives measured worse (2026-10-03):
		 *  - autoaudiosink alone settles on openalsink, silent here;
		 *  - pipewiresink took planar audio as interleaved (static),
		 *    then ran +768 ms late after idle and +80 ms warm; patched
		 *    (patches/pipewire, retired) it still read +43..+60 ms.
		 * 200 ms buffer / 40 ms periods, not alsasink's 10 ms: every
		 * period wakes the player's PipeWire thread and kicks the CPU
		 * frequency governor. Whole board 17.9% -> 7.3% (no audio:
		 * 2.7%), sync +14..+29 ms (2026-10-03).
		 * GST_PLANE_PLAY_AUDIOSINK replaces the sink for measurements.
		 * The pipeline clock is pinned to the system clock in main(). */
		GstElementFactory *alsa = gst_element_factory_find("alsasink");
		const char *override = getenv("GST_PLANE_PLAY_AUDIOSINK");
		const char *sink = override && *override ? override :
				   alsa ? "alsasink device=pipewire "
					  "buffer-time=200000 latency-time=40000" :
				   "autoaudiosink";

		if (alsa)
			gst_object_unref(alsa);
		else if (!strcmp(sink, "autoaudiosink"))
			fprintf(stderr, "gst-plane-play: no alsasink "
				"(gstreamer1.0-alsa); audio may go nowhere\n");
		description = g_strdup_printf("queue ! audioconvert ! "
					      "audioresample ! %s", sink);
		p->have_audio = attach(p, pad, description);
		g_free(description);
	}

	gst_caps_unref(caps);
}

static gboolean stop(gpointer data)
{
	g_main_loop_quit(((struct player *)data)->loop);
	return G_SOURCE_REMOVE;
}

static gboolean on_message(GstBus *bus, GstMessage *message, gpointer data)
{
	struct player *p = data;
	GError *error = NULL;
	gchar *debug = NULL;

	(void)bus;

	switch (GST_MESSAGE_TYPE(message)) {
	case GST_MESSAGE_ERROR:
		gst_message_parse_error(message, &error, &debug);
		fprintf(stderr, "gst-plane-play: ERROR from %s: %s\n%s\n",
			GST_OBJECT_NAME(message->src), error->message,
			debug ? debug : "");
		g_clear_error(&error);
		g_free(debug);
		p->status = 1;
		g_main_loop_quit(p->loop);
		break;
	case GST_MESSAGE_EOS:
		g_main_loop_quit(p->loop);
		break;
	default:
		break;
	}

	return TRUE;
}

int main(int argc, char **argv)
{
	struct player p = { 0 };
	guint64 rendered = 0, dropped = 0;
	gint64 position;
	GstElement *source, *vsink;
	GstCaps *stop_caps;
	GstClock *clock;
	gchar *uri;

	gst_init(&argc, &argv);

	if (argc < 4 ||
	    (strcmp(argv[2], "h264") && strcmp(argv[2], "h265") &&
	     strcmp(argv[2], "vp9") && strcmp(argv[2], "av1"))) {
		fprintf(stderr, "usage: %s FILE h264|h265|vp9|av1 DECODER "
			"[WxH] [SECONDS]\n", argv[0]);
		return 2;
	}
	p.codec = argv[2];
	p.decoder = argv[3];

	if (argc > 4 && strcmp(argv[4], "-")) {
		if (sscanf(argv[4], "%dx%d", &out_w, &out_h) != 2 ||
		    out_w <= 0 || out_h <= 0) {
			fprintf(stderr, "gst-plane-play: bad size %s\n", argv[4]);
			return 2;
		}
		p.scaled = TRUE;
	}

	p.pipeline = gst_pipeline_new("play");
	/* The system clock, which the audio sink follows. pipewiresink's own
	 * clock once showed a 720p clip 93 frames in 19 s, the rest late; the
	 * alsasink numbers were all measured on this clock (2026-10-03). */
	clock = gst_system_clock_obtain();
	gst_pipeline_use_clock(GST_PIPELINE(p.pipeline), clock);
	gst_object_unref(clock);
	p.loop = g_main_loop_new(NULL, FALSE);

	/* Stop at the compressed video (our decoder, not decodebin's pick)
	 * and at raw audio. */
	source = gst_element_factory_make("uridecodebin", "source");
	uri = gst_filename_to_uri(argv[1], NULL);
	stop_caps = gst_caps_from_string("video/x-h264;video/x-h265;"
					 "video/x-vp9;video/x-av1;audio/x-raw");
	g_object_set(source, "uri", uri, "caps", stop_caps, NULL);
	gst_caps_unref(stop_caps);
	g_free(uri);
	gst_bin_add(GST_BIN(p.pipeline), source);
	g_signal_connect(source, "pad-added", G_CALLBACK(on_pad_added), &p);

	gst_bus_add_watch(GST_ELEMENT_BUS(p.pipeline), on_message, &p);
	gst_element_set_state(p.pipeline, GST_STATE_PLAYING);
	if (argc > 5 && atoi(argv[5]) > 0)
		g_timeout_add_seconds(atoi(argv[5]), stop, &p);
	/* Ctrl-C and kill end the run like EOS: counts printed, the pipeline
	 * torn down, the plane released. */
	g_unix_signal_add(SIGINT, stop, &p);
	g_unix_signal_add(SIGTERM, stop, &p);
	g_main_loop_run(p.loop);

	/* GstBaseSink's own counters (fpsdisplaysink would wrap the sink in
	 * a ghost pad that gst_parse_bin_from_description mistakes for the
	 * bin's input). */
	vsink = gst_bin_get_by_name(GST_BIN(p.pipeline), "vsink");
	if (vsink) {
		GstStructure *stats;

		g_object_get(vsink, "stats", &stats, NULL);
		gst_structure_get_uint64(stats, "rendered", &rendered);
		gst_structure_get_uint64(stats, "dropped", &dropped);
		gst_structure_free(stats);
		gst_object_unref(vsink);
	}
	/* The position says how much of the stream should have been shown:
	 * rendered against position separates a slow start from a steady
	 * shortfall. */
	if (!gst_element_query_position(p.pipeline, GST_FORMAT_TIME, &position))
		position = -1;
	printf("gst-plane-play: video=%s audio=%s rendered %" G_GUINT64_FORMAT
	       ", dropped %" G_GUINT64_FORMAT ", position %.3f s\n",
	       p.have_video ? "yes" : "no", p.have_audio ? "yes" : "no",
	       rendered, dropped, position < 0 ? -1.0 : position / 1e9);

	gst_element_set_state(p.pipeline, GST_STATE_NULL);
	gst_object_unref(p.pipeline);
	g_main_loop_unref(p.loop);
	return p.status;
}
