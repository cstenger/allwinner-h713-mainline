/*
 * Measure A/V sync at the outputs: when a flash reaches the display plane and
 * when its beep reaches the sound card, on one clock. RUNS ON THE TARGET.
 *
 * Play a clip with a full-screen white flash and a 1 kHz beep at the same
 * instants, irregularly spaced (tools/video/make-avsync-clip.sh), with any
 * player, and run this alongside. It finds the one offset (within +-3 s)
 * that lines up the flash and beep sequences, then prints each pair's
 * offset beep - flash (positive: audio late) and the median.
 *
 * Video. A tight loop reads the plane state (the video plane when it holds
 * NV12, else the topmost plane with a framebuffer: the GPU path's primary),
 * maps each framebuffer once and samples a centre patch. A flash is the first
 * sample of a bright frame. The plane state is swapped when the commit is
 * applied, which can be up to one vblank before scan-out, so a flash time is
 * early by 0-16.7 ms; the panel's own latency after scan-out is not seen.
 *
 * Audio. PipeWire's sink monitor through pipewiresrc, as what reaches the
 * sound card. Each buffer is stamped with its arrival on CLOCK_MONOTONIC, and
 * the timeline is the earliest-arrival envelope: sample n played at
 * n / rate + min over buffers of (arrival - end-of-buffer sample / rate),
 * which cancels scheduling jitter. Then the frames still queued in the ALSA
 * ring (the PCM status "delay", sampled throughout) are added: the monitor is
 * written in the same graph cycle that fills the ring, and the DAC plays it
 * that much later.
 *
 *   usage: av-sync-probe SECONDS
 *
 * Build on the board:
 *   gcc -O2 -Wall -o av-sync-probe av-sync-probe.c -lm \
 *       $(pkg-config --cflags --libs gstreamer-1.0 gstreamer-app-1.0 libdrm)
 */
#include <fcntl.h>
#include <glob.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>
#include <linux/dma-buf.h>
#include <drm_fourcc.h>
#include <xf86drm.h>
#include <xf86drmMode.h>
#include <gst/gst.h>
#include <gst/app/gstappsink.h>

#define RATE 48000
#define MAX_EVENTS 4096
#define MAX_FBS 64

static double now(void)
{
	struct timespec ts;

	clock_gettime(CLOCK_MONOTONIC, &ts);
	return ts.tv_sec + ts.tv_nsec / 1e9;
}

/* --- audio: sink monitor, earliest-arrival timeline -------------------- */

static int16_t *pcm;
static size_t pcm_len, pcm_cap;
static double env_offset = 1e30;	/* min(arrival - samples / RATE) */

static GstFlowReturn on_sample(GstAppSink *sink, gpointer data)
{
	GstSample *sample = gst_app_sink_pull_sample(sink);
	double arrival = now();
	GstBuffer *buffer;
	GstMapInfo map;
	size_t n;

	(void)data;
	if (!sample)
		return GST_FLOW_EOS;
	buffer = gst_sample_get_buffer(sample);
	if (gst_buffer_map(buffer, &map, GST_MAP_READ)) {
		n = map.size / 2;
		if (pcm_len + n > pcm_cap) {
			pcm_cap = (pcm_len + n) * 2;
			pcm = realloc(pcm, pcm_cap * 2);
		}
		memcpy(pcm + pcm_len, map.data, n * 2);
		pcm_len += n;
		if (arrival - (double)pcm_len / RATE < env_offset)
			env_offset = arrival - (double)pcm_len / RATE;
		gst_buffer_unmap(buffer, &map);
	}
	gst_sample_unref(sample);
	return GST_FLOW_OK;
}

/* Frames queued in the playback PCM, from its proc status. */
static long alsa_delay(void)
{
	glob_t g;
	long delay = -1;

	if (glob("/proc/asound/card*/pcm*p/sub0/status", 0, NULL, &g))
		return -1;
	for (size_t i = 0; i < g.gl_pathc && delay < 0; i++) {
		char line[128];
		FILE *f = fopen(g.gl_pathv[i], "r");
		int running = 0;

		if (!f)
			continue;
		while (fgets(line, sizeof(line), f)) {
			if (!strncmp(line, "state: RUNNING", 14))
				running = 1;
			if (running && sscanf(line, "delay : %ld", &delay) == 1)
				break;
		}
		fclose(f);
	}
	globfree(&g);
	return delay;
}

/* --- video: plane sampling ---------------------------------------------- */

