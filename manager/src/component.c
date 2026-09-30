#include "component.h"

#include <gio/gio.h>
#include <string.h>

static gchar *get_string(GKeyFile *key, const gchar *group, const gchar *name) {
    gchar *value = g_key_file_get_string(key, group, name, NULL);
    if (value) g_strstrip(value);
    return value;
}

static gchar **get_list(GKeyFile *key, const gchar *group, const gchar *name) {
    gsize length = 0;
    gchar **list = g_key_file_get_string_list(key, group, name, &length, NULL);
    if (!list || length == 0) {
        g_strfreev(list);
        return NULL;
    }
    return list;
}

void dcm_component_free(gpointer data) {
    DcmComponent *c = data;
    if (!c) return;
    g_free(c->id);
    g_free(c->name);
    g_free(c->description);
    g_free(c->details);
    g_strfreev(c->detect_any);
    g_strfreev(c->detect_all);
    g_free(c->detect_command);
    g_free(c->service);
    g_free(c->install_script);
    g_free(c->uninstall_script);
    g_free(c->repair_script);
    g_free(c);
}

GPtrArray *dcm_components_load(const gchar *manifest, GError **error) {
    GKeyFile *key = g_key_file_new();
    if (!g_key_file_load_from_file(key, manifest, G_KEY_FILE_NONE, error)) {
        g_key_file_unref(key);
        return NULL;
    }

    gsize count = 0;
    gchar **groups = g_key_file_get_groups(key, &count);
    GPtrArray *items = g_ptr_array_new_with_free_func(dcm_component_free);

    for (gsize i = 0; i < count; ++i) {
        if (!g_str_has_prefix(groups[i], "component:")) continue;
        DcmComponent *c = g_new0(DcmComponent, 1);
        c->id = g_strdup(groups[i] + strlen("component:"));
        c->name = get_string(key, groups[i], "name");
        c->description = get_string(key, groups[i], "description");
        c->details = get_string(key, groups[i], "details");
        c->required = g_key_file_get_boolean(key, groups[i], "required", NULL);
        c->detect_any = get_list(key, groups[i], "detect_any");
        c->detect_all = get_list(key, groups[i], "detect_all");
        c->detect_command = get_string(key, groups[i], "detect_command");
        c->service = get_string(key, groups[i], "service");
        c->install_script = get_string(key, groups[i], "install_script");
        c->uninstall_script = get_string(key, groups[i], "uninstall_script");
        c->repair_script = get_string(key, groups[i], "repair_script");

        if (!c->name || !*c->name) {
            g_free(c->name);
            c->name = g_strdup(c->id);
        }
        if (!c->description) c->description = g_strdup("");
        g_ptr_array_add(items, c);
    }

    g_strfreev(groups);
    g_key_file_unref(key);
    return items;
}

static gboolean path_exists(const DcmContext *ctx, const gchar *value) {
    gchar *path = dcm_expand_path(ctx, value);
    gboolean exists = path && g_file_test(path, G_FILE_TEST_EXISTS);
    g_free(path);
    return exists;
}

static gboolean any_paths_exist(const DcmContext *ctx, gchar **paths) {
    if (!paths) return FALSE;
    for (guint i = 0; paths[i]; ++i) {
        if (path_exists(ctx, paths[i])) return TRUE;
    }
    return FALSE;
}

static gboolean all_paths_exist(const DcmContext *ctx, gchar **paths) {
    if (!paths) return TRUE;
    for (guint i = 0; paths[i]; ++i) {
        if (!path_exists(ctx, paths[i])) return FALSE;
    }
    return TRUE;
}

static gboolean command_exists(const gchar *command) {
    if (!command || !*command) return FALSE;
    gchar *path = g_find_program_in_path(command);
    gboolean found = path != NULL;
    g_free(path);
    return found;
}

static gboolean service_active(const gchar *service) {
    if (!service || !*service) return TRUE;
    gchar *argv[] = {"systemctl", "--user", "is-active", "--quiet", (gchar *)service, NULL};
    gint status = 0;
    if (!g_spawn_sync(NULL, argv, NULL, G_SPAWN_SEARCH_PATH,
                      NULL, NULL, NULL, NULL, &status, NULL)) return FALSE;
    return g_spawn_check_wait_status(status, NULL);
}

DcmComponentState dcm_component_state(const DcmContext *ctx, const DcmComponent *c) {
    gboolean has_any_rule = c->detect_any != NULL;
    gboolean has_all_rule = c->detect_all != NULL;
    gboolean has_command_rule = c->detect_command && *c->detect_command;

    gboolean any_ok = !has_any_rule || any_paths_exist(ctx, c->detect_any);
    gboolean all_ok = !has_all_rule || all_paths_exist(ctx, c->detect_all);
    gboolean command_ok = !has_command_rule || command_exists(c->detect_command);
    gboolean installed = any_ok && all_ok && command_ok;

    if (!has_any_rule && !has_all_rule && !has_command_rule) {
        return DCM_COMPONENT_AVAILABLE;
    }
    if (!installed) return DCM_COMPONENT_NOT_INSTALLED;
    if (!service_active(c->service)) return DCM_COMPONENT_PARTIAL;
    return DCM_COMPONENT_INSTALLED;
}

const gchar *dcm_component_state_label(DcmComponentState state) {
    switch (state) {
        case DCM_COMPONENT_INSTALLED: return "Installé";
        case DCM_COMPONENT_PARTIAL: return "À vérifier";
        case DCM_COMPONENT_NOT_INSTALLED: return "Non installé";
        case DCM_COMPONENT_AVAILABLE:
        default: return "Disponible";
    }
}
