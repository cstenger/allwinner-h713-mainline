// SPDX-License-Identifier: GPL-2.0-or-later
/*
 * Guarded userspace client for the H713 CPU_COMM routine interface.
 *
 * Names are resolved from the live firmware table. Raw component IDs are
 * accepted only with --id, and routines known to wedge the SoC are refused.
 */

#define _GNU_SOURCE

#include <ctype.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

#define CPU_COMM_IOCTL_CALL 0xC0087F26UL
#define CPU_COMM_ROUTINES_PATH "/proc/cpu_comm/routines"
#define CALL_BUFFER_SIZE 168U
#define COMPONENT_ID_OFFSET 40U
#define PARAMS_OFFSET 64U
#define RESULTS_OFFSET 120U
#define MAX_VALUES 10U

/* THal_Vp_EnableScreenCover: confirmed to wedge CPU_COMM and the SoC. */
#define BLOCKED_SCREEN_COVER_ID 0x0152f134U
#define WCE_GET_WINDOW_ID 0xfd483f67U
#define WCE_GET_ACTIVE_WINDOW_ID 0x7bbd5772U
#define WINDOW_SCRATCH_START 0x4d800000U
#define WINDOW_SCRATCH_END 0x4d900000U

struct routine {
	uint32_t id;
	char name[33];
};

static const char *routines_path(void)
{
	const char *override = getenv("CPU_COMM_ROUTINES");

	return override && override[0] ? override : CPU_COMM_ROUTINES_PATH;
}

static void usage(FILE *out, const char *prog)
{
	fprintf(out,
		"Usage:\n"
		"  %s NAME [ARG ...]\n"
		"  %s --id COMPONENT_ID [ARG ...]\n"
		"  %s --list\n"
		"\n"
		"NAME is resolved case-insensitively from %s. The THal_Vp_\n"
		"prefix and _1_000 suffix may be omitted. Prefixes must be unique.\n"
		"Arguments are 32-bit integers (decimal or 0x-prefixed), maximum %u.\n",
		prog, prog, prog, CPU_COMM_ROUTINES_PATH, MAX_VALUES);
}

static uint64_t monotonic_us(void)
{
	struct timespec ts;

	if (clock_gettime(CLOCK_MONOTONIC, &ts) < 0)
		return 0;
	return (uint64_t)ts.tv_sec * UINT64_C(1000000) +
	       (uint64_t)ts.tv_nsec / UINT64_C(1000);
}

static int load_routines(struct routine **routines_out, size_t *count_out)
{
	struct routine *routines = NULL;
	size_t count = 0, capacity = 0;
	char *line = NULL;
	size_t line_size = 0;
	FILE *fp;
	const char *path = routines_path();

	fp = fopen(path, "r");
	if (!fp) {
		fprintf(stderr, "open %s: %s\n", path,
			strerror(errno));
		return -1;
	}

	while (getline(&line, &line_size, fp) >= 0) {
		struct routine item = { 0 };
		unsigned int index, cpu;
		int next;

		if (sscanf(line, " %u 0x%" SCNx32 " %u %d %32[^\n]",
			   &index, &item.id, &cpu, &next, item.name) != 5)
			continue;
		if (!strcmp(item.name, "(unnamed)"))
			continue;

		if (count == capacity) {
			size_t new_capacity = capacity ? capacity * 2 : 128;
			struct routine *new_routines;

			new_routines = realloc(routines,
					       new_capacity * sizeof(*new_routines));
			if (!new_routines) {
				fprintf(stderr, "allocate routine table: %s\n",
					strerror(errno));
				free(routines);
				free(line);
				fclose(fp);
				return -1;
			}
			routines = new_routines;
			capacity = new_capacity;
		}
		routines[count++] = item;
	}

	if (ferror(fp)) {
		fprintf(stderr, "read %s: %s\n", path,
			strerror(errno));
		free(routines);
		free(line);
		fclose(fp);
		return -1;
	}

	free(line);
	fclose(fp);
	*routines_out = routines;
	*count_out = count;
	return 0;
}

