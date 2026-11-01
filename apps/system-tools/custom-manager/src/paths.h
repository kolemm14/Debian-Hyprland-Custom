#ifndef DCM_PATHS_H
#define DCM_PATHS_H

#include <glib.h>

typedef struct {
    gchar *repo_root;
    gchar *components_file;
    gchar *config_file;
    gchar *development_root;
    gchar *data_dir, *state_dir, *cache_dir;
    GKeyFile *ownership_report;
} DcmContext;

DcmContext *dcm_context_new(GError **error);
void dcm_context_free(DcmContext *ctx);
gchar *dcm_expand_path(const DcmContext *ctx, const gchar *value);
gboolean dcm_relative_path_valid(const gchar *path);
gboolean dcm_repo_is_valid(const gchar *path);

#endif
