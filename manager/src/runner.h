#ifndef DCM_RUNNER_H
#define DCM_RUNNER_H

#include <glib.h>
#include <gio/gio.h>
#include "paths.h"

typedef struct {
    gint exit_code;
    gchar *output;
} DcmCommandResult;

DcmCommandResult *dcm_run_capture(const DcmContext *ctx, const gchar *relative_program,
                                  const gchar *const *args, GError **error);
void dcm_command_result_free(DcmCommandResult *result);
/* Bounded capture for terminal jobs; cancellation stops the direct child. */
DcmCommandResult *dcm_run_capture_bounded(const DcmContext *ctx, const gchar *program,
    const gchar *const *args, GCancellable *cancel, GError **error);
gboolean dcm_launch_interactive(const DcmContext *ctx, const gchar *relative_program,
                                const gchar *const *args, GError **error);

#endif
