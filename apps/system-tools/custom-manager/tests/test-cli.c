#include "assistant_router.h"
#include "cli.h"
#include "cli_render.h"
#include "cli_logo.h"
#include "runner.h"
#include <string.h>

static void routing(void) {
    GError *error = NULL;
    GPtrArray *components = dcm_components_load("data/components.ini", &error);
    g_assert_no_error(error); g_assert_nonnull(components);
    const struct { const char *text; DcmIntent intent; } cases[] = {
        {"check updates", DCM_CHECK}, {" CHECK   for updates ", DCM_CHECK},
        {"vérifie les mises à jour", DCM_CHECK}, {"simule la mise à jour", DCM_DRY_RUN},
        {"simulate update", DCM_DRY_RUN}, {"dry run", DCM_DRY_RUN},
        {"montre les composants", DCM_COMPONENTS}, {"show components", DCM_COMPONENTS},
        {"voir les dépendances", DCM_DEPENDENCIES}, {"show dependencies", DCM_DEPENDENCIES},
        {"diagnostique le système", DCM_DIAGNOSE}, {"diagnose system", DCM_DIAGNOSE},
        {"montre les journaux", DCM_LOGS}, {"show logs", DCM_LOGS},
        {"install mpvpaper", DCM_INSTALL}, {"installer mpvpaper", DCM_INSTALL},
        {"open mpvpaper", DCM_OPEN}, {"ouvrir mpvpaper", DCM_OPEN},
        {":help", DCM_HELP}, {"aide", DCM_HELP}, {":quit", DCM_QUIT},
        {"", DCM_UNKNOWN}, {"do something", DCM_UNKNOWN}, {"install unknown", DCM_UNKNOWN},
        {"install mpvpaper; touch /tmp/pwned", DCM_UNKNOWN}, {"$(id)", DCM_UNKNOWN},
        {":check && echo bad", DCM_UNKNOWN}, {"`id`", DCM_UNKNOWN}, {"sh -c id", DCM_UNKNOWN}
    };
    for (guint i = 0; i < G_N_ELEMENTS(cases); i++)
        g_assert_cmpint(dcm_assistant_route(cases[i].text, components).intent, ==, cases[i].intent);
    g_assert_cmpint(dcm_component_lookup(components, "MPVpaper Engine"), ==, 1);
    g_assert_cmpint(dcm_component_lookup(components, "mpvpaper-engine"), ==, 1);
    g_assert_cmpint(dcm_component_lookup(components, "mpvpaper"), ==, 1);
    g_assert_cmpint(dcm_component_lookup(components, "mpv"), ==, -1);
    g_ptr_array_unref(components);
}
static void options(void) {
    gboolean animation = TRUE;
    char *cli[] = {"dcm", "--cli", "--no-animation"};
    g_assert_cmpint(dcm_cli_options(3, cli, &animation), ==, 1); g_assert_false(animation);
    g_assert_cmpint(dcm_cli_options(2, cli, &animation), ==, 1); g_assert_true(animation);
    char *alias[] = {"dcm", "--interactive"};
    g_assert_cmpint(dcm_cli_options(2, alias, &animation), ==, 1);
    char *invalid[] = {"dcm", "--no-animation"};
    g_assert_cmpint(dcm_cli_options(2, invalid, &animation), ==, -1);
    char *diagnose[] = {"dcm", "--diagnose"};
    g_assert_cmpint(dcm_cli_options(2, diagnose, &animation), ==, 0);
    g_assert_cmpint(dcm_cli_options(1, diagnose, &animation), ==, 0);
    char *mixed[] = {"dcm", "--cli", "--diagnose"};
    g_assert_cmpint(dcm_cli_options(3, mixed, &animation), ==, -1);
}
static void rendering(void) {
    g_assert_cmpint(dcm_render_width(180), ==, 90);
    g_assert_cmpint(dcm_render_content_width(180, 45), ==, 44);
    g_assert_cmpint(dcm_render_content_width(80, 24), ==, 50);
    g_assert_cmpint(dcm_render_content_width(45, 18), ==, 37);
    g_assert_cmpint(dcm_render_body_rows(45, FALSE), ==, 18);
    g_assert_cmpint(dcm_render_body_rows(16, TRUE), ==, 5);
    g_assert_cmpint(dcm_layout(120, 30), ==, DCM_LARGE);
    g_assert_cmpint(dcm_layout(80, 24), ==, DCM_MEDIUM);
    g_assert_cmpint(dcm_layout(40, 16), ==, DCM_SMALL);
    g_assert_cmpint(dcm_layout(39, 16), ==, DCM_TINY);
    g_assert_cmpint(dcm_layout(120, 10), ==, DCM_TINY);
    g_assert_cmpint(dcm_color_mode("xterm", "truecolor", "1"), ==, 0);
    g_assert_cmpint(dcm_color_mode("xterm", "truecolor", ""), ==, 0);
    g_assert_cmpint(dcm_color_mode("xterm", "truecolor", NULL), ==, 24);
    g_assert_cmpint(dcm_color_mode("xterm-256color", NULL, NULL), ==, 256);
    g_assert_cmpint(dcm_color_mode("xterm", NULL, NULL), ==, 8);
    gchar *safe = dcm_terminal_text("\033]52;bad\a", 100);
    g_assert_null(strchr(safe, 27)); g_assert_null(strchr(safe, 7)); g_free(safe);
    safe = dcm_terminal_text("é界abc", 4); g_assert_cmpstr(safe, ==, "é界a"); g_free(safe);
}
static void bounded_capture(void) {
    DcmContext ctx = {.repo_root = "."}; GError *error = NULL;
    const gchar *args[] = {"-c", "head -c 400000 /dev/zero | tr '\\0' x", NULL};
    DcmCommandResult *r = dcm_run_capture_bounded(&ctx, "/bin/sh", args, NULL, &error);
    g_assert_no_error(error); g_assert_nonnull(r); g_assert_cmpint(r->exit_code, ==, 0);
    g_assert_cmpuint(strlen(r->output), <, 263000);
    g_assert_true(g_str_has_prefix(r->output, "[Earlier output truncated]"));
    dcm_command_result_free(r);
    GCancellable *cancel = g_cancellable_new(); g_cancellable_cancel(cancel);
    const gchar *slow[] = {"30", NULL};
    r = dcm_run_capture_bounded(&ctx, "/bin/sleep", slow, cancel, &error);
    g_assert_null(r); g_assert_error(error, G_IO_ERROR, G_IO_ERROR_CANCELLED);
    g_clear_error(&error); g_object_unref(cancel);
    r = dcm_run_capture(&ctx, "/does-not-exist", NULL, &error);
    g_assert_null(r); g_assert_nonnull(error); g_clear_error(&error);
}
static void assert_rgb(CliRgb c, int r, int g, int b) {
    g_assert_cmpint(c.r, ==, r); g_assert_cmpint(c.g, ==, g); g_assert_cmpint(c.b, ==, b);
}
static void logo_colors(void) {
    assert_rgb(cli_logo_gradient(0), 0, 242, 254);
    assert_rgb(cli_logo_gradient(0.45), 138, 43, 226);
    assert_rgb(cli_logo_gradient(0.85), 230, 0, 76);
    assert_rgb(cli_logo_gradient(0.225), 69, 143, 240);
    assert_rgb(cli_logo_gradient(-1), 0, 242, 254);
    assert_rgb(cli_logo_gradient(1), 230, 0, 76);
    CliRgb a = cli_logo_color(0.2, 0.7, 1.25, TRUE);
    CliRgb b = cli_logo_color(0.2, 0.7, 8.25, TRUE);
    assert_rgb(b, a.r, a.g, a.b);
    b = cli_logo_color(0.2, 0.7, 1.25, TRUE);
    assert_rgb(b, a.r, a.g, a.b);
    assert_rgb(cli_logo_color(0.45, 0.45, 999, FALSE), 138, 43, 226);
    assert_rgb(cli_logo_color(0, 0, 0, FALSE), 0, 242, 254);
    for (int i = 0; i < 700; i++) {
        a = cli_logo_color(0.25, 0.75, i/100.0, TRUE);
        b = cli_logo_color(0.25, 0.75, (i+1)/100.0, TRUE);
        g_assert_cmpint(ABS((int)a.r-b.r), <=, 5);
        g_assert_cmpint(ABS((int)a.g-b.g), <=, 5);
        g_assert_cmpint(ABS((int)a.b-b.b), <=, 5);
    }
    gchar *escape = cli_logo_escape(cli_logo_gradient(0), 24);
    g_assert_cmpstr(escape, ==, "\033[38;2;0;242;254m"); g_free(escape);
    escape = cli_logo_escape(cli_logo_gradient(0), 256);
    g_assert_cmpstr(escape, ==, "\033[38;5;51m"); g_free(escape);
    escape = cli_logo_escape(cli_logo_gradient(0), 0);
    g_assert_cmpstr(escape, ==, ""); g_free(escape);
}
static void logo_masks(void) {
    g_assert_cmpint(cli_logo_select(120, 30), ==, HYPR_LOGO_LARGE);
    g_assert_cmpint(cli_logo_select(80, 24), ==, HYPR_LOGO_COMPACT);
    g_assert_cmpint(cli_logo_select(45, 18), ==, HYPR_LOGO_MINI);
    for (int size = HYPR_LOGO_LARGE; size <= HYPR_LOGO_MINI; size++) {
        const CliLogo *logo = cli_logo_get(size);
        g_assert_cmpint(logo->height, >, 0);
        for (int row = 0; row < logo->height; row++) {
            for (int unicode = 0; unicode <= 1; unicode++) {
                gchar *text = cli_logo_row(logo, row, unicode);
                g_assert_true(g_utf8_validate(text, -1, NULL));
                g_assert_null(strchr(text, 27));
                g_assert_cmpint(g_utf8_strlen(text, -1), <=, logo->width);
                if (!unicode) g_assert_cmpint(strlen(text), ==, g_utf8_strlen(text, -1));
                g_free(text);
            }
        }
        g_assert_cmpint(logo->width, <=, size == HYPR_LOGO_LARGE ? 36 : size == HYPR_LOGO_COMPACT ? 19 : 7);
    }
}
static gchar *strip_sgr(const gchar *text) {
    GRegex *regex = g_regex_new("\033\\[[0-9;]*m", 0, 0, NULL);
    gchar *plain = g_regex_replace_literal(regex, text, -1, 0, "", 0, NULL);
    g_regex_unref(regex);
    return plain;
}
static void half_blocks(void) {
    /* Empty, top-only, bottom-only, both; the final empty cell checks BG reset. */
    const unsigned char pixels[] = {0,1,0,3,0, 0,0,5,5,0};
    gchar *row = cli_logo_render_pixels(pixels, 5, 2, 0, TRUE, 0, 0, FALSE);
    g_assert_cmpstr(row, ==, " ▀▄█ "); g_assert_null(strchr(row, 27)); g_free(row);
    row = cli_logo_render_pixels(pixels, 5, 2, 0, TRUE, 24, 0, FALSE);
    g_assert_nonnull(strstr(row, "\033[38;2;"));
    g_assert_nonnull(strstr(row, "\033[48;2;"));
    g_assert_nonnull(strstr(row, "\033[49m "));
    gchar *plain = strip_sgr(row); g_assert_cmpstr(plain, ==, " ▀▄▀ ");
    g_free(row); g_free(plain);
    row = cli_logo_render_pixels(pixels, 5, 2, 0, TRUE, 256, 0, FALSE);
    g_assert_nonnull(strstr(row, "\033[38;5;")); g_assert_nonnull(strstr(row, "\033[48;5;")); g_free(row);
    row = cli_logo_render_pixels(pixels, 5, 2, 0, TRUE, 8, 0, FALSE);
    g_assert_null(strstr(row, ";2;")); g_assert_null(strstr(row, ";5;")); g_free(row);
    const unsigned char odd[] = {1};
    row = cli_logo_render_pixels(odd, 1, 1, 0, TRUE, 0, 0, FALSE);
    g_assert_cmpstr(row, ==, "▀"); g_free(row);
    row = cli_logo_render_pixels(odd, 1, 1, 1, TRUE, 0, 0, FALSE);
    g_assert_cmpstr(row, ==, ""); g_free(row);
    const CliLogo *logo = cli_logo_get(HYPR_LOGO_LARGE);
    g_assert_cmpint(logo->width, ==, 36); g_assert_cmpint(logo->height, ==, 18);
    for (int y = 0; y < 18; y++) {
        row = cli_logo_render_large(y, TRUE, 24, 0, FALSE);
        plain = strip_sgr(row); g_assert_cmpint(g_utf8_strlen(plain, -1), ==, 36);
        g_free(row); g_free(plain);
        row = cli_logo_render_large(y, TRUE, 0, 0, FALSE);
        g_assert_null(strchr(row, 27)); g_assert_cmpint(g_utf8_strlen(row, -1), ==, 36); g_free(row);
    }
    row = cli_logo_render_large(0, TRUE, 0, 0, FALSE);
    g_assert_nonnull(strstr(row, "▄   ▄")); g_free(row);
    row = cli_logo_render_large(8, TRUE, 24, 42, FALSE);
    plain = cli_logo_render_large(8, TRUE, 24, 0, FALSE);
    g_assert_cmpstr(row, ==, plain); g_free(row); g_free(plain);
}
static void spatial_colors(void) {
    assert_rgb(cli_logo_spatial_gradient(0), 0,242,254);
    assert_rgb(cli_logo_spatial_gradient(0.25), 91,140,255);
    assert_rgb(cli_logo_spatial_gradient(0.5), 138,43,226);
    assert_rgb(cli_logo_spatial_gradient(0.75), 255,98,176);
    assert_rgb(cli_logo_spatial_gradient(1), 230,0,76);
    assert_rgb(cli_logo_spatial_gradient(0.125), 46,191,255);
    g_assert_cmpint(rgb_to_ansi256((CliRgb){0,255,255}), ==, 51);
    g_assert_cmpint(rgb_to_ansi256((CliRgb){255,0,0}), ==, 196);
    for (int region = 1; region <= 5; region++) {
        CliRgb a = cli_logo_pixel_color(region, 10, 12, 36, 36, 0, TRUE);
        CliRgb b = cli_logo_pixel_color(region, 10, 12, 36, 36, 7, TRUE);
        assert_rgb(b, a.r, a.g, a.b);
        a = cli_logo_pixel_color(region, 10, 12, 36, 36, 999, FALSE);
        b = cli_logo_pixel_color(region, 10, 12, 36, 36, 0, FALSE);
        assert_rgb(b, a.r, a.g, a.b);
    }
    for (int tick = 0; tick <= 70; tick++) {
        double seconds = tick / 10.0;
        CliRgb cyan = cli_logo_pixel_color(1, 1, 14, 36, 36, seconds, TRUE);
        CliRgb violet = cli_logo_pixel_color(3, 16, 15, 36, 36, seconds, TRUE);
        CliRgb red = cli_logo_pixel_color(5, 31, 15, 36, 36, seconds, TRUE);
        g_assert_cmpint(cyan.g, >, 160); g_assert_cmpint(cyan.r, <, 65);
        g_assert_cmpint(violet.b, >, 150); g_assert_cmpint(violet.r, >, violet.g);
        g_assert_cmpint(red.r, >, 180); g_assert_cmpint(red.r, >, red.b + 70);
    }
}
int main(int argc, char **argv) {
    g_test_init(&argc, &argv, NULL);
    g_test_add_func("/cli/router", routing); g_test_add_func("/cli/options", options);
    g_test_add_func("/cli/render", rendering); g_test_add_func("/cli/bounded-capture", bounded_capture);
    g_test_add_func("/logo/colors", logo_colors);
    g_test_add_func("/logo/masks", logo_masks);
    g_test_add_func("/logo/half-blocks", half_blocks);
    g_test_add_func("/logo/spatial-colors", spatial_colors);
    return g_test_run();
}