struct fbmap {
	uint32_t id;
	uint8_t *map;
	size_t len;
	int dfd;
	uint32_t format, pitch, offset, width, height;
};

static struct fbmap fbs[MAX_FBS];

static struct fbmap *fb_get(int fd, uint32_t id)
{
	drmModeFB2 *fb;
	struct fbmap *m = NULL;
	int dfd;

	for (int i = 0; i < MAX_FBS; i++) {
		if (fbs[i].id == id)
			return &fbs[i];
		if (!m && !fbs[i].id)
			m = &fbs[i];
	}
	if (!m)
		return NULL;

	fb = drmModeGetFB2(fd, id);
	if (!fb || !fb->handles[0] ||
	    drmPrimeHandleToFD(fd, fb->handles[0], O_RDONLY | O_CLOEXEC, &dfd)) {
		if (fb)
			drmModeFreeFB2(fb);
		return NULL;
	}
	m->len = lseek(dfd, 0, SEEK_END);
	m->map = mmap(NULL, m->len, PROT_READ, MAP_SHARED, dfd, 0);
	if (m->map == MAP_FAILED) {
		close(dfd);
		drmModeFreeFB2(fb);
		return NULL;
	}
	m->id = id;
	m->dfd = dfd;
	m->format = fb->pixel_format;
	m->pitch = fb->pitches[0];
	m->offset = fb->offsets[0];
	m->width = fb->width;
	m->height = fb->height;
	drmModeFreeFB2(fb);
	return m;
}

/* Mean brightness of a 16x16 centre patch: luma for NV12, green for RGB. */
static int patch(struct fbmap *m)
{
	struct dma_buf_sync sync = { DMA_BUF_SYNC_START | DMA_BUF_SYNC_READ };
	int bpp = m->format == DRM_FORMAT_NV12 ? 1 : 4;
	int x0 = m->width / 2 - 8, y0 = m->height / 2 - 8;
	long sum = 0;

	ioctl(m->dfd, DMA_BUF_IOCTL_SYNC, &sync);
	for (int y = y0; y < y0 + 16; y++)
		for (int x = x0; x < x0 + 16; x++)
			sum += m->map[m->offset + (size_t)y * m->pitch +
				      x * bpp + (bpp == 4 ? 1 : 0)];
	sync.flags = DMA_BUF_SYNC_END | DMA_BUF_SYNC_READ;
	ioctl(m->dfd, DMA_BUF_IOCTL_SYNC, &sync);
	return sum / 256;
}

/* The NV12 video plane if it is showing something, else the topmost plane
 * with a framebuffer. */
static uint32_t pick_fb(int fd, drmModePlaneRes *res)
{
	uint32_t best = 0, nv12 = 0;

	for (uint32_t i = 0; i < res->count_planes; i++) {
		drmModePlane *p = drmModeGetPlane(fd, res->planes[i]);

		if (!p)
			continue;
		if (p->crtc_id && p->fb_id) {
			struct fbmap *m = fb_get(fd, p->fb_id);

			if (m && m->format == DRM_FORMAT_NV12)
				nv12 = p->fb_id;
			best = p->fb_id;
		}
		drmModeFreePlane(p);
	}
	return nv12 ? nv12 : best;
}

static int cmp_double(const void *a, const void *b)
{
	double x = *(const double *)a, y = *(const double *)b;

	return x < y ? -1 : x > y;
}

static int cmp_long(const void *a, const void *b)
{
	long x = *(const long *)a, y = *(const long *)b;

	return x < y ? -1 : x > y;
}

