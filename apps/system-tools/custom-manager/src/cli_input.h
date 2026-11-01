#ifndef DCM_CLI_INPUT_H
#define DCM_CLI_INPUT_H
#include <glib.h>
enum { DCM_KEY_NONE = 256, DCM_KEY_UP, DCM_KEY_DOWN, DCM_KEY_PAGE_UP,
       DCM_KEY_PAGE_DOWN, DCM_KEY_HOME, DCM_KEY_END, DCM_KEY_EOF };
gboolean dcm_terminal_enter(void);
void dcm_terminal_leave(void);
int dcm_key_read(int timeout_ms);
void dcm_terminal_size(int *cols, int *rows);
#endif
