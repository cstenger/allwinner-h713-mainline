// SPDX-License-Identifier: GPL-2.0
/* Run on the board. Checks SPS defaults, pure TRY, and Main10 allocation guards. */
#include <errno.h>
#include <fcntl.h>
#include <linux/videodev2.h>
#include <linux/v4l2-controls.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

#define CHECK(e) do { if (!(e)) { \
    fprintf(stderr, "FAIL line %d: %s (errno=%d %s)\n", __LINE__, #e, errno, strerror(errno)); \
    exit(1); } } while (0)

static int sps_ioctl(int fd, unsigned long request, struct v4l2_ctrl_hevc_sps *sps)
{
    struct v4l2_ext_control c = {
        .id = V4L2_CID_STATELESS_HEVC_SPS, .size = sizeof(*sps), .ptr = sps,
    };
    struct v4l2_ext_controls cs = {.count = 1, .controls = &c};
    return ioctl(fd, request, &cs);
}

static struct v4l2_pix_format format(int fd)
{
    struct v4l2_format f = {.type = V4L2_BUF_TYPE_VIDEO_CAPTURE};
    CHECK(ioctl(fd, VIDIOC_G_FMT, &f) == 0);
    return f.fmt.pix;
}

int main(int argc, char **argv)
{
    int fd = open(argc > 1 ? argv[1] : "/dev/video0", O_RDWR | O_CLOEXEC);
    struct v4l2_ctrl_hevc_sps sps, current;
    struct v4l2_format f = {.type = V4L2_BUF_TYPE_VIDEO_OUTPUT};
    struct v4l2_pix_format before, after;
    struct v4l2_requestbuffers buffers = {
        .type = V4L2_BUF_TYPE_VIDEO_CAPTURE, .memory = V4L2_MEMORY_MMAP, .count = 2,
    };
    CHECK(fd >= 0);
    memset(&sps, 0, sizeof(sps));
    CHECK(sps_ioctl(fd, VIDIOC_G_EXT_CTRLS, &sps) == 0);
    printf("HEVC default chroma_format_idc=%u depth=%u/%u\n", sps.chroma_format_idc,
           sps.bit_depth_luma_minus8 + 8, sps.bit_depth_chroma_minus8 + 8);
    CHECK(sps_ioctl(fd, VIDIOC_TRY_EXT_CTRLS, &sps) == 0);
    CHECK(sps_ioctl(fd, VIDIOC_S_EXT_CTRLS, &sps) == 0);
    CHECK(sps.chroma_format_idc == 1);

    f.fmt.pix.pixelformat = V4L2_PIX_FMT_HEVC_SLICE;
    f.fmt.pix.width = 640;
    f.fmt.pix.height = 480;
    f.fmt.pix.sizeimage = 1024 * 1024;
    CHECK(ioctl(fd, VIDIOC_S_FMT, &f) == 0);
    f.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    f.fmt.pix.pixelformat = V4L2_PIX_FMT_NV12;
    f.fmt.pix.width = 258;
    f.fmt.pix.height = 242;
    f.fmt.pix.bytesperline = 0;
    CHECK(ioctl(fd, VIDIOC_S_FMT, &f) == 0);
    before = format(fd);
    sps.bit_depth_luma_minus8 = sps.bit_depth_chroma_minus8 = 2;
    CHECK(sps_ioctl(fd, VIDIOC_TRY_EXT_CTRLS, &sps) == 0);
    after = format(fd);
    CHECK(memcmp(&before, &after, sizeof(before)) == 0);
    CHECK(sps_ioctl(fd, VIDIOC_G_EXT_CTRLS, &current) == 0);
    CHECK(current.bit_depth_luma_minus8 == 0 && current.bit_depth_chroma_minus8 == 0);

    /* Allocating after TRY must still allocate the original 8-bit format. */
    CHECK(ioctl(fd, VIDIOC_REQBUFS, &buffers) == 0 && buffers.count >= 2);
    CHECK(sps_ioctl(fd, VIDIOC_S_EXT_CTRLS, &sps) == -1 && errno == EINVAL);
    after = format(fd);
    CHECK(memcmp(&before, &after, sizeof(before)) == 0);
    buffers.count = 0;
    CHECK(ioctl(fd, VIDIOC_REQBUFS, &buffers) == 0);
    CHECK(sps_ioctl(fd, VIDIOC_S_EXT_CTRLS, &sps) == 0);
    after = format(fd);
    CHECK(after.sizeimage == before.sizeimage + 96 * 242 * 3 / 2);
    CHECK(after.width == 258 && after.height == 242 && after.bytesperline == 288);

    sps.chroma_format_idc = 0;
    CHECK(sps_ioctl(fd, VIDIOC_TRY_EXT_CTRLS, &sps) == -1 && errno == EINVAL);
    sps.chroma_format_idc = 1;
    sps.bit_depth_luma_minus8 = sps.bit_depth_chroma_minus8 = 4;
    CHECK(sps_ioctl(fd, VIDIOC_TRY_EXT_CTRLS, &sps) == -1 && errno == EINVAL);
    before = format(fd);
    CHECK(memcmp(&before, &after, sizeof(before)) == 0);
    CHECK(close(fd) == 0);
    puts("PASS: supported SPS defaults, pure TRY, Main10 commit, busy guards, invalid SPS rejection");
    return 0;
}