static void normalized_name(const char *source, char *dest, size_t dest_size)
{
	static const char prefix[] = "thal_vp_";
	static const char suffix[] = "_1_000";
	size_t length, i;

	while (isspace((unsigned char)*source))
		source++;
	if (!strncasecmp(source, prefix, sizeof(prefix) - 1))
		source += sizeof(prefix) - 1;

	length = strnlen(source, dest_size - 1);
	while (length && isspace((unsigned char)source[length - 1]))
		length--;
	if (length >= sizeof(suffix) - 1 &&
	    !strncasecmp(source + length - (sizeof(suffix) - 1), suffix,
			 sizeof(suffix) - 1))
		length -= sizeof(suffix) - 1;

	for (i = 0; i < length && i + 1 < dest_size; i++)
		dest[i] = (char)tolower((unsigned char)source[i]);
	dest[i] = '\0';
}

static bool prefix_compatible(const char *left, const char *right)
{
	size_t left_len = strlen(left);
	size_t right_len = strlen(right);
	size_t common = left_len < right_len ? left_len : right_len;

	/* Either side may be truncated: proc names are only 32 bytes wide. */
	return common && !strncmp(left, right, common);
}

static int resolve_name(const struct routine *routines, size_t count,
			const char *query, struct routine *resolved)
{
	char normalized_query[128];
	size_t i, matches = 0;

	normalized_name(query, normalized_query, sizeof(normalized_query));
	if (!normalized_query[0]) {
		fprintf(stderr, "empty routine name\n");
		return -1;
	}

	for (i = 0; i < count; i++) {
		char normalized_routine[128];

		normalized_name(routines[i].name, normalized_routine,
				sizeof(normalized_routine));
		if (!prefix_compatible(normalized_query, normalized_routine))
			continue;

		if (!matches)
			*resolved = routines[i];
		if (++matches <= 8)
			fprintf(stderr, "%sMATCH 0x%08" PRIx32 " %s\n",
				matches == 1 ? "" : "      ", routines[i].id,
				routines[i].name);
	}

	if (!matches) {
		fprintf(stderr, "no firmware routine matches '%s'\n", query);
		return -1;
	}
	if (matches > 1) {
		fprintf(stderr,
			"refusing ambiguous name '%s' (%zu matches); use a longer name\n",
			query, matches);
		return -1;
	}
	return 0;
}

static int parse_u32(const char *text, uint32_t *value)
{
	char *end;
	intmax_t signed_value;
	uintmax_t unsigned_value;

	errno = 0;
	if (text[0] == '-') {
		signed_value = strtoimax(text, &end, 0);
		if (errno || *end || signed_value < INT32_MIN)
			return -1;
		*value = (uint32_t)(int32_t)signed_value;
		return 0;
	}

	unsigned_value = strtoumax(text, &end, 0);
	if (errno || *end || unsigned_value > UINT32_MAX)
		return -1;
	*value = (uint32_t)unsigned_value;
	return 0;
}

static unsigned int window_arg_count(uint32_t component)
{
	if (component == WCE_GET_WINDOW_ID)
		return 3;
	if (component == WCE_GET_ACTIVE_WINDOW_ID)
		return 2;
	return 0;
}

static bool window_output_safe(uint32_t address, size_t bytes)
{
	return !(address & 3) && address >= WINDOW_SCRATCH_START &&
	       address < WINDOW_SCRATCH_END &&
	       bytes <= WINDOW_SCRATCH_END - address;
}

