#include "component.h"
#include "runner.h"
#include "install_state.h"

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
    g_free(c->ownership_id); g_strfreev(c->required_files); g_strfreev(c->dependencies);
    g_free(c->binary); g_free(c->version_file); g_free(c->available_version);
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
        c->ownership_id = get_string(key, groups[i], "ownership_id");
        if (!c->ownership_id) c->ownership_id = g_strdup(c->id);
        c->required_files = get_list(key, groups[i], "required_files");
        c->dependencies = get_list(key, groups[i], "dependencies");
        c->binary = get_string(key, groups[i], "binary");
        c->version_file = get_string(key, groups[i], "version_file");
        c->available_version = get_string(key, groups[i], "available_version");
        const gchar *scripts[] = {c->install_script, c->uninstall_script, c->repair_script, c->details};
        for (guint j=0;j<G_N_ELEMENTS(scripts);j++) {
            if (scripts[j] && *scripts[j] && !dcm_relative_path_valid(scripts[j])) {
                g_set_error(error,G_IO_ERROR,G_IO_ERROR_INVALID_DATA,"Unsafe manifest path: %s",scripts[j]);
                dcm_component_free(c); g_ptr_array_unref(items); g_strfreev(groups); g_key_file_unref(key); return NULL;
            }
        }
        if (!g_regex_match_simple("^[A-Za-z0-9][A-Za-z0-9._-]*$",c->ownership_id,0,0)) {
            g_set_error_literal(error,G_IO_ERROR,G_IO_ERROR_INVALID_DATA,"Invalid component id");
            dcm_component_free(c); g_ptr_array_unref(items); g_strfreev(groups); g_key_file_unref(key); return NULL;
        }

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

static gboolean command_exists(const gchar *command) {
    if (!command || !*command) return FALSE;
    gchar *path = g_find_program_in_path(command);
    gboolean found = path != NULL;
    g_free(path);
    return found;
}

