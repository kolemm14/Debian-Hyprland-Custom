#ifndef DCM_CLI_H
#define DCM_CLI_H
#include <glib.h>
/* 0: GTK, 1: CLI, -1: invalid CLI options. */
int dcm_cli_options(int argc, char **argv, gboolean *animate);
int dcm_cli_run(gboolean animate);
#endif
