#ifndef DCM_INSTALL_STATE_H
#define DCM_INSTALL_STATE_H
#include "paths.h"
typedef struct {
    guint schema_version;
    gchar *installed_version, *installed_commit, *channel, *repository, *branch, *installed_at;
} DcmInstallState;
DcmInstallState *dcm_install_state_load(const gchar *path, GError **error);
DcmInstallState *dcm_install_state_migrate(const DcmContext *ctx, GError **error);
gboolean dcm_install_state_write(const gchar *path, const DcmInstallState *state, GError **error);
void dcm_install_state_free(DcmInstallState *state);
#endif
