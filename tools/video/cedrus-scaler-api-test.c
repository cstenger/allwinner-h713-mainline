// SPDX-License-Identifier: GPL-2.0
/* RUN ON THE BOARD: cc -O2 -Wall -Wextra -Werror -o scaler-api-test cedrus-scaler-api-test.c
 * Exercises sizing negotiation, state isolation, and allocation-time guards.
 * Pixel correctness is covered separately by cedrus-scaler-check.py.
 */
#include <errno.h>
#include <fcntl.h>
#include <linux/videodev2.h>
#include <linux/v4l2-controls.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

#define CHECK(expr) do { if (!(expr)) { \
    fprintf(stderr, "FAIL line %d: %s (errno=%d %s)\n", __LINE__, #expr, errno, strerror(errno)); \
    exit(1); } } while (0)

static struct v4l2_format capture(unsigned int w, unsigned int h)
{
    struct v4l2_format f = {.type = V4L2_BUF_TYPE_VIDEO_CAPTURE};
    f.fmt.pix.width = w;
    f.fmt.pix.height = h;
    f.fmt.pix.pixelformat = V4L2_PIX_FMT_NV12;
    return f;
}

static struct v4l2_selection compose(int w, int h, unsigned int flags)
{
    struct v4l2_selection s = {
        .type = V4L2_BUF_TYPE_VIDEO_CAPTURE,
        .target = V4L2_SEL_TGT_COMPOSE,
        .flags = flags,
        .r = {.width = w, .height = h},
    };
    return s;
}

static void active(int fd, unsigned int w, unsigned int h)
{
    struct v4l2_selection s = compose(0, 0, 0);
    CHECK(ioctl(fd, VIDIOC_G_SELECTION, &s) == 0);
    CHECK(s.r.width == w && s.r.height == h && !s.r.left && !s.r.top);
}

static void codec(int fd, unsigned int fourcc, unsigned int w, unsigned int h)
{
    struct v4l2_format f = {.type = V4L2_BUF_TYPE_VIDEO_OUTPUT};
    f.fmt.pix.pixelformat = fourcc;
    f.fmt.pix.width = w;
    f.fmt.pix.height = h;
    f.fmt.pix.sizeimage = 1024 * 1024;
    CHECK(ioctl(fd, VIDIOC_S_FMT, &f) == 0);
    CHECK(f.fmt.pix.pixelformat == fourcc && f.fmt.pix.width == w && f.fmt.pix.height == h);
}

static void exercise(int fd, unsigned int fourcc)
{
    struct v4l2_format f;
    struct v4l2_selection s;
    struct v4l2_frmsizeenum e = {.pixel_format = V4L2_PIX_FMT_NV12};
    struct v4l2_requestbuffers buffers = {
        .type = V4L2_BUF_TYPE_VIDEO_CAPTURE,
        .memory = V4L2_MEMORY_MMAP,
        .count = 2,
    };

    codec(fd, fourcc, 1920, 1080);
    active(fd, 1920, 1080);
    CHECK(ioctl(fd, VIDIOC_ENUM_FRAMESIZES, &e) == 0);
    CHECK(e.type == V4L2_FRMSIZE_TYPE_STEPWISE);
    CHECK(e.stepwise.min_width == 480 && e.stepwise.min_height == 270);
    CHECK(e.stepwise.step_width == 2 && e.stepwise.step_height == 2);
    e.index = 1;
    CHECK(ioctl(fd, VIDIOC_ENUM_FRAMESIZES, &e) == -1 && errno == EINVAL);

    f = capture(1280, 720);
    CHECK(ioctl(fd, VIDIOC_S_FMT, &f) == 0);
    CHECK(f.fmt.pix.width == 1280 && f.fmt.pix.height == 720);
    active(fd, 1280, 720);
    f = capture(640, 360);
    CHECK(ioctl(fd, VIDIOC_TRY_FMT, &f) == 0);
    CHECK(f.fmt.pix.width == 640 && f.fmt.pix.height == 360);
    active(fd, 1280, 720); /* TRY_FMT must leave actual output unchanged. */

    s = compose(853, 479, V4L2_SEL_FLAG_LE);
    CHECK(ioctl(fd, VIDIOC_S_SELECTION, &s) == 0);
    CHECK(s.r.width == 852 && s.r.height == 478);
    s = compose(853, 479, V4L2_SEL_FLAG_GE);
    CHECK(ioctl(fd, VIDIOC_S_SELECTION, &s) == 0);
    CHECK(s.r.width == 854 && s.r.height == 480);
    s = compose(853, 479, V4L2_SEL_FLAG_LE | V4L2_SEL_FLAG_GE);
    CHECK(ioctl(fd, VIDIOC_S_SELECTION, &s) == -1 && errno == ERANGE);
    active(fd, 854, 480);
    s = compose(478, 268, V4L2_SEL_FLAG_LE);
    CHECK(ioctl(fd, VIDIOC_S_SELECTION, &s) == -1 && errno == ERANGE);
    active(fd, 854, 480);
    s = compose(-1, 480, 0);
    CHECK(ioctl(fd, VIDIOC_S_SELECTION, &s) == -1 && errno == EINVAL);
    s = compose(640, 360, 0x80000000);
    CHECK(ioctl(fd, VIDIOC_S_SELECTION, &s) == -1 && errno == EINVAL);
    s = compose(640, 360, 0);
    s.r.left = 2;
    CHECK(ioctl(fd, VIDIOC_S_SELECTION, &s) == -1 && errno == EINVAL);
    active(fd, 854, 480);

    f = capture(640, 360);
    f.fmt.pix.bytesperline = 1280;
    CHECK(ioctl(fd, VIDIOC_S_FMT, &f) == 0);
    CHECK(f.fmt.pix.bytesperline == 1280);
    active(fd, 640, 360);
    s = compose(480, 270, 0);
    CHECK(ioctl(fd, VIDIOC_S_SELECTION, &s) == 0);
    f = capture(0, 0);
    CHECK(ioctl(fd, VIDIOC_G_FMT, &f) == 0);
    CHECK(f.fmt.pix.width == 640 && f.fmt.pix.height == 360);
    CHECK(f.fmt.pix.bytesperline == 1280); /* COMPOSE preserves the canvas pitch. */

    CHECK(ioctl(fd, VIDIOC_REQBUFS, &buffers) == 0 && buffers.count >= 2);
    f = capture(1280, 720);
    CHECK(ioctl(fd, VIDIOC_S_FMT, &f) == -1 && errno == EBUSY);
    s = compose(1280, 720, 0);
    CHECK(ioctl(fd, VIDIOC_S_SELECTION, &s) == -1 && errno == EBUSY);
    active(fd, 480, 270);
    buffers.count = 0;
    CHECK(ioctl(fd, VIDIOC_REQBUFS, &buffers) == 0);

    codec(fd, fourcc, 640, 480);
    active(fd, 640, 480); /* OUTPUT sizing discards the old scale geometry. */
    f = capture(320, 240);
    f.fmt.pix.pixelformat = V4L2_PIX_FMT_NV21;
    CHECK(ioctl(fd, VIDIOC_S_FMT, &f) == 0);
    CHECK(f.fmt.pix.pixelformat == V4L2_PIX_FMT_NV21);
    CHECK(f.fmt.pix.width == 640 && f.fmt.pix.height == 480);
    active(fd, 640, 480); /* Secondary scaling is offered for NV12 only. */
}

