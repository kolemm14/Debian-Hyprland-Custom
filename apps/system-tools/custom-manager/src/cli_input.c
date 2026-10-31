#define _POSIX_C_SOURCE 200809L
#include "cli_input.h"
#include <termios.h>
#include <poll.h>
#include <unistd.h>
#include <stdio.h>
#include <sys/ioctl.h>
#include <stdlib.h>

static struct termios saved;
static gboolean active;
void dcm_terminal_leave(void) {
    if (!active) return;
    tcsetattr(STDIN_FILENO, TCSANOW, &saved);
    fputs("\033[0m\033[?25h\033[?1049l", stdout);
    fflush(stdout);
    active = FALSE;
}
gboolean dcm_terminal_enter(void) {
    if (!isatty(STDIN_FILENO) || !isatty(STDOUT_FILENO) ||
        tcgetattr(STDIN_FILENO, &saved) < 0) return FALSE;
    struct termios raw = saved;
    raw.c_lflag &= ~(ICANON | ECHO | IEXTEN);
    raw.c_iflag &= ~(IXON | ICRNL);
    raw.c_cc[VMIN] = 1;
    raw.c_cc[VTIME] = 0;
    if (tcsetattr(STDIN_FILENO, TCSANOW, &raw) < 0) return FALSE;
    active = TRUE;
    atexit(dcm_terminal_leave);
    fputs("\033[?1049h\033[?25l\033[2J", stdout);
    fflush(stdout);
    return TRUE;
}
static int read_byte(int timeout) {
    struct pollfd fd = { STDIN_FILENO, POLLIN, 0 };
    int result = poll(&fd, 1, timeout);
    if (result < 0 || result == 0) return DCM_KEY_NONE;
    unsigned char c;
    return read(STDIN_FILENO, &c, 1) == 1 ? c : DCM_KEY_EOF;
}
int dcm_key_read(int timeout_ms) {
    int c = read_byte(timeout_ms);
    if (c != 27) return c;
    int next = read_byte(35);
    if (next == DCM_KEY_NONE) return 27;
    if (next != '[' && next != 'O') return DCM_KEY_NONE;
    char seq[16] = {0};
    for (guint i = 0; i < sizeof(seq) - 1; i++) {
        next = read_byte(35);
        if (next >= 256) return DCM_KEY_NONE;
        seq[i] = (char)next;
        if ((next >= 'A' && next <= 'Z') || next == '~') break;
    }
    if (!g_strcmp0(seq, "A")) return DCM_KEY_UP;
    if (!g_strcmp0(seq, "B")) return DCM_KEY_DOWN;
    if (!g_strcmp0(seq, "H") || !g_strcmp0(seq, "1~")) return DCM_KEY_HOME;
    if (!g_strcmp0(seq, "F") || !g_strcmp0(seq, "4~")) return DCM_KEY_END;
    if (!g_strcmp0(seq, "5~")) return DCM_KEY_PAGE_UP;
    if (!g_strcmp0(seq, "6~")) return DCM_KEY_PAGE_DOWN;
    return DCM_KEY_NONE;
}
void dcm_terminal_size(int *cols, int *rows) {
    struct winsize size;
    *cols = 80; *rows = 24;
    if (ioctl(STDOUT_FILENO, TIOCGWINSZ, &size) == 0) {
        *cols = size.ws_col; *rows = size.ws_row;
    }
}
