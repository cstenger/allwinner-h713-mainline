// SPDX-License-Identifier: GPL-2.0
/*
 * Seek/flush test for a stateless decoder behind GStreamer. RUNS ON THE TARGET.
 *
 * Plays a pipeline that ends in "appsink name=sink", and for each position
 * given does a flushing seek and pulls N frames, printing each frame's
 * timestamp and MD5. The caller maps timestamps to frame numbers and checks
 * the hashes against a software reference (gst-seek-check.sh), so a frame
 * decoded against the wrong references after a flush shows up as a mismatch
 * rather than as "it kept playing".
 *
 * Seeks are issued while the decoder is mid-stream (frames still queued),
 * which is what a player does.
 *
 *   cc -O2 -o gst-seek-test gst-seek-test.c \
 *      $(pkg-config --cflags --libs gstreamer-1.0 gstreamer-app-1.0)
 *   gst-seek-test N 'filesrc location=x.mp4 ! qtdemux ! av1parse ! v4l2slav1dec !
 *      videoconvert ! video/x-raw,format=I420 ! appsink name=sink sync=false' \
 *      0 12.5 3.0 ...            (seconds; a leading "k" = KEY_UNIT, else ACCURATE)
 */
#include <gst/gst.h>
#include <gst/app/gstappsink.h>
#include <stdio.h>
#include <stdlib.h>

static int pull(GstElement *sink, int n, const char *tag)
{
	int i;

	for (i = 0; i < n; i++) {
		GstSample *s = gst_app_sink_try_pull_sample(GST_APP_SINK(sink), 20 * GST_SECOND);
		GstBuffer *b;
		GstMapInfo m;
		gchar *sum;

		if (!s) {
			if (gst_app_sink_is_eos(GST_APP_SINK(sink))) {
				printf("%s eos\n", tag);
				return 0;
			}
			printf("%s TIMEOUT after %d frames\n", tag, i);
			return -1;
		}
		b = gst_sample_get_buffer(s);
		gst_buffer_map(b, &m, GST_MAP_READ);
		sum = g_compute_checksum_for_data(G_CHECKSUM_MD5, m.data, m.size);
		printf("%s frame %" G_GUINT64_FORMAT " %s\n", tag, GST_BUFFER_PTS(b), sum);
		g_free(sum);
		gst_buffer_unmap(b, &m);
		gst_sample_unref(s);
	}
	return 0;
}

int main(int argc, char **argv)
{
	GstElement *pipe, *sink;
	GError *err = NULL;
	int n, i, ret = 0;

	gst_init(&argc, &argv);
	if (argc < 4) {
		fprintf(stderr, "usage: %s frames-per-seek 'pipeline ! appsink name=sink' pos...\n", argv[0]);
		return 2;
	}
	n = atoi(argv[1]);
	pipe = gst_parse_launch(argv[2], &err);
	if (!pipe) {
		fprintf(stderr, "pipeline: %s\n", err->message);
		return 2;
	}
	sink = gst_bin_get_by_name(GST_BIN(pipe), "sink");
	g_object_set(sink, "max-buffers", 4, "drop", FALSE, NULL);
	gst_element_set_state(pipe, GST_STATE_PLAYING);
	if (pull(sink, n, "start") < 0)
		ret = 1;

	for (i = 3; i < argc && !ret; i++) {
		gboolean key = argv[i][0] == 'k';
		double pos = atof(argv[i] + key);
		char tag[32];

		snprintf(tag, sizeof(tag), "seek%d@%s", i - 2, argv[i]);
		if (!gst_element_seek_simple(pipe, GST_FORMAT_TIME,
					     GST_SEEK_FLAG_FLUSH |
					     (key ? GST_SEEK_FLAG_KEY_UNIT : GST_SEEK_FLAG_ACCURATE),
					     (gint64)(pos * GST_SECOND))) {
			printf("%s SEEK-REFUSED\n", tag);
			ret = 1;
			break;
		}
		if (pull(sink, n, tag) < 0)
			ret = 1;
	}
	gst_element_set_state(pipe, GST_STATE_NULL);
	return ret;
}
