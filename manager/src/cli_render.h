#ifndef DCM_CLI_RENDER_H
#define DCM_CLI_RENDER_H
#include <glib.h>
typedef enum { DCM_TINY, DCM_SMALL, DCM_MEDIUM, DCM_LARGE } DcmLayout;
typedef struct {
    GPtrArray *previous;
    int color;
    gint64 animation_start;
    guint last_frame;
    double seconds;
} DcmRenderer;
DcmLayout dcm_layout(int cols, int rows);
int dcm_render_width(int cols);
int dcm_render_content_width(int cols, int rows);
int dcm_render_body_rows(int rows, gboolean input);
int dcm_color_mode(const char *term, const char *colorterm, const char *no_color);
gchar *dcm_terminal_text(const gchar *text, int width);
void dcm_render(DcmRenderer *r, GPtrArray *lines, const gchar *mode,
                const gchar *status, const gchar *prompt, int selected,
                int offset, guint frame, gboolean busy, gboolean full);
void dcm_renderer_clear(DcmRenderer *r);
#endif
