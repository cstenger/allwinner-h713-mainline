// SPDX-License-Identifier: GPL-2.0
/*
 * Minimal ALSA control list/set, over the raw ioctl interface.
 *
 * This image has no alsa-utils and no libasound headers, but it does ship
 * /usr/include/sound/asound.h from linux-libc-dev, which is all the control
 * interface actually needs. Written because audio bring-up stalled on not
 * being able to see, let alone change, a single mixer control.
 *
 *   alsa-ctl list                       show every control and its value
 *   alsa-ctl set "NAME" V [V2...]       set a control by name
 *
 * Why this matters here: sun4i-codec's card is fully_routed, and its DAC to
 * LINEOUT path runs through switches and an enum. If those default off the
 * path never completes, DAPM never powers the output, and the speaker amp's
 * event never fires -- which looks exactly like broken audio.
 */
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

#include <sound/asound.h>

static const char *type_name(int t)
{
	switch (t) {
	case SNDRV_CTL_ELEM_TYPE_BOOLEAN:    return "bool";
	case SNDRV_CTL_ELEM_TYPE_INTEGER:    return "int";
	case SNDRV_CTL_ELEM_TYPE_ENUMERATED: return "enum";
	case SNDRV_CTL_ELEM_TYPE_BYTES:      return "bytes";
	case SNDRV_CTL_ELEM_TYPE_INTEGER64:  return "int64";
	default:                             return "?";
	}
}

static void print_value(int fd, struct snd_ctl_elem_info *info)
{
	struct snd_ctl_elem_value val = {0};
	unsigned int i;

	val.id = info->id;
	if (ioctl(fd, SNDRV_CTL_IOCTL_ELEM_READ, &val) < 0) {
		printf(" <read failed>");
		return;
	}
	for (i = 0; i < info->count && i < 8; i++) {
		switch (info->type) {
		case SNDRV_CTL_ELEM_TYPE_BOOLEAN:
		case SNDRV_CTL_ELEM_TYPE_INTEGER:
			printf(" %ld", val.value.integer.value[i]);
			break;
		case SNDRV_CTL_ELEM_TYPE_ENUMERATED:
			printf(" %u", val.value.enumerated.item[i]);
			break;
		default:
			printf(" ?");
			break;
		}
	}
	if (info->type == SNDRV_CTL_ELEM_TYPE_INTEGER)
		printf("   [%ld..%ld]", info->value.integer.min,
		       info->value.integer.max);
	if (info->type == SNDRV_CTL_ELEM_TYPE_ENUMERATED)
		printf("   [0..%u]", info->value.enumerated.items - 1);
}

static int do_list(int fd)
{
	struct snd_ctl_elem_list list = {0};
	struct snd_ctl_elem_id *ids;
	unsigned int i;

	if (ioctl(fd, SNDRV_CTL_IOCTL_ELEM_LIST, &list) < 0) {
		perror("ELEM_LIST");
		return 1;
	}
	ids = calloc(list.count, sizeof(*ids));
	if (!ids)
		return 1;
	list.space = list.count;
	list.pids = ids;
	if (ioctl(fd, SNDRV_CTL_IOCTL_ELEM_LIST, &list) < 0) {
		perror("ELEM_LIST(2)");
		free(ids);
		return 1;
	}
	for (i = 0; i < list.used; i++) {
		struct snd_ctl_elem_info info = {0};

		info.id = ids[i];
		if (ioctl(fd, SNDRV_CTL_IOCTL_ELEM_INFO, &info) < 0)
			continue;
		printf("%-44s %-6s", (char *)info.id.name, type_name(info.type));
		print_value(fd, &info);
		printf("\n");
	}
	free(ids);
	return 0;
}

static int do_set(int fd, const char *name, int argc, char **argv)
{
	struct snd_ctl_elem_info info = {0};
	struct snd_ctl_elem_value val = {0};
	unsigned int i;

	info.id.iface = SNDRV_CTL_ELEM_IFACE_MIXER;
	snprintf((char *)info.id.name, sizeof(info.id.name), "%s", name);
	if (ioctl(fd, SNDRV_CTL_IOCTL_ELEM_INFO, &info) < 0) {
		perror(name);
		return 1;
	}

	val.id = info.id;
	/* Read first so unspecified channels keep their current value. */
	ioctl(fd, SNDRV_CTL_IOCTL_ELEM_READ, &val);
	for (i = 0; i < info.count; i++) {
		long v = strtol(argv[i < (unsigned int)argc ? i : argc - 1],
				NULL, 0);

		if (info.type == SNDRV_CTL_ELEM_TYPE_ENUMERATED)
			val.value.enumerated.item[i] = (unsigned int)v;
		else
			val.value.integer.value[i] = v;
	}
	if (ioctl(fd, SNDRV_CTL_IOCTL_ELEM_WRITE, &val) < 0) {
		perror("ELEM_WRITE");
		return 1;
	}
	printf("%-44s set to", name);
	print_value(fd, &info);
	printf("\n");
	return 0;
}

int main(int argc, char **argv)
{
	const char *dev = getenv("CTL") ?: "/dev/snd/controlC0";
	int fd, ret;

	if (argc < 2) {
		fprintf(stderr,
			"usage: alsa-ctl list | alsa-ctl set \"NAME\" V [V...]\n");
		return 2;
	}
	fd = open(dev, O_RDWR | O_CLOEXEC);
	if (fd < 0) {
		perror(dev);
		return 1;
	}
	if (!strcmp(argv[1], "list"))
		ret = do_list(fd);
	else if (!strcmp(argv[1], "set") && argc >= 4)
		ret = do_set(fd, argv[2], argc - 3, argv + 3);
	else {
		fprintf(stderr, "usage: alsa-ctl list | set \"NAME\" V [V...]\n");
		ret = 2;
	}
	close(fd);
	return ret;
}