static void main10(int fd)
{
    struct v4l2_ctrl_hevc_sps sps = {
        .chroma_format_idc = 1,
        .bit_depth_luma_minus8 = 2,
        .bit_depth_chroma_minus8 = 2,
    };
    struct v4l2_ext_control control = {
        .id = V4L2_CID_STATELESS_HEVC_SPS,
        .size = sizeof(sps),
        .ptr = &sps,
    };
    struct v4l2_ext_controls controls = {.count = 1, .controls = &control};
    struct v4l2_format f = capture(258, 242);
    unsigned int eight_bit_size;

    codec(fd, V4L2_PIX_FMT_HEVC_SLICE, 640, 480);
    CHECK(ioctl(fd, VIDIOC_S_FMT, &f) == 0);
    CHECK(f.fmt.pix.bytesperline == 288 && f.fmt.pix.height == 242);
    eight_bit_size = f.fmt.pix.sizeimage;
    CHECK(ioctl(fd, VIDIOC_S_EXT_CTRLS, &controls) == 0);
    CHECK(ioctl(fd, VIDIOC_G_FMT, &f) == 0);
    CHECK(f.fmt.pix.width == 258 && f.fmt.pix.height == 242);
    CHECK(f.fmt.pix.sizeimage == eight_bit_size + 96 * 242 * 3 / 2);
    active(fd, 258, 242);
}

int main(int argc, char **argv)
{
    int fd = open(argc > 1 ? argv[1] : "/dev/video0", O_RDWR | O_CLOEXEC);
    struct v4l2_queryctrl rotate = {.id = V4L2_CID_ROTATE};
    struct v4l2_selection s;
    struct v4l2_format f;
    CHECK(fd >= 0);
    CHECK(ioctl(fd, VIDIOC_QUERYCTRL, &rotate) == -1 && errno == EINVAL);
    exercise(fd, V4L2_PIX_FMT_H264_SLICE);
    exercise(fd, V4L2_PIX_FMT_HEVC_SLICE);
    codec(fd, V4L2_PIX_FMT_MPEG2_SLICE, 720, 576);
    s = compose(360, 288, 0);
    CHECK(ioctl(fd, VIDIOC_S_SELECTION, &s) == -1 && errno == EINVAL);
    f = capture(360, 288);
    CHECK(ioctl(fd, VIDIOC_S_FMT, &f) == 0);
    CHECK(f.fmt.pix.width == 720 && f.fmt.pix.height == 576);
    main10(fd);
    CHECK(close(fd) == 0);
    puts("PASS: sizing, TRY_FMT isolation, compose constraints, pitch, busy guards, codec reset, no rotation");
    return 0;
}
