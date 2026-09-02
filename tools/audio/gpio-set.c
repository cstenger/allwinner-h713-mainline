// SPDX-License-Identifier: GPL-2.0
/*
 * Hold a GPIO line at a value for as long as this process runs.
 *
 * Needed because this image has neither the deprecated /sys/class/gpio nor
 * libgpiod's gpioset, and the speaker amp enable has to be asserted before
 * anything can be heard.
 *
 * The line is released when the process exits -- that is the point. A gpio-hog
 * in the device tree would assert it permanently from boot, which is wrong for
 * an amp: the vendor drives this pin around playback with a settle delay, and
 * leaving an amplifier enabled into an idle DAC is how you get hiss and pops.
 *
 *   gpio-set /dev/gpiochip1 2 1 [hold-seconds]
 *
 * On this board the speaker amp is PL2 = gpiochip1 (7022000.pinctrl, r_pio)
 * line 2, active high, and the vendor waits 160 ms after asserting it before
 * starting audio (pa_msleep_time = 0xa0).
 *
 * CAUTION: confirm a pin has no shared duty before holding it. PB5 on this
 * board is the backlight AND fan enable, and holding it low stops the fan --
 * see docs/backlight-investigation.md. PL2's other duties, if any, are unknown.
 */
#include <fcntl.h>
#include <linux/gpio.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

int main(int argc, char **argv)
{
	struct gpio_v2_line_request req = {0};
	unsigned int line, value, hold = 0;
	struct gpio_v2_line_values vals;
	int fd;

	if (argc < 4 || argc > 5) {
		fprintf(stderr,
			"usage: gpio-set /dev/gpiochipN LINE VALUE [hold-seconds]\n");
		return 2;
	}
	line = (unsigned int)strtoul(argv[2], NULL, 0);
	value = (unsigned int)strtoul(argv[3], NULL, 0);
	if (argc == 5)
		hold = (unsigned int)strtoul(argv[4], NULL, 0);

	fd = open(argv[1], O_RDWR | O_CLOEXEC);
	if (fd < 0) {
		perror(argv[1]);
		return 1;
	}

	req.offsets[0] = line;
	req.num_lines = 1;
	req.config.flags = GPIO_V2_LINE_FLAG_OUTPUT;
	req.config.num_attrs = 1;
	req.config.attrs[0].attr.id = GPIO_V2_LINE_ATTR_ID_OUTPUT_VALUES;
	req.config.attrs[0].attr.values = value ? 1 : 0;
	req.config.attrs[0].mask = 1;
	snprintf(req.consumer, sizeof(req.consumer), "h713-amp");

	if (ioctl(fd, GPIO_V2_GET_LINE_IOCTL, &req) < 0) {
		perror("GPIO_V2_GET_LINE_IOCTL");
		close(fd);
		return 1;
	}

	memset(&vals, 0, sizeof(vals));
	vals.mask = 1;
	if (ioctl(req.fd, GPIO_V2_LINE_GET_VALUES_IOCTL, &vals) == 0)
		printf("line %u held at %llu\n", line,
		       (unsigned long long)(vals.bits & 1));
	else
		printf("line %u requested (readback unavailable)\n", line);

	if (hold) {
		sleep(hold);
	} else {
		printf("holding until killed; press enter to release\n");
		getchar();
	}

	close(req.fd);
	close(fd);
	return 0;
}