void dcm_component_refresh_report(DcmContext *ctx) {
    g_clear_pointer(&ctx->ownership_report,g_key_file_unref);
    ctx->ownership_report=g_key_file_new();
    if (!ctx->data_dir) return;
    gchar *manifest=g_build_filename(ctx->data_dir,"installed-files.json",NULL);
    if (g_file_test(manifest,G_FILE_TEST_IS_REGULAR)) {
        const gchar *args[]={"--inspect",NULL};
        DcmCommandResult *r=dcm_run_capture(ctx,"update.sh",args,NULL);
        if (r && !r->exit_code) g_key_file_load_from_data(ctx->ownership_report,r->output,-1,G_KEY_FILE_NONE,NULL);
        dcm_command_result_free(r);
    }
    g_free(manifest);
}
static void problem(DcmComponentHealth *h,const gchar *kind,const gchar *name) {
    g_ptr_array_add(h->problems,g_strdup_printf("%s: %s",kind,name));
}
DcmComponentHealth *dcm_component_inspect(const DcmContext *ctx,const DcmComponent *c) {
    DcmComponentHealth *h=g_new0(DcmComponentHealth,1);
    h->files_ok=h->binary_ok=h->services_ok=h->dependencies_ok=TRUE;
    h->problems=g_ptr_array_new_with_free_func(g_free);
    guint found=0, rules=0;
    gchar *group=g_strconcat("component:",c->ownership_id ? c->ownership_id : c->id,NULL);
    if (ctx->ownership_report) {
        h->owned=g_key_file_get_boolean(ctx->ownership_report,group,"known",NULL);
        if (h->owned) {
            h->files_ok=g_key_file_get_boolean(ctx->ownership_report,group,"files_ok",NULL);
            found+=g_key_file_get_integer(ctx->ownership_report,group,"healthy_files",NULL);
            gchar *problems=g_key_file_get_string(ctx->ownership_report,group,"problems",NULL);
            if (problems && *problems) g_ptr_array_add(h->problems,problems); else g_free(problems);
        }
    }
    g_free(group);
    gchar **lists[]={c->detect_all,c->required_files};
    for (guint j=0;j<2;j++) for (guint i=0;lists[j] && lists[j][i];i++) {
        rules++;
        if (path_exists(ctx,lists[j][i])) found++;
        else { h->files_ok=FALSE; problem(h,"Missing file",lists[j][i]); }
    }
    if (c->detect_any) {
        gboolean any=FALSE;
        for (guint i=0;c->detect_any[i];i++) if (path_exists(ctx,c->detect_any[i])) any=TRUE;
        rules++;
        if (any) found++; else { h->files_ok=FALSE; problem(h,"Missing installation",c->detect_any[0]); }
    }
    const gchar *binary=c->binary && *c->binary ? c->binary : c->detect_command;
    if (binary && *binary) {
        rules++;
        h->binary_ok=command_exists(binary);
        if (h->binary_ok) found++; else problem(h,"Missing binary",binary);
    }
    for (guint i=0;c->dependencies && c->dependencies[i];i++) {
        if (!command_exists(c->dependencies[i])) { h->dependencies_ok=FALSE; problem(h,"Missing dependency",c->dependencies[i]); }
    }
    if ((found || h->owned) && c->service && *c->service) {
        if (!g_regex_match_simple("^[A-Za-z0-9][A-Za-z0-9@_.-]*$",c->service,0,0)) {
            h->services_ok=FALSE; problem(h,"Invalid service",c->service);
        } else {
            gchar *out=NULL; gint status=0;
            gchar *argv[]={"systemctl","--user","show",(gchar *)c->service,"--property=LoadState","--property=ActiveState",NULL};
            gboolean ok=g_spawn_sync(NULL,argv,NULL,G_SPAWN_SEARCH_PATH|G_SPAWN_STDERR_TO_DEV_NULL,NULL,NULL,&out,NULL,&status,NULL);
            h->services_ok=ok && status==0 && out && strstr(out,"LoadState=loaded") && strstr(out,"ActiveState=active");
            if (!h->services_ok) problem(h,"Missing or inactive service",c->service);
            g_free(out);
        }
    }
    if (!rules && !h->owned) h->status=DCM_COMPONENT_UNKNOWN;
    else if (!found && !h->owned) h->status=DCM_COMPONENT_NOT_INSTALLED;
    else if (!h->binary_ok || (h->owned && !h->files_ok && !found)) h->status=DCM_COMPONENT_BROKEN;
    else if (!h->files_ok || !h->services_ok || !h->dependencies_ok) h->status=DCM_COMPONENT_PARTIAL;
    else h->status=DCM_COMPONENT_INSTALLED;
    if (c->version_file && *c->version_file) {
        gchar *path=dcm_expand_path(ctx,c->version_file), *version=NULL;
        gboolean ok=path && g_file_get_contents(path,&version,NULL,NULL);
        if (ok) g_strstrip(version);
        if (!ok && (found || h->owned)) { h->status=DCM_COMPONENT_PARTIAL; problem(h,"Missing version manifest",c->version_file); }
        else if (ok && c->available_version && strcmp(version,c->available_version) && h->status==DCM_COMPONENT_INSTALLED)
            h->status=DCM_COMPONENT_UPDATE_AVAILABLE;
        g_free(path); g_free(version);
    }
    if (h->owned && h->status==DCM_COMPONENT_INSTALLED && ctx->cache_dir && ctx->data_dir) {
        gchar *ip=g_build_filename(ctx->data_dir,"install-state.ini",NULL), *ap=g_build_filename(ctx->cache_dir,"available.ini",NULL);
        DcmInstallState *installed=dcm_install_state_load(ip,NULL), *available=dcm_install_state_load(ap,NULL);
        if (installed && available && !strcmp(installed->repository,available->repository) &&
            !strcmp(installed->branch,available->branch) && strcmp(installed->installed_commit,available->installed_commit))
            h->status=DCM_COMPONENT_UPDATE_AVAILABLE;
        dcm_install_state_free(installed); dcm_install_state_free(available); g_free(ip); g_free(ap);
    }
    return h;
}
void dcm_component_health_free(DcmComponentHealth *h) {
    if (!h) return;
    g_ptr_array_unref(h->problems); g_free(h);
}
gchar *dcm_component_health_summary(const DcmComponentHealth *h) {
    GString *out=g_string_new(NULL);
    for (guint i=0;i<h->problems->len;i++) {
        if (i) g_string_append_c(out,'\n');
        g_string_append(out,g_ptr_array_index(h->problems,i));
    }
    return g_string_free(out,FALSE);
}
DcmComponentState dcm_component_state(const DcmContext *ctx,const DcmComponent *c) {
    DcmComponentHealth *h=dcm_component_inspect(ctx,c);
    DcmComponentState state=h->status; dcm_component_health_free(h); return state;
}
const gchar *dcm_component_state_label(DcmComponentState state) {
    switch (state) {
        case DCM_COMPONENT_INSTALLED: return "Installé";
        case DCM_COMPONENT_PARTIAL: return "À vérifier";
        case DCM_COMPONENT_NOT_INSTALLED: return "Non installé";
        case DCM_COMPONENT_UPDATE_AVAILABLE: return "Mise à jour disponible";
        case DCM_COMPONENT_BROKEN: return "Cassé";
        default: return "Inconnu";
    }
}