static int read_phys_words(int mem_fd, uint32_t phys, uint32_t *words,
			   size_t count)
{
	long page_size = sysconf(_SC_PAGESIZE);
	off_t page_base;
	size_t page_offset;
	void *mapping;
	volatile uint32_t *source;
	size_t i;

	if (page_size <= 0 || (phys & 3) || count > SIZE_MAX / sizeof(*words))
		return -1;
	page_base = (off_t)(phys & ~((uint32_t)page_size - 1));
	page_offset = phys - (uint32_t)page_base;
	if (page_offset + count * sizeof(*words) > (size_t)page_size)
		return -1;

	mapping = mmap(NULL, (size_t)page_size, PROT_READ, MAP_SHARED,
		       mem_fd, page_base);
	if (mapping == MAP_FAILED)
		return -1;

	source = (volatile uint32_t *)((uint8_t *)mapping + page_offset);
	for (i = 0; i < count; i++)
		words[i] = source[i];
	munmap(mapping, (size_t)page_size);
	return 0;
}

static void report_window_outputs(const uint32_t *params)
{
	uint32_t first[4], second[4], scalar;
	int mem_fd;

	mem_fd = open("/dev/mem", O_RDONLY | O_SYNC | O_CLOEXEC);
	if (mem_fd < 0) {
		fprintf(stderr, "open /dev/mem for window results: %s\n",
			strerror(errno));
		return;
	}

	if (read_phys_words(mem_fd, params[1], first, 4) ||
	    read_phys_words(mem_fd, params[2], second, 4) ||
	    (params[0] == 3 && read_phys_words(mem_fd, params[3], &scalar, 1))) {
		fprintf(stderr, "read window result workspace: %s\n",
			errno ? strerror(errno) : "invalid or cross-page address");
		close(mem_fd);
		return;
	}
	close(mem_fd);

	printf("CPU_COMM_WINDOW first_raw=%08" PRIx32 ",%08" PRIx32
	       ",%08" PRIx32 ",%08" PRIx32
	       " first_pixels=%g,%g %gx%g\n",
	       first[0], first[1], first[2], first[3],
	       first[0] / 16.0, first[2] / 16.0,
	       first[1] / 16.0, first[3] / 16.0);
	printf("CPU_COMM_WINDOW second_raw=%08" PRIx32 ",%08" PRIx32
	       ",%08" PRIx32 ",%08" PRIx32,
	       second[0], second[1], second[2], second[3]);
	if (params[0] == 3)
		printf(" scalar=%08" PRIx32, scalar);
	putchar('\n');
}

