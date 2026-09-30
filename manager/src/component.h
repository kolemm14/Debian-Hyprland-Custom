#ifndef DCM_COMPONENT_H
#define DCM_COMPONENT_H

#include <glib.h>
#include "paths.h"

typedef enum {
    DCM_COMPONENT_AVAILABLE,
    DCM_COMPONENT_INSTALLED,
    DCM_COMPONENT_PARTIAL,
    DCM_COMPONENT_NOT_INSTALLED
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
} DcmComponent;

GPtrArray *dcm_components_load(const gchar *manifest, GError **error);
void dcm_component_free(gpointer data);
DcmComponentState dcm_component_state(const DcmContext *ctx, const DcmComponent *component);
const gchar *dcm_component_state_label(DcmComponentState state);

#endif
