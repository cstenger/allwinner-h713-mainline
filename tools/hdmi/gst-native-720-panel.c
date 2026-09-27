// SPDX-License-Identifier: GPL-2.0
/*
 * Bounded H713 HDMI capture-to-panel pipeline with machine-readable counters.
 *
 * Build on the target:
 *   cc -O2 -Wall -Wextra -o gst-native-720-panel \
 *      gst-native-720-panel.c $(pkg-config --cflags --libs gstreamer-1.0)
 *
 * This program changes the visible panel. Its caller must enforce the
 * camera-ready checkpoint and restore the console after it exits.
 */

#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>

#include <gst/gst.h>

#define DEFAULT_FRAMES 360u
#define MAX_FRAMES 1200u

struct timing_stats {
	GMutex lock;
	guint64 source_buffers;
	guint64 sink_buffers;
	guint64 pts_mismatches;
	guint64 unmatched_buffers;
	gint64 source_arrival_us[MAX_FRAMES];
	GstClockTime source_pts[MAX_FRAMES];
	guint64 conversion_total_us;
	guint64 conversion_max_us;
};

static GstPadProbeReturn source_probe(GstPad *pad, GstPadProbeInfo *info,
				      gpointer data)
{
	struct timing_stats *stats = data;
	GstBuffer *buffer;
	guint64 index;

	(void)pad;
	if (!(GST_PAD_PROBE_INFO_TYPE(info) & GST_PAD_PROBE_TYPE_BUFFER))
		return GST_PAD_PROBE_OK;
	buffer = GST_PAD_PROBE_INFO_BUFFER(info);

	g_mutex_lock(&stats->lock);
	index = stats->source_buffers++;
	if (index < MAX_FRAMES) {
		stats->source_arrival_us[index] = g_get_monotonic_time();
		stats->source_pts[index] = GST_BUFFER_PTS(buffer);
	}
	g_mutex_unlock(&stats->lock);
	return GST_PAD_PROBE_OK;
}

static GstPadProbeReturn sink_probe(GstPad *pad, GstPadProbeInfo *info,
				    gpointer data)
{
	struct timing_stats *stats = data;
	GstBuffer *buffer;
	guint64 index;
	gint64 now_us;

	(void)pad;
	if (!(GST_PAD_PROBE_INFO_TYPE(info) & GST_PAD_PROBE_TYPE_BUFFER))
		return GST_PAD_PROBE_OK;
	buffer = GST_PAD_PROBE_INFO_BUFFER(info);
	now_us = g_get_monotonic_time();

	g_mutex_lock(&stats->lock);
	index = stats->sink_buffers++;
	if (index >= MAX_FRAMES || index >= stats->source_buffers) {
		stats->unmatched_buffers++;
	} else {
		guint64 elapsed_us = now_us - stats->source_arrival_us[index];

		if (stats->source_pts[index] != GST_BUFFER_PTS(buffer))
			stats->pts_mismatches++;
		stats->conversion_total_us += elapsed_us;
		if (elapsed_us > stats->conversion_max_us)
			stats->conversion_max_us = elapsed_us;
	}
	g_mutex_unlock(&stats->lock);
	return GST_PAD_PROBE_OK;
}

static guint64 structure_counter(const GstStructure *stats, const char *name)
{
	guint64 value64;
	guint value;

	if (stats && gst_structure_get_uint64(stats, name, &value64))
		return value64;
	if (stats && gst_structure_get_uint(stats, name, &value))
		return value;
	return G_MAXUINT64;
}

