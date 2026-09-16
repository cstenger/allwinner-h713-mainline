// SPDX-License-Identifier: GPL-2.0
/* Headless test adapter, NOT a playback interface.
 * cc -shared -fPIC -O2 -Wall -Wextra -Werror -o compose-probe.so cedrus-compose-probe.c -ldl
 * CEDRUS_COMPOSE=960x544 CEDRUS_DUMP=/tmp/scaled.nv12 LD_PRELOAD=./compose-probe.so \
 *   ffmpeg -hwaccel vaapi -hwaccel_output_format vaapi -i clip.mp4 -frames:v 60 -f null -
 * Do not hwdownload or display these VA surfaces: VA still describes coded size.
 * Injects COMPOSE before capture allocation and dumps one completed buffer.
 * CEDRUS_DUMP_AT selects its one-based completion number (default 1).
 * CEDRUS_CANVAS optionally requests a larger capture allocation (for example
 * 1280x720) while COMPOSE remains the smaller active picture.
 * CEDRUS_STRIDE optionally requests a larger aligned capture pitch.
 * CEDRUS_ROTATE optionally sets clockwise rotation (0, 90, 180 or 270) before
 * COMPOSE.  The requested compose dimensions are in the final orientation.
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <linux/videodev2.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>

static int (*real_ioctl)(int, unsigned long, ...);
static int decoder = -1, dumped;
static unsigned int completed;
static struct v4l2_pix_format capture;

static int configure_capture(int fd)
{
    unsigned int w, h;
    char extra;
    struct v4l2_selection sel = {
        .type = V4L2_BUF_TYPE_VIDEO_CAPTURE,
        .target = V4L2_SEL_TGT_COMPOSE,
    };
    struct v4l2_format fmt = {
        .type = V4L2_BUF_TYPE_VIDEO_CAPTURE,
    };

    if (getenv("CEDRUS_ROTATE")) {
        char *end = NULL;
        unsigned long rotation;
        struct v4l2_control ctrl = {.id = V4L2_CID_ROTATE};

        errno = 0;
        rotation = strtoul(getenv("CEDRUS_ROTATE"), &end, 0);
        if (errno || *end || rotation > 270 || rotation % 90) {
            errno = EINVAL;
            return -1;
        }
        ctrl.value = rotation;
        if (real_ioctl(fd, VIDIOC_S_CTRL, &ctrl) < 0)
            return -1;
    }

    if (sscanf(getenv("CEDRUS_COMPOSE"), "%ux%u%c", &w, &h, &extra) != 2 ||
        !w || !h) {
        errno = EINVAL;
        return -1;
    }
    sel.r.width = w;
    sel.r.height = h;
    if (real_ioctl(fd, VIDIOC_S_SELECTION, &sel) < 0 ||
        real_ioctl(fd, VIDIOC_G_FMT, &fmt) < 0)
        return -1;
    if (getenv("CEDRUS_CANVAS")) {
        unsigned int canvas_w, canvas_h;

        if (sscanf(getenv("CEDRUS_CANVAS"), "%ux%u%c",
                   &canvas_w, &canvas_h, &extra) != 2 ||
            !canvas_w || !canvas_h) {
            errno = EINVAL;
            return -1;
        }
        fmt.fmt.pix.width = canvas_w;
        fmt.fmt.pix.height = canvas_h;
        fmt.fmt.pix.sizeimage = 0;
    }
    if (getenv("CEDRUS_STRIDE")) {
        char *end = NULL;
        unsigned long stride;

        errno = 0;
        stride = strtoul(getenv("CEDRUS_STRIDE"), &end, 0);
        if (errno || !stride || *end || stride > UINT_MAX) {
            errno = EINVAL;
            return -1;
        }
        fmt.fmt.pix.bytesperline = stride;
        fmt.fmt.pix.sizeimage = 0;
    }
    if ((getenv("CEDRUS_CANVAS") || getenv("CEDRUS_STRIDE")) &&
        real_ioctl(fd, VIDIOC_S_FMT, &fmt) < 0)
        return -1;
    capture = fmt.fmt.pix;
    fprintf(stderr, "compose-probe: %ux%u stride=%u bytes=%u format=%c%c%c%c\n",
            capture.width, capture.height, capture.bytesperline,
            capture.sizeimage, capture.pixelformat & 255,
            (capture.pixelformat >> 8) & 255,
            (capture.pixelformat >> 16) & 255,
            capture.pixelformat >> 24);
    if (capture.pixelformat != V4L2_PIX_FMT_NV12) {
        errno = EINVAL;
        return -1;
    }
    return 0;
}

int ioctl(int fd, unsigned long req, ...)
{
    va_list ap;
    void *arg = NULL;
    int rc;
    if (!real_ioctl)
        real_ioctl = dlsym(RTLD_NEXT, "ioctl");
    if (_IOC_DIR(req) || _IOC_SIZE(req)) {
        va_start(ap, req);
        arg = va_arg(ap, void *);
        va_end(ap);
    }
    if (req == VIDIOC_S_FMT && arg && getenv("CEDRUS_TRACE")) {
        const struct v4l2_format *fmt = arg;

        fprintf(stderr,
                "compose-probe: S_FMT fd=%d type=%u %ux%u format=%c%c%c%c\n",
                fd, fmt->type, fmt->fmt.pix.width, fmt->fmt.pix.height,
                fmt->fmt.pix.pixelformat & 255,
                (fmt->fmt.pix.pixelformat >> 8) & 255,
                (fmt->fmt.pix.pixelformat >> 16) & 255,
                fmt->fmt.pix.pixelformat >> 24);
    }
    rc = real_ioctl(fd, req, arg);
    if (rc < 0 || !getenv("CEDRUS_COMPOSE"))
        return rc;
    if (req == VIDIOC_S_FMT && arg) {
        struct v4l2_format *fmt = arg;
        if (fmt->type == V4L2_BUF_TYPE_VIDEO_OUTPUT) {
            /* Both engines carry a scale/rotate secondary output. */
            decoder = (fmt->fmt.pix.pixelformat == V4L2_PIX_FMT_H264_SLICE ||
                       fmt->fmt.pix.pixelformat == V4L2_PIX_FMT_HEVC_SLICE)
                      ? fd : -1;
            dumped = 0;
            completed = 0;
            if (decoder >= 0 && configure_capture(fd) < 0)
                return -1;
        }
        if (fd == decoder && fmt->type == V4L2_BUF_TYPE_VIDEO_CAPTURE) {
            if (configure_capture(fd) < 0 || real_ioctl(fd, VIDIOC_G_FMT, fmt) < 0)
                return -1;
        }
    }
    if (req == VIDIOC_DQBUF && fd == decoder && arg && !dumped && getenv("CEDRUS_DUMP")) {
        struct v4l2_buffer *done = arg;
        if (done->type == V4L2_BUF_TYPE_VIDEO_CAPTURE) {
            const char *dump_at_env = getenv("CEDRUS_DUMP_AT");
            char *end = NULL;
            unsigned long dump_at = 1;
            struct v4l2_buffer buf = {.type = done->type, .memory = V4L2_MEMORY_MMAP, .index = done->index};
            void *map;
            FILE *out;

            completed++;
            if (dump_at_env) {
                errno = 0;
                dump_at = strtoul(dump_at_env, &end, 0);
                if (errno || !dump_at || *end || dump_at > UINT_MAX) {
                    fprintf(stderr, "compose-probe: invalid CEDRUS_DUMP_AT\n");
                    errno = EINVAL;
                    return -1;
                }
            }
            if (completed != dump_at)
                return rc;
            if (done->flags & V4L2_BUF_FLAG_ERROR || real_ioctl(fd, VIDIOC_QUERYBUF, &buf) < 0 ||
                buf.length < capture.sizeimage) {
                fprintf(stderr, "compose-probe: invalid completed buffer\n");
                errno = EIO;
                return -1;
            }
            map = mmap(NULL, buf.length, PROT_READ, MAP_SHARED, fd, buf.m.offset);
            if (map == MAP_FAILED)
                return -1;
            out = fopen(getenv("CEDRUS_DUMP"), "wb");
            int failed = !out;
            if (out) {
                failed = fwrite(map, 1, capture.sizeimage, out) != capture.sizeimage;
                if (fclose(out)) failed = 1;
            }
            munmap(map, buf.length);
            if (failed) { errno = EIO; return -1; }
            fprintf(stderr, "compose-probe: saved capture %u (%u bytes)\n",
                    completed, capture.sizeimage);
            dumped = 1;
        }
    }
    return rc;
}