int main(int argc, char **argv)
{
	_Alignas(uint32_t) uint8_t call[CALL_BUFFER_SIZE] = { 0 };
	uint32_t *component = (uint32_t *)(call + COMPONENT_ID_OFFSET);
	uint32_t *params = (uint32_t *)(call + PARAMS_OFFSET);
	uint32_t *results = (uint32_t *)(call + RESULTS_OFFSET);
	struct routine *routines = NULL;
	struct routine resolved = { 0 };
	size_t routine_count = 0;
	uint64_t before, after;
	bool raw_id = false;
	unsigned int arg_count, i;
	int fd, rc, saved_errno;

	if (argc == 2 && !strcmp(argv[1], "--list")) {
		if (load_routines(&routines, &routine_count))
			return 1;
		for (i = 0; i < routine_count; i++)
			printf("0x%08" PRIx32 " %s\n", routines[i].id,
			       routines[i].name);
		free(routines);
		return 0;
	}

	if (argc > 1 && (!strcmp(argv[1], "-h") ||
			 !strcmp(argv[1], "--help"))) {
		usage(stdout, argv[0]);
		return 0;
	}

	if (argc > 1 && !strcmp(argv[1], "--id")) {
		raw_id = true;
		argv++;
		argc--;
	}
	if (argc < 2) {
		usage(stderr, argv[0]);
		return 2;
	}

	arg_count = (unsigned int)(argc - 2);
	if (arg_count > MAX_VALUES) {
		fprintf(stderr, "too many arguments: %u (maximum %u)\n",
			arg_count, MAX_VALUES);
		return 2;
	}

	if (raw_id) {
		if (parse_u32(argv[1], component)) {
			fprintf(stderr, "invalid 32-bit component ID: %s\n", argv[1]);
			return 2;
		}
		strcpy(resolved.name, "(raw ID)");
		resolved.id = *component;
	} else {
		if (load_routines(&routines, &routine_count))
			return 1;
		if (resolve_name(routines, routine_count, argv[1], &resolved)) {
			free(routines);
			return 2;
		}
		free(routines);
		*component = resolved.id;
	}

	if (*component == BLOCKED_SCREEN_COVER_ID) {
		fprintf(stderr,
			"REFUSED 0x%08" PRIx32 " %s: confirmed to wedge CPU_COMM; "
			"physical power cycle required\n",
			*component, resolved.name);
		return 3;
	}
	if (window_arg_count(*component) && arg_count == 0) {
		fprintf(stderr,
			"REFUSED malformed window getter: %s requires %u ARM "
			"physical output address%s\n", resolved.name,
			window_arg_count(*component),
			window_arg_count(*component) == 1 ? "" : "es");
		return 2;
	}

	params[0] = arg_count;
	for (i = 0; i < arg_count; i++) {
		if (parse_u32(argv[i + 2], &params[i + 1])) {
			fprintf(stderr, "invalid 32-bit argument %u: %s\n", i,
				argv[i + 2]);
			return 2;
		}
	}
	if (window_arg_count(*component) &&
	    (arg_count != window_arg_count(*component) || !params[1] ||
	     !params[2] || !window_output_safe(params[1], 16) ||
	     !window_output_safe(params[2], 16) ||
	     (arg_count == 3 &&
	      (!params[3] || !window_output_safe(params[3], 4))))) {
		fprintf(stderr,
			"REFUSED malformed window getter: supply %u nonzero output "
			"address%s in verified scratch range 0x%08x..0x%08x\n",
			window_arg_count(*component),
			window_arg_count(*component) == 1 ? "" : "es",
			WINDOW_SCRATCH_START, WINDOW_SCRATCH_END - 1);
		return 2;
	}

	fd = open("/dev/cpu_comm", O_RDWR | O_CLOEXEC);
	if (fd < 0) {
		fprintf(stderr, "open /dev/cpu_comm: %s\n", strerror(errno));
		return 1;
	}

	printf("CPU_COMM_CALL_BEGIN component=%08" PRIx32 " name=%s params=%u",
	       *component, resolved.name, arg_count);
	for (i = 0; i < arg_count; i++)
		printf(" arg%u=%08" PRIx32, i, params[i + 1]);
	putchar('\n');
	fflush(stdout);

	/* The whole call buffer, including the result area, starts zeroed. */
	before = monotonic_us();
	rc = ioctl(fd, CPU_COMM_IOCTL_CALL, call);
	saved_errno = errno;
	after = monotonic_us();
	close(fd);

	if (rc < 0) {
		fprintf(stderr,
			"CPU_COMM_CALL_ERROR component=%08" PRIx32
			" elapsed_us=%" PRIu64 " errno=%d (%s)\n",
			*component, after - before, saved_errno,
			strerror(saved_errno));
		return 1;
	}

	printf("CPU_COMM_CALL_OK component=%08" PRIx32
	       " elapsed_us=%" PRIu64 " nret=%" PRIu32,
	       *component, after - before, results[0]);
	for (i = 0; i < results[0] && i < MAX_VALUES; i++)
		printf(" ret%u=%08" PRIx32, i, results[i + 1]);
	putchar('\n');
	if (window_arg_count(*component))
		report_window_outputs(params);

	if (results[0] > MAX_VALUES) {
		fprintf(stderr,
			"warning: firmware reported %" PRIu32
			" results; driver copied none because maximum is %u\n",
			results[0], MAX_VALUES);
		return 4;
	}

	return 0;
}