int main(int argc, char **argv)
{
	struct timing_stats timing = { 0 };
	GstElement *pipeline = NULL, *source = NULL, *sink = NULL;
	GstPad *source_pad = NULL, *sink_pad = NULL;
	GstBus *bus = NULL;
	GstMessage *message = NULL;
	GstStructure *sink_stats = NULL;
	GError *error = NULL;
	gchar *description = NULL;
	guint frames = DEFAULT_FRAMES;
	guint64 rendered, dropped;
	gint64 start_us, end_us;
	double conversion_mean_us = 0.0;
	gboolean selftest;
	int rc = EXIT_FAILURE;

	if (argc > 2) {
		fprintf(stderr, "usage: %s [frames]\n", argv[0]);
		return EXIT_FAILURE;
	}
	if (argc == 2) {
		char *end;
		unsigned long value = strtoul(argv[1], &end, 10);

		if (*end || value < 1 || value > MAX_FRAMES) {
			fprintf(stderr, "frames must be 1..%u\n", MAX_FRAMES);
			return EXIT_FAILURE;
		}
		frames = value;
	}

	gst_init(&argc, &argv);
	g_mutex_init(&timing.lock);
	selftest = g_getenv("H713_GST_SELFTEST") != NULL;
	if (selftest)
		description = g_strdup_printf(
			"videotestsrc name=source num-buffers=%u is-live=true "
			"! video/x-raw,format=NV16,width=1280,height=720,framerate=60/1 "
			"! videoconvert n-threads=4 "
			"! video/x-raw,format=NV12 "
			"! fakesink name=panel sync=false", frames);
	else
		description = g_strdup_printf(
			"v4l2src name=source device=/dev/video1 num-buffers=%u io-mode=mmap "
			"! video/x-raw,format=NV16,width=1280,height=720,framerate=60/1 "
			"! videoconvert n-threads=4 "
			"! video/x-raw,format=NV12 "
			"! kmssink name=panel driver-name=sun50i-h713-afbd "
			"sync=false skip-vsync=true", frames);
	pipeline = gst_parse_launch(description, &error);
	g_free(description);
	if (!pipeline || error) {
		fprintf(stderr, "pipeline construction failed: %s\n",
			error ? error->message : "unknown error");
		g_clear_error(&error);
		goto out;
	}

	source = gst_bin_get_by_name(GST_BIN(pipeline), "source");
	sink = gst_bin_get_by_name(GST_BIN(pipeline), "panel");
	if (!source || !sink) {
		fprintf(stderr, "pipeline elements were not found\n");
		goto out;
	}
	source_pad = gst_element_get_static_pad(source, "src");
	sink_pad = gst_element_get_static_pad(sink, "sink");
	if (!source_pad || !sink_pad) {
		fprintf(stderr, "pipeline pads were not found\n");
		goto out;
	}
	gst_pad_add_probe(source_pad, GST_PAD_PROBE_TYPE_BUFFER,
			  source_probe, &timing, NULL);
	gst_pad_add_probe(sink_pad, GST_PAD_PROBE_TYPE_BUFFER,
			  sink_probe, &timing, NULL);

	bus = gst_element_get_bus(pipeline);
	start_us = g_get_monotonic_time();
	if (gst_element_set_state(pipeline, GST_STATE_PLAYING) ==
	    GST_STATE_CHANGE_FAILURE) {
		fprintf(stderr, "pipeline could not enter PLAYING\n");
		goto out;
	}
	message = gst_bus_timed_pop_filtered(bus, 20 * GST_SECOND,
					     GST_MESSAGE_ERROR |
					     GST_MESSAGE_EOS);
	end_us = g_get_monotonic_time();
	if (!message) {
		fprintf(stderr, "pipeline timed out\n");
		goto out;
	}
	if (GST_MESSAGE_TYPE(message) == GST_MESSAGE_ERROR) {
		gchar *debug = NULL;

		gst_message_parse_error(message, &error, &debug);
		fprintf(stderr, "pipeline error: %s%s%s\n", error->message,
			debug ? "; " : "", debug ? debug : "");
		g_free(debug);
		g_clear_error(&error);
		goto out;
	}

	g_object_get(sink, "stats", &sink_stats, NULL);
	rendered = structure_counter(sink_stats, "rendered");
	dropped = structure_counter(sink_stats, "dropped");
	if (timing.sink_buffers)
		conversion_mean_us = (double)timing.conversion_total_us /
				     timing.sink_buffers;

	printf("{\"selftest\":%s,\"requested_frames\":%u,"
	       "\"source_buffers\":%" PRIu64
	       ",\"sink_buffers\":%" PRIu64 ",\"rendered\":%" PRIu64
	       ",\"dropped\":%" PRIu64 ",\"pts_mismatches\":%" PRIu64
	       ",\"unmatched_buffers\":%" PRIu64
	       ",\"conversion_mean_us\":%.2f,\"conversion_max_us\":%" PRIu64
	       ",\"elapsed_seconds\":%.9f}\n",
	       selftest ? "true" : "false", frames, timing.source_buffers,
	       timing.sink_buffers, rendered,
	       dropped, timing.pts_mismatches, timing.unmatched_buffers,
	       conversion_mean_us, timing.conversion_max_us,
	       (end_us - start_us) / 1000000.0);
	if (timing.source_buffers != frames || timing.sink_buffers != frames ||
	    rendered != frames || dropped || timing.pts_mismatches ||
	    timing.unmatched_buffers)
		goto out;
	rc = EXIT_SUCCESS;

out:
	if (pipeline)
		gst_element_set_state(pipeline, GST_STATE_NULL);
	if (sink_stats)
		gst_structure_free(sink_stats);
	if (message)
		gst_message_unref(message);
	if (bus)
		gst_object_unref(bus);
	if (source_pad)
		gst_object_unref(source_pad);
	if (sink_pad)
		gst_object_unref(sink_pad);
	if (source)
		gst_object_unref(source);
	if (sink)
		gst_object_unref(sink);
	if (pipeline)
		gst_object_unref(pipeline);
	g_mutex_clear(&timing.lock);
	return rc;
}
