#ifndef DCM_CLI_LOGO_H
#define DCM_CLI_LOGO_H
#include <glib.h>
typedef enum { HYPR_LOGO_LARGE, HYPR_LOGO_COMPACT, HYPR_LOGO_MINI } CliLogoSize;
typedef struct { const char *const *rows; int width, height; } CliLogo;
typedef struct { guint8 r, g, b; } CliRgb;
const CliLogo *cli_logo_get(CliLogoSize size);
CliLogoSize cli_logo_select(int cols, int rows);
gchar *cli_logo_row(const CliLogo *logo, int row, gboolean unicode);
CliRgb cli_logo_gradient(double t);
CliRgb cli_logo_color(double nx, double ny, double seconds, gboolean animated);
gchar *cli_logo_escape(CliRgb color, int mode);
int rgb_to_ansi256(CliRgb color);
CliRgb cli_logo_spatial_gradient(double t);
CliRgb cli_logo_pixel_color(unsigned char region, int x, int y, int width, int height,
                           double seconds, gboolean animated);
gchar *cli_logo_render_pixels(const unsigned char *pixels, int width, int height,
    int row, gboolean unicode, int mode, double seconds, gboolean animated);
gchar *cli_logo_render_large(int row, gboolean unicode, int mode, double seconds, gboolean animated);
#endif
