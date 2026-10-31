#include "cli_logo.h"
#include <math.h>

/* Image-reference revision: hand-traced open crest, asymmetric outer blade,
 * separate inner arc and a coiled centre. Replaces the former solid interior.
 * 36x36 region mask; no raster conversion or geometry generation at runtime.
 * See tests/logo-image-match.md for reference comparison and limitations. */
#define LOGO_WIDTH 36
#define LOGO_HEIGHT 36
static const unsigned char HYPRDEBIAN_LOGO[LOGO_HEIGHT][LOGO_WIDTH] = {
{0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0},
{0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,0,0,0,2,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0},
{0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,1,0,0,2,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0},
{0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,1,0,0,2,2,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0},
{0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,1,0,0,0,2,2,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0},
{0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,1,0,0,0,0,2,2,0,0,0,0,0,0,0,0,0,0,0,0,0,0},
{0,0,0,0,0,0,0,0,0,0,0,0,0,1,1,1,0,0,0,0,3,3,3,0,0,0,0,0,0,0,0,0,0,0,0,0},
{0,0,0,0,0,0,0,0,0,0,0,0,1,1,1,0,0,0,0,0,0,3,3,0,0,0,0,0,0,0,0,0,0,0,0,0},
{0,0,0,0,0,0,0,0,0,0,0,0,1,1,0,0,0,0,0,0,0,0,3,3,0,0,0,0,0,0,0,0,0,0,0,0},
{0,0,0,0,0,0,0,0,0,0,0,1,1,1,0,0,0,0,0,0,0,0,3,3,3,0,0,0,0,0,0,0,0,0,0,0},
{0,0,0,0,0,0,0,0,0,0,1,1,1,0,0,0,0,0,0,0,0,0,0,3,3,0,0,0,0,0,0,0,0,0,0,0},
{0,0,0,0,0,0,0,0,0,1,1,1,0,0,0,0,0,4,4,4,4,4,4,4,3,3,0,0,0,0,0,0,0,0,0,0},
{0,0,0,0,0,0,0,0,1,1,1,0,0,0,0,0,4,4,4,4,4,4,4,4,4,4,4,0,0,0,0,0,0,0,0,0},
{0,0,0,0,0,0,0,0,1,1,0,0,0,0,0,3,4,0,0,0,0,0,0,0,4,4,4,4,0,0,0,0,0,0,0,0},
{0,0,0,0,0,0,0,1,1,1,0,0,0,0,3,3,0,0,0,0,0,0,0,0,0,0,4,4,0,0,0,0,0,0,0,0},
{0,0,0,0,0,0,1,1,1,0,0,0,0,3,3,0,0,0,0,0,0,0,0,0,0,0,4,4,4,0,0,0,0,0,0,0},
{0,0,0,0,0,1,1,1,0,0,0,0,0,3,0,0,0,0,0,0,0,0,0,0,0,0,0,4,4,0,0,0,0,0,0,0},
{0,0,0,0,0,1,1,0,0,0,0,0,3,3,0,0,0,0,0,0,0,0,0,0,0,0,0,0,4,4,0,0,0,0,0,0},
{0,0,0,0,1,1,1,0,0,0,0,0,3,0,0,0,0,0,0,0,4,5,0,0,0,0,0,0,5,5,0,0,0,0,0,0},
{0,0,0,0,1,1,0,0,0,0,0,0,3,0,0,0,0,0,0,4,4,5,5,0,0,0,0,0,0,5,5,0,0,0,0,0},
{0,0,0,0,1,1,0,0,0,0,0,3,3,0,0,0,0,0,4,0,0,0,5,5,0,0,0,0,0,5,5,0,0,0,0,0},
{0,0,0,1,1,1,0,0,0,0,0,3,3,0,0,0,0,0,4,0,4,5,0,5,0,0,0,0,0,0,5,5,0,0,0,0},
{0,0,0,1,1,1,0,0,0,0,0,3,3,0,0,0,0,0,4,0,4,0,5,5,0,0,0,0,0,0,5,5,0,0,0,0},
{0,0,0,1,1,1,0,0,0,0,0,3,3,0,0,0,0,0,4,0,4,5,5,0,0,0,0,0,0,0,5,5,0,0,0,0},
{0,0,0,0,2,2,0,0,0,0,0,0,3,0,0,0,0,0,4,0,0,0,0,0,0,0,0,0,0,0,5,5,0,0,0,0},
{0,0,0,0,2,2,0,0,0,0,0,0,3,3,0,0,0,0,0,4,0,0,0,5,5,0,0,0,0,0,5,5,0,0,0,0},
{0,0,0,0,2,2,2,0,0,0,0,0,3,3,0,0,0,0,0,0,4,5,5,5,0,0,0,0,0,0,5,5,0,0,0,0},
{0,0,0,0,0,2,2,0,0,0,0,0,0,3,3,3,0,0,0,0,0,0,0,0,0,0,0,0,0,4,5,5,0,0,0,0},
{0,0,0,0,0,2,2,2,0,0,0,0,0,0,3,3,4,0,0,0,0,0,0,0,0,0,0,0,0,4,5,5,0,0,0,0},
{0,0,0,0,0,0,2,2,2,0,0,0,0,0,0,3,4,4,0,0,0,0,0,0,0,0,0,0,4,5,5,0,0,0,0,0},
{0,0,0,0,0,0,0,3,3,3,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,4,5,5,5,0,0,0,0,0},
{0,0,0,0,0,0,0,0,3,3,3,3,0,0,0,0,0,0,0,0,0,0,0,0,0,0,4,5,5,5,0,0,0,0,0,0},
{0,0,0,0,0,0,0,0,0,3,3,3,3,3,0,0,0,0,0,0,0,0,0,0,0,4,5,5,5,0,0,0,0,0,0,0},
{0,0,0,0,0,0,0,0,0,0,3,3,3,3,3,3,5,3,0,0,0,0,4,4,5,5,5,5,0,0,0,0,0,0,0,0},
{0,0,0,0,0,0,0,0,0,0,0,0,3,3,3,3,5,5,5,5,5,5,5,5,5,5,0,0,0,0,0,0,0,0,0,0},
{0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,3,5,5,5,5,5,5,5,5,5,0,0,0,0,0,0,0,0,0,0,0}
};

