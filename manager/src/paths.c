#include "paths.h"

#include <gio/gio.h>
#include <string.h>

#define DCM_ERROR dcm_error_quark()

static GQuark dcm_error_quark(void) {
    return g_quark_from_static_string("debian-custom-manager-error");
}

static gchar *replace_all(const gchar *input, const gchar *needle, const gchar *replacement) {
    if (!input) return NULL;
    if (!needle || !*needle) return g_strdup(input);
    gchar **parts = g_strsplit(input, needle, -1);
    gchar *result = g_strjoinv(replacement ? replacement : "", parts);
    g_strfreev(parts);
    return result;
}

static gchar *trimmed_stdout(gchar *value) {
    if (!value) return NULL;
    g_strstrip(value);
    if (*value == '\0') {
        g_free(value);
        return NULL;
    }
    return value;
}

gboolean dcm_repo_is_valid(const gchar *path) {
    if (!path || !*path) return FALSE;
    gchar *install = g_build_filename(path, "install.sh", NULL);
    gchar *update = g_build_filename(path, "update.sh", NULL);
    gboolean ok = g_file_test(install, G_FILE_TEST_IS_REGULAR) &&
                  g_file_test(update, G_FILE_TEST_IS_REGULAR);
    g_free(install);
    g_free(update);
    return ok;
}

static gchar *repo_from_git(void) {
    gchar *stdout_text = NULL;
    gchar *stderr_text = NULL;
    gint status = 0;
    gchar *argv[] = {"git", "rev-parse", "--show-toplevel", NULL};

    if (!g_spawn_sync(NULL, argv, NULL, G_SPAWN_SEARCH_PATH, NULL, NULL,
                      &stdout_text, &stderr_text, &status, NULL)) {
        g_free(stdout_text);
        g_free(stderr_text);
        return NULL;
    }
    g_free(stderr_text);
    if (!g_spawn_check_wait_status(status, NULL)) {
        g_free(stdout_text);
        return NULL;
    }
    return trimmed_stdout(stdout_text);
}

static gchar *config_path(void) {
    return g_build_filename(g_get_user_config_dir(), "debian-custom-manager", "config.ini", NULL);
}

static gchar *repo_from_config(const gchar *path) {
    GKeyFile *key = g_key_file_new();
    gchar *repo = NULL;
    if (g_key_file_load_from_file(key, path, G_KEY_FILE_NONE, NULL)) {
        repo = g_key_file_get_string(key, "manager", "repo_root", NULL);
        if (repo) g_strstrip(repo);
    }
    g_key_file_unref(key);
    return repo;
}

static gchar *resolve_repo_root(const gchar *cfg) {
    const gchar *env = g_getenv("DHC_REPO_ROOT");
    if (env && dcm_repo_is_valid(env)) return g_strdup(env);

    gchar *candidate = repo_from_config(cfg);
    if (candidate && dcm_repo_is_valid(candidate)) return candidate;
    g_clear_pointer(&candidate, g_free);

    candidate = repo_from_git();
    if (candidate && dcm_repo_is_valid(candidate)) return candidate;
    g_clear_pointer(&candidate, g_free);

    candidate = g_build_filename(g_get_home_dir(), "Debian-Hyprland-Custom", NULL);
    if (dcm_repo_is_valid(candidate)) return candidate;
    g_clear_pointer(&candidate, g_free);

    return NULL;
}

static gchar *resolve_components_file(const gchar *repo_root) {
    const gchar *override = g_getenv("DCM_COMPONENTS_FILE");
    if (override && g_file_test(override, G_FILE_TEST_IS_REGULAR)) return g_strdup(override);

    gchar *path = g_build_filename(repo_root, "manager", "data", "components.ini", NULL);
    if (g_file_test(path, G_FILE_TEST_IS_REGULAR)) return path;
    g_free(path);

    path = g_build_filename(g_get_user_data_dir(), "debian-custom-manager", "components.ini", NULL);
    if (g_file_test(path, G_FILE_TEST_IS_REGULAR)) return path;
    g_free(path);
    return NULL;
}

DcmContext *dcm_context_new(GError **error) {
    DcmContext *ctx = g_new0(DcmContext, 1);
    ctx->config_file = config_path();
    ctx->repo_root = resolve_repo_root(ctx->config_file);

    if (!ctx->repo_root) {
        g_set_error(error, DCM_ERROR, 1,
                    "Dépôt Debian-Hyprland-Custom introuvable. Lancez le Manager depuis le dépôt, "
                    "définissez DHC_REPO_ROOT, ou relancez manager/scripts/install.sh.");
        dcm_context_free(ctx);
        return NULL;
    }

    ctx->components_file = resolve_components_file(ctx->repo_root);
    if (!ctx->components_file) {
        g_set_error(error, DCM_ERROR, 2,
                    "Manifest du Manager introuvable (manager/data/components.ini).");
        dcm_context_free(ctx);
        return NULL;
    }
    return ctx;
}

void dcm_context_free(DcmContext *ctx) {
    if (!ctx) return;
    g_free(ctx->repo_root);
    g_free(ctx->components_file);
    g_free(ctx->config_file);
    g_free(ctx);
}

gchar *dcm_expand_path(const DcmContext *ctx, const gchar *value) {
    if (!value) return NULL;
    gchar *out = g_strdup(value);
    gchar *tmp = NULL;

    if (g_str_has_prefix(out, "~/")) {
        tmp = g_build_filename(g_get_home_dir(), out + 2, NULL);
        g_free(out);
        out = tmp;
    }

    if (strstr(out, "$HOME")) {
        tmp = replace_all(out, "$HOME", g_get_home_dir());
        g_free(out);
        out = tmp;
    }
    if (ctx && ctx->repo_root && strstr(out, "$REPO")) {
        tmp = replace_all(out, "$REPO", ctx->repo_root);
        g_free(out);
        out = tmp;
    }
    return out;
}
