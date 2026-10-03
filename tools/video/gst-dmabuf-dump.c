// SPDX-License-Identifier: GPL-2.0
/*
 * Dump a GStreamer decoder's output to a raw file, including formats that
 * exist only as dma-bufs. RUNS ON THE TARGET.
 *
 * WHY THIS EXISTS. `v4l2slav1dec ! filesink` cannot write 10-bit AV1. The
 * decoder hands out DMA_DRM caps (P010 + DRM_FORMAT_MOD_ALLWINNER_LSB10),
 * because no GstVideoFormat describes the core's LSB-aligned layout, so there
 * is no system-memory fallback. And it outputs DMA_DRM only to a peer that
 * accepts frame-layout metadata (GstVideoMeta), which filesink never does
 * (gstv4l2codecav1dec.c:430): negotiation fails before a frame is decoded.
 * appsink can accept it since GStreamer 1.24, through its propose_allocation
 * callback. That is all this tool adds.
 *
 * Each frame's planes are written tight-packed at the picture size (luma,
 * then the interleaved chroma), whatever pitch and padding the decoder used:
 * hantro pads 720 lines to 768. Bytes per sample come from the caps:
 * P010 -> 2 (left as the decoder wrote it, so --layout lsb for
 * tools/video/p010-compare.py on 10-bit AV1), NV12 -> 1. dma-buf memory is
 * read through its own mmap inside DMA_BUF_IOCTL_SYNC; system memory is
 * mapped the GStreamer way.
 *
 * Build on the target:
 *   cc -O2 -Wall -o gst-dmabuf-dump gst-dmabuf-dump.c \
 *      $(pkg-config --cflags --libs gstreamer-1.0 gstreamer-app-1.0 \
 *        gstreamer-video-1.0 gstreamer-allocators-1.0)
 *
 * The 10-bit format needs the project's v4l2codecs (patches/gstreamer):
 * source /opt/gst-h713/env first. The stock plugin refuses 10-bit AV1.
 *
 *   usage: gst-dmabuf-dump '<pipeline without a sink>' out.raw
 *   e.g.   gst-dmabuf-dump 'filesrc location=hbd720.ivf ! ivfparse ! av1parse ! v4l2slav1dec' out.raw
 *
 * Prints the frame count and geometry. A run that writes no frame fails:
 * a dump tool that "succeeds" with an empty file is how a missing decoder
 * looks like a passing test.
 */
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>

#include <linux/dma-buf.h>

#include <gst/gst.h>
#include <gst/app/gstappsink.h>
#include <gst/video/video.h>
#include <gst/allocators/gstdmabuf.h>

static gboolean propose_allocation(GstAppSink *sink, GstQuery *query,
				   gpointer user_data)
{
	(void)sink;
	(void)user_data;
	gst_query_add_allocation_meta(query, GST_VIDEO_META_API_TYPE, NULL);
	return TRUE;
}

/*
 * The pipeline's error, if it has one, printed. appsink's pull blocks until
 * EOS, so a decoder that fails mid-stream would otherwise hang the tool.
 */
static gboolean pipeline_failed(GstElement *pipeline)
{
	GstBus *bus = gst_element_get_bus(pipeline);
	GstMessage *msg = gst_bus_pop_filtered(bus, GST_MESSAGE_ERROR);
	GError *err = NULL;
	gchar *debug = NULL;

	gst_object_unref(bus);
	if (!msg)
		return FALSE;
	gst_message_parse_error(msg, &err, &debug);
	fprintf(stderr, "error: %s\n%s%s", err->message, debug ? debug : "",
		debug ? "\n" : "");
	g_error_free(err);
	g_free(debug);
	gst_message_unref(msg);
	return TRUE;
}

static int dmabuf_sync(int fd, guint64 flags)
{
	struct dma_buf_sync sync = { .flags = flags };
	int rc;

	do
		rc = ioctl(fd, DMA_BUF_IOCTL_SYNC, &sync);
	while (rc < 0 && (errno == EINTR || errno == EAGAIN));
	return rc;
}