_Static_assert(LOGO_HEIGHT % 2 == 0, "Logo height must be even");

static const char *const compact[] = {
    "        ╱ ╷",
    "      ╱  ╱",
    "    ╱  ╱ ╭───╮",
    "   ╱  │╭─╯   ╰╮",
    "  │   ││ ╭──╮ │",
    " │    ││ │◉╯│ │",
    " │    │╰╮╰──╯ │",
    "  ╲    ╲╰────╯",
    "   ╲          ╱",
    "    ╰────────╯"
};
static const char *const mini[] = {"   ╱ ╷", " ╱╭@╮│", " ╰╰─╯╯"};
static const CliLogo logos[] = {{NULL, LOGO_WIDTH, LOGO_HEIGHT / 2}, {compact, 16, 10}, {mini, 7, 3}};
const CliLogo *cli_logo_get(CliLogoSize size) {
    return &logos[CLAMP(size, HYPR_LOGO_LARGE, HYPR_LOGO_MINI)];
}
CliLogoSize cli_logo_select(int cols, int rows) {
    if (cols >= 86 && rows >= 30) return HYPR_LOGO_LARGE;
    if (cols >= 65 && rows >= 22) return HYPR_LOGO_COMPACT;
    return HYPR_LOGO_MINI;
}
gchar *cli_logo_row(const CliLogo *logo, int row, gboolean unicode) {
    if (row < 0 || row >= logo->height) return g_strdup("");
    if (!logo->rows) return cli_logo_render_large(row, unicode, 0, 0, FALSE);
    if (unicode) return g_strdup(logo->rows[row]);
    GString *text = g_string_new(NULL);
    for (const gchar *p = logo->rows[row]; *p; p = g_utf8_next_char(p)) {
        gunichar c = g_utf8_get_char(p);
        char ascii = c < 128 ? (char)c : c == 0x2571 ? '/' : c == 0x2572 ? '\\' :
            c == 0x2500 ? '-' : c == 0x2502 || c == 0x2577 ? '|' : c == 0x25c9 ? '@' : '+';
        g_string_append_c(text, ascii);
    }
    return g_string_free(text, FALSE);
}
static CliRgb mix(CliRgb a, CliRgb b, double t) {
    t = CLAMP(t, 0.0, 1.0);
    return (CliRgb){lround(a.r + (b.r-a.r)*t), lround(a.g + (b.g-a.g)*t), lround(a.b + (b.b-a.b)*t)};
}
CliRgb cli_logo_gradient(double t) {
    const CliRgb cyan = {0,242,254}, violet = {138,43,226}, red = {230,0,76};
    if (t <= 0.45) return mix(cyan, violet, t / 0.45);
    return mix(violet, red, (t - 0.45) / 0.40);
}
CliRgb cli_logo_color(double nx, double ny, double seconds, gboolean animated) {
    double base = (CLAMP(nx, 0.0, 1.0) + CLAMP(ny, 0.0, 1.0)) / 2.0;
    if (!animated) return cli_logo_gradient(base);
    double phase = seconds / 7.0;
    CliRgb c = cli_logo_gradient(base + 0.04 * sin(phase * 2 * G_PI + base * G_PI));
    double brightness = 0.94 + 0.06 * sin(phase * 2 * G_PI);
    double band = (sin(phase * 2 * G_PI) + 1) / 2;
    double distance = (base-band) / 0.10;
    double shimmer = 1.0 + 0.03 * exp(-distance*distance);
    double factor = MIN(1.0, brightness * shimmer);
    return (CliRgb){lround(c.r*factor), lround(c.g*factor), lround(c.b*factor)};
}
gchar *cli_logo_escape(CliRgb c, int mode) {
    if (mode == 24) return g_strdup_printf("\033[38;2;%u;%u;%um", c.r, c.g, c.b);
    if (mode == 256) {
        return g_strdup_printf("\033[38;5;%dm", rgb_to_ansi256(c));
    }
    if (mode) return g_strdup_printf("\033[%dm", c.g > c.r ? 36 : c.b > c.r ? 35 : 31);
    return g_strdup("");
}

