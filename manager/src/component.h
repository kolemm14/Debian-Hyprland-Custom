#ifndef DCM_COMPONENT_H
#define DCM_COMPONENT_H

#include <glib.h>
#include "paths.h"

typedef enum {
    DCM_COMPONENT_UNKNOWN,
    DCM_COMPONENT_AVAILABLE = DCM_COMPONENT_UNKNOWN,
    DCM_COMPONENT_INSTALLED,
    DCM_COMPONENT_PARTIAL,
    DCM_COMPONENT_NOT_INSTALLED,
    DCM_COMPONENT_UPDATE_AVAILABLE,
    DCM_COMPONENT_BROKEN
} DcmComponentState;

typedef struct {
    gchar *id;
    gchar *name;
    gchar *description;
    gchar *details;
    gboolean required;
    gchar **detect_any;
    gchar **detect_all;
    gchar *detect_command;
    gchar *service;
    gchar *install_script;
    gchar *uninstall_script;
    gchar *repair_script;
    gchar *ownership_id;
    gchar **required_files, **dependencies;
    gchar *binary, *version_file, *available_version;
} DcmComponent;

typedef struct {
    DcmComponentState status;
    gboolean files_ok, binary_ok, services_ok, dependencies_ok, owned;
    GPtrArray *problems;
} DcmComponentHealth;
DcmComponentHealth *dcm_component_inspect(const DcmContext *ctx, const DcmComponent *component);
void dcm_component_health_free(DcmComponentHealth *health);
gchar *dcm_component_health_summary(const DcmComponentHealth *health);
void dcm_component_refresh_report(DcmContext *ctx);
GPtrArray *dcm_components_load(const gchar *manifest, GError **error);
void dcm_component_free(gpointer data);
DcmComponentState dcm_component_state(const DcmContext *ctx, const DcmComponent *component);
const gchar *dcm_component_state_label(DcmComponentState state);

#endif
