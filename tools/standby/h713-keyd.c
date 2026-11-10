/*
 * h713-keyd: run a command when the power key is pressed. RUNS ON THE TARGET.
 *
 * The case button (gpio-keys, PL4) and the IR remote (rc-hy200-projector)
 * both send KEY_POWER. This opens every input device that can send it --
 * chosen by capability, not by name -- and on each press runs
 *
 *     h713-standby toggle        (or argv[1], argv[2..] as its arguments)
 *
 * synchronously. Key-down only: auto-repeat (value 2) and key-up are
 * ignored, and so is anything that arrives while the command runs or within
 * HOLDOFF_MS after it, so one press is one toggle however long the remote
 * keeps repeating and whichever of the two sources it came from.
 *
 * Devices may come and go -- a USB keypad or GPIO board plugged in later is
 * picked up as soon as its /dev/input node appears (inotify), and a device
 * that goes away makes it reopen the rest.
 *
 * logind must not act on KEY_POWER (HandlePowerKey=ignore) or the board
 * powers off on the first press. docs/standby-plan.md.
 *
 *   gcc -O2 -Wall -o h713-keyd h713-keyd.c
 */
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/input.h>
#include <poll.h>
#include <stdio.h>
#include <string.h>
#include <sys/inotify.h>
#include <sys/ioctl.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#define MAX_DEVS	8
#define HOLDOFF_MS	600

static char *default_cmd[] = { "/usr/local/bin/h713-standby", "toggle", NULL };

static int has_power_key(int fd)
{
	unsigned long bits[KEY_MAX / (8 * sizeof(long)) + 1] = { 0 };

	if (ioctl(fd, EVIOCGBIT(EV_KEY, sizeof(bits)), bits) < 0)
		return 0;
	return (bits[KEY_POWER / (8 * sizeof(long))] >> (KEY_POWER % (8 * sizeof(long)))) & 1;
}

static int open_devices(struct pollfd *pfd)
{
	DIR *d = opendir("/dev/input");
	struct dirent *e;
	int n = 0;

	if (!d)
		return 0;
	while ((e = readdir(d)) && n < MAX_DEVS) {
		char path[sizeof(e->d_name) + 16], name[64] = "?";
		int fd;

		if (strncmp(e->d_name, "event", 5))
			continue;
		snprintf(path, sizeof(path), "/dev/input/%s", e->d_name);
		fd = open(path, O_RDONLY | O_NONBLOCK | O_CLOEXEC);
		if (fd < 0)
			continue;
		if (!has_power_key(fd)) {
			close(fd);
			continue;
		}
		ioctl(fd, EVIOCGNAME(sizeof(name)), name);
		fprintf(stderr, "h713-keyd: watching %s (%s)\n", path, name);
		pfd[n].fd = fd;
		pfd[n].events = POLLIN;
		n++;
	}
	closedir(d);
	return n;
}

static long long now_ms(void)
{
	struct timespec ts;

	clock_gettime(CLOCK_MONOTONIC, &ts);
	return ts.tv_sec * 1000LL + ts.tv_nsec / 1000000;
}

static void run(char **cmd)
{
	pid_t pid = fork();
	int status;

	if (pid == 0) {
		execv(cmd[0], cmd);
		perror(cmd[0]);
		_exit(127);
	}
	if (pid > 0 && waitpid(pid, &status, 0) > 0)
		fprintf(stderr, "h713-keyd: %s %s -> %d\n", cmd[0],
			cmd[1] ? cmd[1] : "", WIFEXITED(status) ? WEXITSTATUS(status) : -1);
}

int main(int argc, char **argv)
{
	char **cmd = argc > 1 ? argv + 1 : default_cmd;
	struct pollfd pfd[MAX_DEVS + 1];
	struct input_event ev[64];
	long long quiet_until = 0;
	int n, i, ino;

	/* /dev/input changes (hotplug) make us reopen everything. */
	ino = inotify_init1(IN_NONBLOCK | IN_CLOEXEC);
	if (ino < 0 || inotify_add_watch(ino, "/dev/input", IN_CREATE | IN_DELETE) < 0) {
		perror("h713-keyd: inotify /dev/input");
		return 1;
	}

	for (;;) {
		n = open_devices(pfd);
		pfd[n].fd = ino;	/* always last; poll() with no devices too */
		pfd[n].events = POLLIN;

		for (;;) {
			int fire = 0, reopen = 0;

			if (poll(pfd, n + 1, -1) < 0) {
				if (errno == EINTR)
					continue;
				break;
			}
			if (pfd[n].revents & POLLIN) {
				char buf[4096];

				while (read(ino, buf, sizeof(buf)) > 0)
					;
				usleep(200000);	/* let udev finish the node */
				reopen = 1;
			}
			for (i = 0; i < n; i++) {
				ssize_t r;

				if (pfd[i].revents & (POLLERR | POLLHUP | POLLNVAL)) {
					reopen = 1;
					continue;
				}
				if (!(pfd[i].revents & POLLIN))
					continue;
				while ((r = read(pfd[i].fd, ev, sizeof(ev))) > 0) {
					for (size_t k = 0; k < r / sizeof(ev[0]); k++)
						if (ev[k].type == EV_KEY && ev[k].code == KEY_POWER &&
						    ev[k].value == 1 && now_ms() >= quiet_until)
							fire = 1;
				}
				if (r < 0 && errno != EAGAIN)
					reopen = 1;
			}
			if (fire) {
				run(cmd);
				/* drop whatever queued up while it ran */
				for (i = 0; i < n; i++)
					while (read(pfd[i].fd, ev, sizeof(ev)) > 0)
						;
				quiet_until = now_ms() + HOLDOFF_MS;
			}
			if (reopen)
				break;
		}
		for (i = 0; i < n; i++)
			close(pfd[i].fd);
	}
}
