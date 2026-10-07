#include "cli_render.h"
#include "cli_input.h"
#include "cli_logo.h"
#include <stdio.h>
#include <string.h>

DcmLayout dcm_layout(int cols, int rows) {
    if (cols < 40 || rows < 16) return DCM_TINY;
    if ((cols >= 86 && rows >= 30) || (cols >= 100 && rows >= 24)) return DCM_LARGE;
    return cols >= 65 && rows >= 22 ? DCM_MEDIUM : DCM_SMALL;
}
int dcm_color_mode(const char *term, const char *ct, const char *nc) {
    if (nc || !term || !strcmp(term, "dumb")) return 0;
    if (ct && (strstr(ct, "truecolor") || strstr(ct, "24bit"))) return 24;
    return strstr(term, "256color") ? 256 : 8;
}
/* Treat external output as text, never as terminal control sequences. */
gchar *dcm_terminal_text(const gchar *text, int width) {
    gchar *valid = g_utf8_make_valid(text ? text : "", -1);
    GString *out = g_string_new(NULL);
    int used = 0;
    for (const gchar *p = valid; *p && used < width; p = g_utf8_next_char(p)) {
        gunichar c = g_utf8_get_char(p);
        if (g_unichar_iscntrl(c) || !g_unichar_isprint(c)) c = ' ';
        int cells = g_unichar_iswide(c) ? 2 : (g_unichar_combining_class(c) ? 0 : 1);
        if (used + cells > width) break;
        g_string_append_unichar(out, c);
        used += cells;
    }
    g_free(valid);
    return g_string_free(out, FALSE);
}

