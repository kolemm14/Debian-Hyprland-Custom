#ifndef DCM_ASSISTANT_ROUTER_H
#define DCM_ASSISTANT_ROUTER_H
#include "component.h"
typedef enum {
    DCM_UNKNOWN, DCM_OVERVIEW, DCM_COMPONENTS, DCM_CHECK, DCM_DRY_RUN,
    DCM_DEPENDENCIES, DCM_DIAGNOSE, DCM_LOGS, DCM_ASSISTANT, DCM_HELP,
    DCM_QUIT, DCM_INSTALL, DCM_OPEN, DCM_UPDATE, DCM_ROLLBACK
} DcmIntent;
typedef struct { DcmIntent intent; gint component; } DcmRoute;
gchar *dcm_normalize(const gchar *text);
gint dcm_component_lookup(GPtrArray *components, const gchar *name);
DcmRoute dcm_assistant_route(const gchar *text, GPtrArray *components);
#endif
