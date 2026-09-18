// Does the OUTPUT queue offer M2M_HOLD_CAPTURE_BUF for a given coded format?
// Field-picture MPEG-2 needs it: two coded fields must land in ONE capture
// buffer, which means holding that buffer across the first field's job.
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <linux/videodev2.h>

int main(int argc, char **argv)
{
	int fd = open(argv[1], O_RDWR);
	for (int i = 2; i < argc; i++) {
		struct v4l2_format f = {.type = V4L2_BUF_TYPE_VIDEO_OUTPUT};
		struct v4l2_requestbuffers rb = {
			.type = V4L2_BUF_TYPE_VIDEO_OUTPUT,
			.memory = V4L2_MEMORY_MMAP, .count = 0,
		};
		unsigned int fourcc;
		memcpy(&fourcc, argv[i], 4);
		f.fmt.pix.width = 720; f.fmt.pix.height = 576;
		f.fmt.pix.pixelformat = fourcc;
		f.fmt.pix.sizeimage = 1 << 20;
		if (ioctl(fd, VIDIOC_S_FMT, &f) < 0) { perror("S_FMT"); continue; }
		if (ioctl(fd, VIDIOC_REQBUFS, &rb) < 0) { perror("REQBUFS"); continue; }
		printf("%.4s: caps=0x%08x  M2M_HOLD_CAPTURE_BUF=%s\n", argv[i],
		       rb.capabilities,
		       rb.capabilities & V4L2_BUF_CAP_SUPPORTS_M2M_HOLD_CAPTURE_BUF
		           ? "YES" : "no");
	}
	return 0;
}
