#include "runner.h"

#include <gio/gio.h>
#include <sys/wait.h>

static gchar *repo_program(const DcmContext *ctx, const gchar *relative_program) {
    if (!relative_program || !*relative_program) return NULL;
    if (g_path_is_absolute(relative_program)) return g_strdup(relative_program);
    return g_build_filename(ctx->repo_root, relative_program, NULL);
}

DcmCommandResult *dcm_run_capture(const DcmContext *ctx, const gchar *relative_program,
                                  const gchar *const *args, GError **error) {
    gchar *program = repo_program(ctx, relative_program);
    if (!program || !g_file_test(program, G_FILE_TEST_EXISTS)) {
        g_set_error(error, G_IO_ERROR, G_IO_ERROR_NOT_FOUND,
                    "Programme introuvable : %s", program ? program : "(null)");
        g_free(program);
        return NULL;
    }

    GPtrArray *argv = g_ptr_array_new_with_free_func(g_free);
    g_ptr_array_add(argv, g_strdup(program));
    if (args) {
        for (guint i = 0; args[i]; ++i) g_ptr_array_add(argv, g_strdup(args[i]));
    }
    g_ptr_array_add(argv, NULL);

    GSubprocessLauncher *launcher = g_subprocess_launcher_new(
        G_SUBPROCESS_FLAGS_STDOUT_PIPE | G_SUBPROCESS_FLAGS_STDERR_MERGE);
    g_subprocess_launcher_set_cwd(launcher, ctx->repo_root);

    GSubprocess *process = g_subprocess_launcher_spawnv(
        launcher, (const gchar *const *)argv->pdata, error);
    g_object_unref(launcher);
    g_ptr_array_free(argv, TRUE);
    g_free(program);
    if (!process) return NULL;

    gchar *stdout_text = NULL;
    if (!g_subprocess_communicate_utf8(process, NULL, NULL, &stdout_text, NULL, error)) {
        g_object_unref(process);
        g_free(stdout_text);
        return NULL;
    }

    DcmCommandResult *result = g_new0(DcmCommandResult, 1);
    result->exit_code = g_subprocess_get_if_exited(process)
        ? g_subprocess_get_exit_status(process) : 1;
    result->output = stdout_text ? stdout_text : g_strdup("");
    g_object_unref(process);
    return result;
}

void dcm_command_result_free(DcmCommandResult *result) {
    if (!result) return;
    g_free(result->output);
    g_free(result);
}

static gchar *build_shell_command(const DcmContext *ctx, const gchar *program,
                                  const gchar *const *args) {
    gchar *q_repo = g_shell_quote(ctx->repo_root);
    gchar *q_prog = g_shell_quote(program);
    GString *cmd = g_string_new(NULL);
    g_string_append_printf(cmd, "cd %s && %s", q_repo, q_prog);
    g_free(q_repo);
    g_free(q_prog);

    if (args) {
        for (guint i = 0; args[i]; ++i) {
            gchar *q = g_shell_quote(args[i]);
            g_string_append_c(cmd, ' ');
            g_string_append(cmd, q);
            g_free(q);
        }
    }
    g_string_append(cmd,
        "; rc=$?; printf '\\n\\nCommande terminée (code %d).\\n' \"$rc\"; "
        "printf 'Appuyez sur Entrée pour fermer...'; read _; exit \"$rc\"");
    return g_string_free(cmd, FALSE);
}

static gchar *find_terminal(void) {
    const gchar *candidates[] = {
        "x-terminal-emulator", "kitty", "foot", "alacritty", "gnome-terminal", "xterm", NULL
    };
    for (guint i = 0; candidates[i]; ++i) {
        gchar *path = g_find_program_in_path(candidates[i]);
        if (path) return path;
    }
    return NULL;
}

gboolean dcm_launch_interactive(const DcmContext *ctx, const gchar *relative_program,
                                const gchar *const *args, GError **error) {
    gchar *program = repo_program(ctx, relative_program);
    if (!program || !g_file_test(program, G_FILE_TEST_EXISTS)) {
        g_set_error(error, G_IO_ERROR, G_IO_ERROR_NOT_FOUND,
                    "Script introuvable : %s", program ? program : "(null)");
        g_free(program);
        return FALSE;
    }

    gchar *terminal = find_terminal();
    if (!terminal) {
        g_set_error(error, G_IO_ERROR, G_IO_ERROR_NOT_FOUND,
                    "Aucun terminal compatible trouvé.");
        g_free(program);
        return FALSE;
    }

    gchar *cmd = build_shell_command(ctx, program, args);
    gchar *base = g_path_get_basename(terminal);
    GPtrArray *argv = g_ptr_array_new_with_free_func(g_free);
    g_ptr_array_add(argv, g_strdup(terminal));

    if (g_strcmp0(base, "gnome-terminal") == 0) {
        g_ptr_array_add(argv, g_strdup("--"));
        g_ptr_array_add(argv, g_strdup("bash"));
        g_ptr_array_add(argv, g_strdup("-lc"));
        g_ptr_array_add(argv, g_strdup(cmd));
    } else if (g_strcmp0(base, "kitty") == 0) {
        g_ptr_array_add(argv, g_strdup("--hold"));
        g_ptr_array_add(argv, g_strdup("bash"));
        g_ptr_array_add(argv, g_strdup("-lc"));
        g_ptr_array_add(argv, g_strdup(cmd));
    } else if (g_strcmp0(base, "xterm") == 0) {
        g_ptr_array_add(argv, g_strdup("-hold"));
        g_ptr_array_add(argv, g_strdup("-e"));
        g_ptr_array_add(argv, g_strdup("bash"));
        g_ptr_array_add(argv, g_strdup("-lc"));
        g_ptr_array_add(argv, g_strdup(cmd));
    } else {
        g_ptr_array_add(argv, g_strdup("-e"));
        g_ptr_array_add(argv, g_strdup("bash"));
        g_ptr_array_add(argv, g_strdup("-lc"));
        g_ptr_array_add(argv, g_strdup(cmd));
    }
    g_ptr_array_add(argv, NULL);

    gboolean ok = g_spawn_async(NULL, (gchar **)argv->pdata, NULL, G_SPAWN_SEARCH_PATH,
                                NULL, NULL, NULL, error);
    g_ptr_array_free(argv, TRUE);
    g_free(cmd);
    g_free(base);
    g_free(terminal);
    g_free(program);
    return ok;
}