/* 2 for P010 in any spelling, 1 for 8-bit; 0 if the caps say neither. */
static unsigned int bytes_per_sample(GstCaps *caps)
{
	GstStructure *s = gst_caps_get_structure(caps, 0);
	const char *format = gst_structure_get_string(s, "format");

	if (format && !strcmp(format, "DMA_DRM"))
		format = gst_structure_get_string(s, "drm-format");
	if (!format)
		return 0;
	if (!strncmp(format, "P010", 4))
		return 2;
	if (!strncmp(format, "NV12", 4))
		return 1;
	return 0;
}

/* Write rows x row_bytes from base, pitch apart. */
static int write_plane(FILE *out, const guint8 *base, gsize avail,
		       unsigned int pitch, unsigned int row_bytes,
		       unsigned int rows)
{
	unsigned int r;

	if (rows && (gsize)(rows - 1) * pitch + row_bytes > avail) {
		fprintf(stderr, "plane runs past its memory (%u rows x %u, pitch %u, %zu bytes)\n",
			rows, row_bytes, pitch, (size_t)avail);
		return -1;
	}
	for (r = 0; r < rows; r++)
		if (fwrite(base + (gsize)r * pitch, 1, row_bytes, out) != row_bytes)
			return -1;
	return 0;
}

static int dump_frame(GstSample *sample, FILE *out, unsigned int *width,
		      unsigned int *height, unsigned int *bps,
		      gboolean *was_dmabuf)
{
	GstBuffer *buf = gst_sample_get_buffer(sample);
	GstCaps *caps = gst_sample_get_caps(sample);
	GstVideoMeta *meta = gst_buffer_get_video_meta(buf);
	unsigned int plane;

	*bps = bytes_per_sample(caps);
	if (!*bps) {
		gchar *s = gst_caps_to_string(caps);

		fprintf(stderr, "unsupported caps: %s\n", s);
		g_free(s);
		return -1;
	}
	if (!meta || meta->n_planes != 2) {
		fprintf(stderr, "frame without a two-plane GstVideoMeta\n");
		return -1;
	}
	/*
	 * The picture size from the caps; the meta's is the allocation's
	 * (hantro pads 360 lines to 384, 720 to 768). Only the strides and
	 * offsets are taken from the meta.
	 */
	{
		GstStructure *st = gst_caps_get_structure(caps, 0);
		int w, h;

		if (!gst_structure_get_int(st, "width", &w) ||
		    !gst_structure_get_int(st, "height", &h) ||
		    (guint)w > meta->width || (guint)h > meta->height) {
			fprintf(stderr, "caps carry no usable picture size\n");
			return -1;
		}
		*width = w;
		*height = h;
	}

	for (plane = 0; plane < 2; plane++) {
		unsigned int rows = plane ? (*height + 1) / 2 : *height;
		unsigned int row_bytes = ((*width + plane) & ~plane) * *bps;
		GstMemory *mem;
		guint idx, len;
		gsize skip, mem_offset, mem_size;
		int rc;

		if (!gst_buffer_find_memory(buf, meta->offset[plane], 1, &idx,
					    &len, &skip)) {
			fprintf(stderr, "plane %u offset %zu is in no memory\n",
				plane, (size_t)meta->offset[plane]);
			return -1;
		}
		mem = gst_buffer_peek_memory(buf, idx);
		mem_size = gst_memory_get_sizes(mem, &mem_offset, NULL);

		if (gst_is_dmabuf_memory(mem)) {
			int fd = gst_dmabuf_memory_get_fd(mem);
			off_t total = lseek(fd, 0, SEEK_END);
			guint8 *map;

			*was_dmabuf = TRUE;
			if (total <= 0) {
				perror("lseek dma-buf");
				return -1;
			}
			map = mmap(NULL, total, PROT_READ, MAP_SHARED, fd, 0);
			if (map == MAP_FAILED) {
				perror("mmap dma-buf");
				return -1;
			}
			dmabuf_sync(fd, DMA_BUF_SYNC_START | DMA_BUF_SYNC_READ);
			rc = write_plane(out, map + mem_offset + skip,
					 mem_size - skip, meta->stride[plane],
					 row_bytes, rows);
			dmabuf_sync(fd, DMA_BUF_SYNC_END | DMA_BUF_SYNC_READ);
			munmap(map, total);
		} else {
			GstMapInfo info;

			if (!gst_memory_map(mem, &info, GST_MAP_READ)) {
				fprintf(stderr, "cannot map plane %u\n", plane);
				return -1;
			}
			rc = write_plane(out, info.data + skip, info.size - skip,
					 meta->stride[plane], row_bytes, rows);
			gst_memory_unmap(mem, &info);
		}
		if (rc < 0)
			return -1;
	}
	return 0;
}

