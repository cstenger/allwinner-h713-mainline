// SPDX-License-Identifier: GPL-2.0
/* Headless test adapter, NOT a playback interface.
 * cc -shared -fPIC -O2 -Wall -Wextra -Werror -o compose-probe.so cedrus-compose-probe.c -ldl
 * CEDRUS_COMPOSE=960x544 CEDRUS_DUMP=/tmp/scaled.nv12 LD_PRELOAD=./compose-probe.so \
 *   ffmpeg -hwaccel vaapi -hwaccel_output_format vaapi -i clip.mp4 -frames:v 60 -f null -
 * Do not hwdownload or display these VA surfaces: VA still describes coded size.
 * Injects COMPOSE before capture allocation and dumps one completed buffer.
 * CEDRUS_DUMP_ONLY captures the unchanged coded output without sizing ioctls.
 * CEDRUS_DUMP_AT selects its one-based completion number (default 1).
 * CEDRUS_DUMP_FULL writes the whole allocated buffer instead of sizeimage as it
 * stood at the app's G_FMT. Main10 needs this: bit_depth is only known once the
 * SPS control arrives, so a G_FMT taken earlier reports the 8-bit size and the
 * 2-bit side plane past it is never written out.
 * CEDRUS_CANVAS optionally requests a larger capture allocation (for example
 * 1280x720) while COMPOSE remains the smaller active picture.
 * CEDRUS_STRIDE optionally requests a larger aligned capture pitch.
 * CEDRUS_CAPTURE_SIZE selects output dimensions through CAPTURE S_FMT instead
 * of COMPOSE. Use it alone to test the standard sizing interface.
 * CEDRUS_CROP=WxH narrows what the scaler reads, via S_SELECTION(CROP).
 * CEDRUS_ROTATE retains the legacy control probe for negative testing.
 * The current driver rejects it because rotation is no longer exposed.
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

/*
 * CEDRUS_CROP=WxH narrows what the scaler READS out of the coded frame, via
 * S_SELECTION(CAPTURE, V4L2_SEL_TGT_CROP). Use it to exclude coded padding:
 * H.264 stores 1080p as 1088 rows, so CEDRUS_CROP=1920x1080 stops the eight
 * rows of encoder padding being scaled into the picture.
 *
 * Applied immediately after the OUTPUT format is set, because the crop is
 * bounded by the coded size and re-derives the compose rectangle -- so it has
 * to land before the capture size is negotiated.
 */
static int configure_crop(int fd)
{
    const char *value = getenv("CEDRUS_CROP");
    struct v4l2_selection sel = {
        .type = V4L2_BUF_TYPE_VIDEO_CAPTURE,
        .target = V4L2_SEL_TGT_CROP,
    };
    unsigned int w, h;
    char extra;

    if (!value)
        return 0;
    if (sscanf(value, "%ux%u%c", &w, &h, &extra) != 2 || !w || !h) {
        errno = EINVAL;
        return -1;
    }
    sel.r.width = w;
    sel.r.height = h;
    if (real_ioctl(fd, VIDIOC_S_SELECTION, &sel) < 0)
        return -1;
    fprintf(stderr, "compose-probe: crop -> %ux%u\n", sel.r.width, sel.r.height);
    return 0;
}

static int configure_capture(int fd)
{
    unsigned int w, h;
    const char *size = getenv("CEDRUS_CAPTURE_SIZE");
    int use_format = size != NULL;
    char extra;
    struct v4l2_selection sel = {
        .type = V4L2_BUF_TYPE_VIDEO_CAPTURE,
        .target = V4L2_SEL_TGT_COMPOSE,
    };
    struct v4l2_format fmt = {
        .type = V4L2_BUF_TYPE_VIDEO_CAPTURE,
    };

    if (!size && !getenv("CEDRUS_COMPOSE")) {
        if (real_ioctl(fd, VIDIOC_G_FMT, &fmt) < 0)
            return -1;
        sel.r.width = fmt.fmt.pix.width;
        sel.r.height = fmt.fmt.pix.height;
        goto record;
    }

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

    if (!size) size = getenv("CEDRUS_COMPOSE");
    if (sscanf(size, "%ux%u%c", &w, &h, &extra) != 2 ||
        !w || !h) {
        errno = EINVAL;
        return -1;
    }
    sel.r.width = w;
    sel.r.height = h;
    if (real_ioctl(fd, VIDIOC_G_FMT, &fmt) < 0)
        return -1;
    if (use_format) {
        if (getenv("CEDRUS_CANVAS")) {
            errno = EINVAL;
            return -1;
        }
        fmt.fmt.pix.width = w;
        fmt.fmt.pix.height = h;
        fmt.fmt.pix.bytesperline = 0;
        fmt.fmt.pix.sizeimage = 0;
        fmt.fmt.pix.pixelformat = V4L2_PIX_FMT_NV12;
    }
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
    if ((use_format || getenv("CEDRUS_CANVAS") || getenv("CEDRUS_STRIDE")) &&
        real_ioctl(fd, VIDIOC_S_FMT, &fmt) < 0)
        return -1;
    if (!use_format && real_ioctl(fd, VIDIOC_S_SELECTION, &sel) < 0)
        return -1;
    if (real_ioctl(fd, VIDIOC_G_FMT, &fmt) < 0 ||
        real_ioctl(fd, VIDIOC_G_SELECTION, &sel) < 0)
        return -1;
record:
    capture = fmt.fmt.pix;
    fprintf(stderr, "compose-probe: %ux%u stride=%u bytes=%u format=%c%c%c%c active=%dx%d\n",
            capture.width, capture.height, capture.bytesperline,
            capture.sizeimage, capture.pixelformat & 255,
            (capture.pixelformat >> 8) & 255,
            (capture.pixelformat >> 16) & 255,
            capture.pixelformat >> 24, sel.r.width, sel.r.height);
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
    if (rc < 0 || (!getenv("CEDRUS_COMPOSE") && !getenv("CEDRUS_CAPTURE_SIZE") &&
                   !getenv("CEDRUS_CROP") && !getenv("CEDRUS_DUMP_ONLY")))
        return rc;
    if (req == VIDIOC_S_FMT && arg) {
        struct v4l2_format *fmt = arg;
        if (fmt->type == V4L2_BUF_TYPE_VIDEO_OUTPUT) {
            /* Both engines can feed the polyphase scaler. */
            decoder = (fmt->fmt.pix.pixelformat == V4L2_PIX_FMT_H264_SLICE ||
                       fmt->fmt.pix.pixelformat == V4L2_PIX_FMT_HEVC_SLICE)
                      ? fd : -1;
            dumped = 0;
            completed = 0;
            if (decoder >= 0 && (configure_crop(fd) < 0 ||
                                 configure_capture(fd) < 0))
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
            size_t want = getenv("CEDRUS_DUMP_FULL") ? buf.length : capture.sizeimage;
            out = fopen(getenv("CEDRUS_DUMP"), "wb");
            int failed = !out;
            if (out) {
                failed = fwrite(map, 1, want, out) != want;
                if (fclose(out)) failed = 1;
            }
            munmap(map, buf.length);
            if (failed) { errno = EIO; return -1; }
            fprintf(stderr, "compose-probe: saved capture %u (%zu bytes, allocated %u)\n",
                    completed, want, buf.length);
            dumped = 1;
        }
    }
    return rc;
}
