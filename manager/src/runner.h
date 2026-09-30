#ifndef DCM_RUNNER_H
#define DCM_RUNNER_H

#include <glib.h>
#include "paths.h"

typedef struct {
    gint exit_code;
    gchar *output;
} DcmCommandResult;

DcmCommandResult *dcm_run_capture(const DcmContext *ctx, const gchar *relative_program,
                                  const gchar *const *args, GError **error);
void dcm_command_result_free(DcmCommandResult *result);
gboolean dcm_launch_interactive(const DcmContext *ctx, const gchar *relative_program,
                                const gchar *const *args, GError **error);

#endif
