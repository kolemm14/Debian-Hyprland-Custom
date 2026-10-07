#include "install_state.h"
#include "runner.h"
#include <gio/gio.h>
#include <string.h>

static gboolean valid(const DcmInstallState *s) {
    if (!s || s->schema_version != 2) return FALSE;
    const gchar *values[] = {s->installed_version,s->installed_commit,s->channel,s->repository,s->branch,s->installed_at};
    for (guint i=0;i<G_N_ELEMENTS(values);i++)
        if (!values[i] || !*values[i] || strpbrk(values[i], "\n\r")) return FALSE;
    if (strlen(s->installed_commit)!=40 && strlen(s->installed_commit)!=64) return FALSE;
    for (const gchar *p=s->installed_commit;*p;p++) if (!g_ascii_isxdigit(*p) || g_ascii_isupper(*p)) return FALSE;
    if (strstr(s->branch,"..") || s->branch[0]=='-' || s->branch[0]=='/') return FALSE;
    for (const gchar *p=s->branch;*p;p++) if (!g_ascii_isalnum(*p) && !strchr("._/-",*p)) return FALSE;
    return g_path_is_absolute(s->repository) || g_str_has_prefix(s->repository,"https://") ||
        g_str_has_prefix(s->repository,"ssh://") || g_str_has_prefix(s->repository,"git@") ||
        g_str_has_prefix(s->repository,"file://");
}
void dcm_install_state_free(DcmInstallState *s) {
    if (!s) return;
    g_free(s->installed_version); g_free(s->installed_commit); g_free(s->channel);
    g_free(s->repository); g_free(s->branch); g_free(s->installed_at); g_free(s);
}
DcmInstallState *dcm_install_state_load(const gchar *path, GError **error) {
    if (!g_file_test(path,G_FILE_TEST_EXISTS)) return NULL;
    GKeyFile *key=g_key_file_new();
    if (!g_key_file_load_from_file(key,path,G_KEY_FILE_NONE,error)) { g_key_file_unref(key); return NULL; }
    DcmInstallState *s=g_new0(DcmInstallState,1);
    s->schema_version=g_key_file_get_integer(key,"installation","schema_version",NULL);
#define GET(field) s->field=g_key_file_get_string(key,"installation",#field,NULL)
    GET(installed_version); GET(installed_commit); GET(channel); GET(repository); GET(branch); GET(installed_at);
#undef GET
    g_key_file_unref(key);
    if (!valid(s)) { g_set_error_literal(error,G_IO_ERROR,G_IO_ERROR_INVALID_DATA,"Invalid InstallState; original file preserved"); dcm_install_state_free(s); return NULL; }
    return s;
}
gboolean dcm_install_state_write(const gchar *path,const DcmInstallState *s,GError **error) {
    if (!valid(s)) { g_set_error_literal(error,G_IO_ERROR,G_IO_ERROR_INVALID_DATA,"Invalid InstallState"); return FALSE; }
    GKeyFile *key=g_key_file_new();
    g_key_file_set_integer(key,"installation","schema_version",2);
#define SET(field) g_key_file_set_string(key,"installation",#field,s->field)
    SET(installed_version); SET(installed_commit); SET(channel); SET(repository); SET(branch); SET(installed_at);
#undef SET
    gsize size; gchar *data=g_key_file_to_data(key,&size,NULL), *dir=g_path_get_dirname(path);
    gboolean ok=FALSE;
    if (g_mkdir_with_parents(dir,0700)==0)
        ok=g_file_set_contents_full(path,data,size,G_FILE_SET_CONTENTS_CONSISTENT|G_FILE_SET_CONTENTS_DURABLE,0600,error);
    else g_set_error_literal(error,G_IO_ERROR,G_IO_ERROR_FAILED,"Cannot create InstallState directory");
    g_free(dir); g_free(data); g_key_file_unref(key); return ok;
}
DcmInstallState *dcm_install_state_migrate(const DcmContext *ctx,GError **error) {
    gchar *path=g_build_filename(ctx->data_dir,"install-state.ini",NULL);
    DcmInstallState *s=dcm_install_state_load(path,error);
    if (!s && (!error || !*error) && !g_file_test(path,G_FILE_TEST_EXISTS)) {
        const gchar *args[]={"--state",NULL};
        DcmCommandResult *r=dcm_run_capture(ctx,"update.sh",args,error);
        if (r && r->exit_code) g_set_error(error,G_IO_ERROR,G_IO_ERROR_FAILED,"InstallState migration failed: %s",r->output);
        if (r && !r->exit_code) s=dcm_install_state_load(path,error);
        dcm_command_result_free(r);
    }
    g_free(path); return s;
}