int dcm_render_width(int cols) { return MIN(90, MAX(1, cols - 2)); }
int dcm_render_content_width(int cols, int rows) {
    DcmLayout layout = dcm_layout(cols, rows);
    int side = layout == DCM_LARGE ? 40 : layout == DCM_MEDIUM ? 22 : 0;
    return MAX(10, dcm_render_width(cols) - side - 6);
}
int dcm_render_body_rows(int rows, gboolean input) {
    return MAX(1, MIN(18, rows - 8 - (input ? 3 : 0)));
}
static gboolean unicode_available(void) {
    const gchar *locale = g_getenv("LC_ALL");
    if (!locale || !*locale) locale = g_getenv("LC_CTYPE");
    if (!locale || !*locale) locale = g_getenv("LANG");
    gchar *lower = g_ascii_strdown(locale ? locale : "C", -1);
    gboolean utf = strstr(lower, "utf-8") || strstr(lower, "utf8");
    g_free(lower);
    return utf;
}
static int cells(const gchar *text) {
    int width = 0;
    for (const gchar *p = text; *p; p = g_utf8_next_char(p)) {
        gunichar c = g_utf8_get_char(p);
        width += g_unichar_iswide(c) ? 2 : g_unichar_combining_class(c) ? 0 : 1;
    }
    return width;
}
static gchar *pad(const gchar *text, int width) {
    gchar *safe = dcm_terminal_text(text, width);
    gchar *space = g_strnfill(MAX(0, width - cells(safe)), ' ');
    gchar *out = g_strconcat(safe, space, NULL);
    g_free(safe); g_free(space);
    return out;
}
static gchar *paint_mask(DcmRenderer *r, const gchar *text, int width, int height,
                          int row, double seconds, gboolean animated, double brightness) {
    GString *out = g_string_new(NULL);
    int x = 0;
    for (const gchar *p = text; *p; p = g_utf8_next_char(p), x++) {
        if (*p == ' ') { g_string_append_c(out, ' '); continue; }
        CliRgb rgb = cli_logo_color(x / (double)MAX(1, width-1),
            row / (double)MAX(1, height-1), seconds, animated);
        rgb.r *= brightness; rgb.g *= brightness; rgb.b *= brightness;
        gchar *color = cli_logo_escape(rgb, r->color);
        g_string_append(out, color);
        g_string_append_len(out, p, g_utf8_next_char(p) - p);
        g_free(color);
    }
    if (r->color) g_string_append(out, "\033[0m");
    return g_string_free(out, FALSE);
}
static gchar *gradient(DcmRenderer *r, const gchar *text, guint frame, int row) {
    return paint_mask(r, text, MAX(2, cells(text)), 1, 0,
        r->seconds / 3.0 + row * 0.01, frame != 0, 1.0);
}
static gchar *border(int width, const gchar *title, gboolean bottom, gboolean utf) {
    GString *out = g_string_new(utf ? (bottom ? "╰" : "╭") : "+");
    gchar *safe = dcm_terminal_text(title, MAX(0, width - 6));
    int used = 0;
    if (*safe) { g_string_append_printf(out, "─ %s ", safe); used = cells(safe) + 3; }
    /* ASCII terminals must not receive box-drawing characters. */
    if (!utf && *safe) { g_string_truncate(out, 1); g_string_append_printf(out, "- %s ", safe); }
    for (int i = used; i < width - 2; i++) g_string_append(out, utf ? "─" : "-");
    g_string_append(out, utf ? (bottom ? "╯" : "╮") : "+");
    g_free(safe);
    return g_string_free(out, FALSE);
}
static const gchar *panel_title(const gchar *mode) {
    if (!strcmp(mode, "MENU")) return "Actions";
    if (!strcmp(mode, "ASSISTANT")) return "Assistant";
    if (!strcmp(mode, "COMPONENTS")) return "Components";
    if (!strcmp(mode, "LOGS")) return "Logs";
    if (!strcmp(mode, "HELP")) return "Help";
    return mode;
}
static gchar *compact_status(const gchar *status) {
    if (g_str_has_prefix(status, "Ready.")) return g_strdup("Ready");
    if (g_str_has_prefix(status, "Read-only operation complete")) return g_strdup("Update check completed");
    const gchar *end = strstr(status, ". ");
    return end ? g_strndup(status, end - status) : g_strdup(status);
}
void dcm_render(DcmRenderer *r, GPtrArray *lines, const gchar *mode,
                const gchar *status, const gchar *prompt, int selected,
                int offset, guint frame, gboolean busy, gboolean full) {
    if (frame && frame != r->last_frame) {
        gint64 now = g_get_monotonic_time();
        if (!r->animation_start) r->animation_start = now;
        r->seconds = (now - r->animation_start) / 1000000.0;
        r->last_frame = frame;
    }
    int cols, height;
    dcm_terminal_size(&cols, &height);
    GPtrArray *rows = g_ptr_array_new_with_free_func(g_free);
    DcmLayout layout = dcm_layout(cols, height);
    gboolean utf = unicode_available();
    gboolean assistant = !strcmp(mode, "ASSISTANT");
    gboolean input = prompt && *prompt;
    if (layout == DCM_TINY) {
        g_ptr_array_add(rows, dcm_terminal_text("Terminal too small.", MAX(0, cols - 1)));
        g_ptr_array_add(rows, dcm_terminal_text("Please resize to at least 40x16.", MAX(0, cols - 1)));
    } else {
        int width = dcm_render_width(cols);
        int side = layout == DCM_LARGE ? 40 : layout == DCM_MEDIUM ? 22 : 0;
        gboolean large_menu = layout == DCM_LARGE && !strcmp(mode, "MENU");
        /* The validated large mask already includes four transparent columns
         * on its right. Use those as the visible gap beside Actions. */
        if (large_menu && cli_logo_select(cols, height) == HYPR_LOGO_LARGE) side -= 4;
        int panel_width = width - side;
        if (large_menu) {
            int content_width = cells(panel_title(mode));
            for (guint i = 0; i < lines->len; i++) {
                const gchar *text = g_ptr_array_index(lines, i);
                if (g_ascii_isdigit(text[0]) && text[1] == '.' && text[2] == ' ') text += 3;
                content_width = MAX(content_width, cells(text));
            }
            panel_width = MIN(panel_width, content_width + 6);
        }
        int capacity = dcm_render_body_rows(height, input);
        int body = MIN(capacity, MAX(1, (int)lines->len - offset));
        const CliLogo *logo = cli_logo_get(cli_logo_select(cols, height));
        int logo_height = side ? logo->height + 1 : 0;
        int used = MAX(body + 2, logo_height);
        gchar *title = gradient(r, "DEBIAN CUSTOM MANAGER", frame, 0);
        gchar *gap = g_strnfill(MAX(1, width - 21 - (int)strlen(mode)), ' ');
        g_ptr_array_add(rows, g_strdup_printf("%s%s%s", title, gap, mode));
        g_free(title); g_free(gap);
        if (!side) {
            for (int y = 0; y < logo->height; y++) {
                gchar *mask = cli_logo_row(logo, y, utf);
                gchar *colored = paint_mask(r, mask, logo->width, logo->height, y,
                    r->seconds, frame != 0, 1.0);
                const gchar *text = y == 0 ? "Debian + Hyprland control center" :
                    y == 1 ? (utf ? "DEBIAN × HYPR" : "DEBIAN / HYPR") : "";
                gchar *clipped = dcm_terminal_text(text, width-logo->width-2);
                gchar *space = g_strnfill(logo->width-cells(mask)+2, ' ');
                g_ptr_array_add(rows, g_strdup_printf("%s%s%s", colored, space, clipped));
                g_free(mask); g_free(colored); g_free(clipped); g_free(space);
            }
        } else {
            g_ptr_array_add(rows, g_strdup("Debian + Hyprland control center"));
            GString *rule = g_string_new(NULL);
            for (int i = 0; i < width; i++) g_string_append(rule, utf ? "─" : "-");
            g_ptr_array_add(rows, g_string_free(rule, FALSE));
            if (!large_menu) g_ptr_array_add(rows, g_strdup(""));
        }
        int panel_top = large_menu ? 0 : MAX(0, (used - body - 2) / 2);
        for (int y = 0; y < used; y++) {
            GString *out = g_string_new(NULL);
            if (side) {
                gchar *mask = cli_logo_row(logo, y, utf);
                const gchar *label = utf ? "DEBIAN × HYPR" : "DEBIAN / HYPR";
                gchar *colored;
                int occupied;
                if (!logo->rows && y < logo->height) {
                    colored = cli_logo_render_large(y, utf, r->color, r->seconds, frame != 0);
                    occupied = logo->width;
                } else {
                    colored = paint_mask(r, y == logo->height ? label : mask,
                        logo->width, logo->height, MIN(y, logo->height-1), r->seconds,
                        frame != 0, y == logo->height ? 0.85 : 1.0);
                    occupied = cells(y == logo->height ? label : mask);
                }
                /* Keep the caption and status adjacent: the separator shares
                 * the caption row instead of adding an empty footer row. */
                if (large_menu && !input && y == used - 1 && y == logo->height) {
                    g_string_append_printf(out, "%s  ", colored);
                    for (int x = occupied + 2; x < width; x++)
                        g_string_append(out, utf ? "─" : "-");
                    g_free(mask); g_free(colored);
                    g_ptr_array_add(rows, g_string_free(out, FALSE));
                    continue;
                }
                gchar *space = g_strnfill(MAX(0, side - occupied), ' ');
                g_string_append_printf(out, "%s%s", colored, space);
                g_free(mask); g_free(colored); g_free(space);
            }
            int py = y - panel_top;
            if (py == 0 || py == body + 1) {
                gchar *edge = border(panel_width, py == 0 ? panel_title(mode) : "", py != 0, utf);
                g_string_append(out, edge); g_free(edge);
            } else if (py > 0 && py <= body) {
                int index = offset + py - 1;
                const gchar *text = index < (int)lines->len ? g_ptr_array_index(lines, index) : "";
                if (!strcmp(mode, "MENU") && g_ascii_isdigit(text[0]) && text[1] == '.' && text[2] == ' ') text += 3;
                gchar *padded = pad(text, panel_width - 6);
                gchar *paint = index == selected ? gradient(r, padded, frame, py) : g_strdup(padded);
                g_string_append_printf(out, "%s %s %s %s", utf ? "│" : "|",
                    index == selected ? (utf ? "›" : ">") : " ", paint, utf ? "│" : "|");
                g_free(padded); g_free(paint);
            }
            g_ptr_array_add(rows, g_string_free(out, FALSE));
        }
        if (input) {
            gchar *edge = border(width, assistant ? (utf ? "✦ Assistant" : "* Assistant") : "Command / Search", FALSE, utf);
            if (assistant) {
                gchar *symbol = gradient(r, utf ? "✦" : "*", frame, 2);
                gchar **parts = g_strsplit(edge, utf ? "✦" : "*", 2);
                gchar *painted = g_strjoinv(symbol, parts);
                g_free(edge); edge = painted;
                g_strfreev(parts); g_free(symbol);
            }
            g_ptr_array_add(rows, edge);
            const gchar *value = prompt;
            if (assistant && g_str_has_prefix(value, " Ask > ")) value += 7;
            if (assistant && !strcmp(value, "_")) value = "Ask Debian Custom Manager...";
            gchar *padded = pad(value, width - 6);
            gchar *symbol = gradient(r, utf ? "✦" : "*", frame, 2);
            g_ptr_array_add(rows, g_strdup_printf("%s %s %s %s", utf ? "│" : "|", symbol, padded, utf ? "│" : "|"));
            g_free(padded); g_free(symbol);
            g_ptr_array_add(rows, border(width, "", TRUE, utf));
        }
        gchar *short_status = compact_status(status);
        const gchar *symbol = busy ? (utf ? "◌" : "~") :
            strstr(status, "detected") || strstr(status, "could not") ? (utf ? "⚠" : "!") :
            strstr(status, "complete") ? (utf ? "✓" : "+") : (utf ? "✦" : "*");
        gchar *state = g_strdup_printf("%s %s", symbol, short_status);
        g_ptr_array_add(rows, dcm_terminal_text(state, width));
        g_free(state); g_free(short_status);
        const gchar *footer = layout == DCM_LARGE ?
            (utf ? "↑↓ Navigate  Enter Select  Tab Assistant  / Search  : Command  ? Help  Esc Exit" : "Up/Down Navigate  Enter Select  Tab Assistant  / Search  : Command  ? Help  Esc Exit") :
            layout == DCM_MEDIUM ? (utf ? "↑↓ Move  Enter Select  Tab Mode  ? Help  Esc Back" : "Up/Down Move  Enter Select  Tab Mode  ? Help  Esc Back") :
            (utf ? "↑↓  Enter  Tab  Esc" : "Up/Down  Enter  Tab  Esc");
        g_ptr_array_add(rows, dcm_terminal_text(footer, width));
        int margin = MAX(0, (cols - width) / 2);
        gchar *indent = g_strnfill(margin, ' ');
        for (guint i = 0; i < rows->len; i++) {
            gchar *old = g_ptr_array_index(rows, i);
            g_ptr_array_index(rows, i) = g_strconcat(indent, old, NULL); g_free(old);
        }
        g_free(indent);
    }
    if (full) { fputs("\033[2J", stdout); g_clear_pointer(&r->previous, g_ptr_array_unref); }
    guint count = MAX(rows->len, r->previous ? r->previous->len : 0);
    for (guint i = 0; i < count && i < (guint)MAX(height, 0); i++) {
        const gchar *line = i < rows->len ? g_ptr_array_index(rows, i) : "";
        if (!r->previous || i >= r->previous->len || strcmp(line, g_ptr_array_index(r->previous, i)))
            printf("\033[%u;1H\033[2K%s", i+1, line);
    }
    fflush(stdout);
    g_clear_pointer(&r->previous, g_ptr_array_unref);
    r->previous = rows;
}
void dcm_renderer_clear(DcmRenderer *r) { g_clear_pointer(&r->previous, g_ptr_array_unref); }