int main(int argc, char **argv)
{
	GstAppSinkCallbacks callbacks = { 0 };
	GstElement *pipeline, *sink;
	GError *error = NULL;
	gchar *description;
	unsigned int frames = 0, width = 0, height = 0, bps = 0;
	gboolean was_dmabuf = FALSE;
	FILE *out;
	int rc = 1;

	gst_init(&argc, &argv);
	if (argc != 3) {
		fprintf(stderr, "usage: %s '<pipeline without a sink>' out.raw\n", argv[0]);
		return 2;
	}

	/*
	 * Say DMA_DRM out loud: the decoder offers its DMA_DRM-only formats to
	 * a peer whose caps list them, and ANY does not count.
	 *
	 * max-buffers bounds the queue (appsink then blocks the decoder). The
	 * default is unbounded, and with sync=false a decoder that outruns the
	 * file writes keeps every frame alive: GStreamer va then allocates a
	 * new surface per frame until the VA driver's 32 CAPTURE buffers run
	 * out, and the decodes beyond that fail ("resource allocation
	 * failed"), which dropped 20 of 60 H.264 frames, 2026-10-03.
	 */
	description = g_strdup_printf("%s ! appsink name=sink sync=false "
				      "max-buffers=2 "
				      "caps=\"video/x-raw(memory:DMABuf),format=DMA_DRM;"
				      "video/x-raw\"", argv[1]);
	pipeline = gst_parse_launch(description, &error);
	g_free(description);
	if (!pipeline) {
		fprintf(stderr, "pipeline: %s\n", error ? error->message : "?");
		return 1;
	}
	sink = gst_bin_get_by_name(GST_BIN(pipeline), "sink");
	callbacks.propose_allocation = propose_allocation;
	gst_app_sink_set_callbacks(GST_APP_SINK(sink), &callbacks, NULL, NULL);

	out = fopen(argv[2], "wb");
	if (!out) {
		perror(argv[2]);
		return 1;
	}

	if (gst_element_set_state(pipeline, GST_STATE_PLAYING) ==
	    GST_STATE_CHANGE_FAILURE) {
		fprintf(stderr, "pipeline refused to start\n");
		goto out;
	}

	for (;;) {
		GstSample *sample = gst_app_sink_try_pull_sample(GST_APP_SINK(sink),
								 GST_SECOND / 2);

		if (!sample) {
			if (pipeline_failed(pipeline))
				goto out;
			if (gst_app_sink_is_eos(GST_APP_SINK(sink)))
				break;
			continue;
		}
		if (dump_frame(sample, out, &width, &height, &bps, &was_dmabuf)) {
			gst_sample_unref(sample);
			goto out;
		}
		gst_sample_unref(sample);
		frames++;
	}

	if (pipeline_failed(pipeline))
		goto out;
	if (!frames) {
		fprintf(stderr, "no frame reached the sink\n");
		goto out;
	}
	printf("%u frames, %ux%u, %u byte(s) per sample, %s memory -> %s\n",
	       frames, width, height, bps, was_dmabuf ? "dma-buf" : "system",
	       argv[2]);
	rc = 0;
out:
	if (fclose(out))
		rc = 1;
	gst_element_set_state(pipeline, GST_STATE_NULL);
	gst_object_unref(sink);
	gst_object_unref(pipeline);
	return rc;
}