int main(int argc, char **argv)
{
	static double flashes[MAX_EVENTS], beeps[MAX_EVENTS], offs[MAX_EVENTS];
	static long delays[100000];
	int nflash = 0, nbeep = 0, noff = 0, ndelay = 0;
	double seconds = argc > 1 ? atof(argv[1]) : 20, t0, end, last_alsa = 0;
	GstElement *pipeline, *sink;
	drmModePlaneRes *res;
	GError *error = NULL;
	int fd, bright = 0;

	gst_init(&argc, &argv);
	if (seconds <= 0) {
		fprintf(stderr, "usage: av-sync-probe SECONDS\n");
		return 2;
	}

	fd = open("/dev/dri/card0", O_RDWR | O_CLOEXEC);
	drmSetClientCap(fd, DRM_CLIENT_CAP_UNIVERSAL_PLANES, 1);
	res = fd >= 0 ? drmModeGetPlaneResources(fd) : NULL;
	if (!res) {
		perror("drm");
		return 1;
	}

	pipeline = gst_parse_launch(
		"pipewiresrc stream-properties=\"props,stream.capture.sink=true\" "
		"! audioconvert ! audio/x-raw,format=S16LE,channels=1,rate=48000 "
		"! appsink name=a sync=false", &error);
	if (!pipeline) {
		fprintf(stderr, "audio: %s\n", error->message);
		return 1;
	}
	sink = gst_bin_get_by_name(GST_BIN(pipeline), "a");
	gst_app_sink_set_callbacks(GST_APP_SINK(sink),
				   &(GstAppSinkCallbacks){ .new_sample = on_sample },
				   NULL, NULL);
	gst_element_set_state(pipeline, GST_STATE_PLAYING);

	t0 = now();
	end = t0 + seconds;
	while (now() < end) {
		uint32_t id = pick_fb(fd, res);
		struct fbmap *m = id ? fb_get(fd, id) : NULL;
		double t = now();

		if (m) {
			int v = patch(m);

			if (!bright && v > 128 && nflash < MAX_EVENTS)
				flashes[nflash++] = t;
			bright = v > 128 ? 1 : v < 64 ? 0 : bright;
		}
		if (t - last_alsa > 0.05) {
			long d = alsa_delay();

			if (d >= 0 && ndelay < (int)(sizeof(delays) / sizeof(*delays)))
				delays[ndelay++] = d;
			last_alsa = t;
		}
		usleep(1000);
	}
	gst_element_set_state(pipeline, GST_STATE_NULL);

	/* Beeps: onsets of the 1 ms envelope crossing half of its maximum,
	 * at least 0.5 s apart. */
	{
		double peak = 0, *env = calloc(pcm_len, sizeof(double)), acc = 0;
		long last = -RATE;
		long alsa = 0;

		for (size_t i = 0; i < pcm_len; i++) {
			acc += (double)pcm[i] * pcm[i];
			if (i >= 48)
				acc -= (double)pcm[i - 48] * pcm[i - 48];
			env[i] = sqrt(acc / 48);
			if (env[i] > peak)
				peak = env[i];
		}
		if (ndelay) {
			qsort(delays, ndelay, sizeof(long), cmp_long);
			alsa = delays[ndelay / 2];
		}
		for (size_t i = 1; i < pcm_len && nbeep < MAX_EVENTS; i++)
			if (env[i] > peak / 2 && env[i - 1] <= peak / 2 &&
			    (long)i - last > RATE / 2) {
				beeps[nbeep++] = env_offset + (double)i / RATE +
						 (double)alsa / RATE;
				last = i;
			}
		free(env);
		printf("audio: %zu samples, peak %.0f, ALSA delay median %ld frames "
		       "(%.1f ms, %d samples)\n", pcm_len, peak, alsa,
		       alsa * 1000.0 / RATE, ndelay);
	}

	printf("flashes %d, beeps %d\n", nflash, nbeep);

	/*
	 * Pair by the one offset that lines up the whole sequence, not each
	 * flash with its nearest beep: the clip's events are irregularly
	 * spaced, so only the true offset matches them all. Nearest-beep
	 * pairing on a periodic clip read audio 770 ms late as 230 ms early.
	 */
	{
		int best_n = 0;
		double best_d = 0;

		for (int ms = -3000; ms <= 3000; ms++) {
			double d = ms / 1000.0;
			int n = 0;

			for (int i = 0; i < nflash; i++)
				for (int j = 0; j < nbeep; j++)
					if (fabs(beeps[j] - flashes[i] - d) < 0.03) {
						n++;
						break;
					}
			if (n > best_n) {
				best_n = n;
				best_d = d;
			}
		}

		for (int i = 0; i < nflash; i++)
			for (int j = 0; j < nbeep; j++)
				if (fabs(beeps[j] - flashes[i] - best_d) < 0.03) {
					offs[noff++] = beeps[j] - flashes[i];
					printf("  flash %8.3f s  beep %+7.1f ms\n",
					       flashes[i] - t0,
					       (beeps[j] - flashes[i]) * 1000);
					break;
				}
	}
	if (noff) {
		qsort(offs, noff, sizeof(double), cmp_double);
		printf("A/V offset (beep - flash, + = audio late): median %+.1f ms, "
		       "min %+.1f, max %+.1f, n=%d of %d flashes\n",
		       offs[noff / 2] * 1000, offs[0] * 1000,
		       offs[noff - 1] * 1000, noff, nflash);
	} else {
		printf("A/V offset: no flash/beep pairs\n");
	}
	return noff ? 0 : 1;
}