int rgb_to_ansi256(CliRgb c) {
    /* Nearest level in the actual xterm 6x6x6 cube. */
    const int levels[] = {0, 95, 135, 175, 215, 255};
    int channels[] = {c.r, c.g, c.b}, index[3] = {0};
    for (int channel = 0; channel < 3; channel++)
        for (int i = 1; i < 6; i++)
            if (ABS(channels[channel]-levels[i]) < ABS(channels[channel]-levels[index[channel]]))
                index[channel] = i;
    return 16 + 36*index[0] + 6*index[1] + index[2];
}
CliRgb cli_logo_spatial_gradient(double t) {
    const CliRgb stops[] = {{0,242,254}, {91,140,255}, {138,43,226}, {255,98,176}, {230,0,76}};
    double scaled = CLAMP(t, 0.0, 1.0) * 4;
    int index = MIN(3, (int)scaled);
    return mix(stops[index], stops[index+1], scaled-index);
}
CliRgb cli_logo_pixel_color(unsigned char region, int x, int y, int width, int height,
                           double seconds, gboolean animated) {
    double nx = CLAMP(x / (double)MAX(1, width-1), 0.0, 1.0);
    double ny = CLAMP(y / (double)MAX(1, height-1), 0.0, 1.0);
    double spatial = (nx + ny) / 2;
    double base = 0.90 * (CLAMP((int)region, 1, 5)-1) / 4.0 + 0.10 * spatial;
    if (!animated) return cli_logo_spatial_gradient(base);
    double phase = 2 * G_PI * fmod(seconds / 7.0, 1.0);
    CliRgb c = cli_logo_spatial_gradient(base + 0.04 * sin(phase + spatial * G_PI));
    double brightness = 0.94 + 0.06 * sin(phase);
    double distance = (spatial - (sin(phase)+1)/2) / 0.09;
    double factor = brightness * (1 + 0.08 * exp(-distance*distance));
    return (CliRgb){MIN(255, lround(c.r*factor)), MIN(255, lround(c.g*factor)), MIN(255, lround(c.b*factor))};
}
static int basic_color(CliRgb c) {
    if (c.g > c.r) return c.g > c.b * 0.7 ? 36 : 34;
    return c.b > c.r * 0.65 ? 35 : 31;
}
static guint color_key(CliRgb c, int mode) {
    if (mode == 24) return ((guint)c.r << 16) | ((guint)c.g << 8) | c.b;
    return mode == 256 ? (guint)rgb_to_ansi256(c) : (guint)basic_color(c);
}
static void set_channel(GString *out, CliRgb color, int mode, gboolean bg, gint64 *last) {
    guint key = color_key(color, mode);
    if (*last == key) return;
    if (mode == 24) g_string_append_printf(out, "\033[%d;2;%u;%u;%um", bg ? 48 : 38, color.r, color.g, color.b);
    else if (mode == 256) g_string_append_printf(out, "\033[%d;5;%um", bg ? 48 : 38, key);
    else g_string_append_printf(out, "\033[%um", key + (bg ? 10 : 0));
    *last = key;
}
gchar *cli_logo_render_pixels(const unsigned char *pixels, int width, int height,
    int row, gboolean unicode, int mode, double seconds, gboolean animated) {
    if (!pixels || width <= 0 || height <= 0 || row < 0 || row >= height/2 + height%2)
        return g_strdup("");
    GString *out = g_string_sized_new((gsize)width * 16);
    gint64 fg = -1, bg = -1;
    int y = row * 2;
    for (int x = 0; x < width; x++) {
        unsigned char top = pixels[(gsize)y*width+x];
        unsigned char bottom = y+1 < height ? pixels[(gsize)(y+1)*width+x] : 0;
        gboolean dual = unicode && top && bottom;
        /* Never let a lower-pixel background leak into transparent cells. */
        if (mode && bg != -1 && !dual) { g_string_append(out, "\033[49m"); bg = -1; }
        if (!top && !bottom) { g_string_append_c(out, ' '); continue; }
        if (mode) {
            CliRgb color = cli_logo_pixel_color(top ? top : bottom, x, top ? y : y+1,
                width, height, seconds, animated);
            set_channel(out, color, mode, FALSE, &fg);
            if (dual) set_channel(out, cli_logo_pixel_color(bottom, x, y+1, width, height, seconds, animated), mode, TRUE, &bg);
        }
        g_string_append(out, !unicode ? (top && bottom ? "#" : top ? "^" : "_") :
            top && bottom ? (mode ? "▀" : "█") : top ? "▀" : "▄");
    }
    if (mode && fg != -1) g_string_append(out, "\033[0m");
    return g_string_free(out, FALSE);
}
gchar *cli_logo_render_large(int row, gboolean unicode, int mode, double seconds, gboolean animated) {
    return cli_logo_render_pixels(&HYPRDEBIAN_LOGO[0][0], LOGO_WIDTH, LOGO_HEIGHT,
        row, unicode, mode, seconds, animated);
}
