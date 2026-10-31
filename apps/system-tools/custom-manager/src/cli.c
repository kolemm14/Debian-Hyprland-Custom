#define _POSIX_C_SOURCE 200809L
#include "cli.h"
#include "assistant_router.h"
#include "cli_input.h"
#include "cli_render.h"
#include "runner.h"
#include <signal.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

static volatile sig_atomic_t stop_requested, resized;
static void on_signal(int sig) {
    if (sig == SIGWINCH) resized = 1;
    else stop_requested = sig;
}

typedef enum { MENU, OVERVIEW, COMPONENTS, ACTIONS, DEPENDENCIES, LOGS, ASSISTANT, HELP, CONFIRM } Page;
typedef struct {
    DcmContext *ctx;
    GPtrArray *components;
    GArray *states;
    Page page, previous;
    int selected, offset, component, field;
    GString *input, *filter, *logs;
    GPtrArray *history;
    gchar *status, *pending_script;
    gboolean rollback, running, animate;
    DcmRenderer renderer;
    GThread *thread;
    GMutex mutex;
    gboolean done;
    GCancellable *cancel;
    DcmCommandResult *result;
    GError *error;
    const gchar *job_arg;
} Cli;
static const char *menu[] = {"1. Overview", "2. Components", "3. Check for updates",
    "4. Simulate update", "5. Dependencies", "6. Diagnose", "7. Logs", "8. Assistant",
    "9. Help", "0. Exit"};
static const DcmIntent menu_intents[] = {DCM_OVERVIEW, DCM_COMPONENTS, DCM_CHECK, DCM_DRY_RUN,
    DCM_DEPENDENCIES, DCM_DIAGNOSE, DCM_LOGS, DCM_ASSISTANT, DCM_HELP, DCM_QUIT};
static void status_set(Cli *a, const gchar *text) { g_free(a->status); a->status = g_strdup(text); }
static void add(GPtrArray *lines, const gchar *text) { g_ptr_array_add(lines, g_strdup(text)); }
static void log_add(Cli *a, const gchar *text) {
    g_string_append(a->logs, text);
    g_string_append_c(a->logs, '\n');
    if (a->logs->len > 262144) {
        gsize cut = a->logs->len - 262144;
        while (cut < a->logs->len && ((guchar)a->logs->str[cut] & 0xc0) == 0x80) cut++;
        g_string_erase(a->logs, 0, cut);
    }
}
static void page_set(Cli *a, Page page) {
    a->page = page; a->selected = 0; a->offset = 0; a->field = 0;
    g_string_truncate(a->input, 0); g_string_truncate(a->filter, 0);
}
static gboolean matches(const gchar *text, const gchar *filter) {
    gchar *n = dcm_normalize(text), *f = dcm_normalize(filter);
    gboolean match = strstr(n, f) != NULL;
    g_free(n); g_free(f); return match;
}
static GPtrArray *wrap_lines(GPtrArray *lines) {
    int cols, rows;
    dcm_terminal_size(&cols, &rows);
    int width = dcm_render_content_width(cols, rows);
    GPtrArray *wrapped = g_ptr_array_new_with_free_func(g_free);
    for (guint i = 0; i < lines->len; i++) {
        gchar *safe = dcm_terminal_text(g_ptr_array_index(lines, i), G_MAXINT);
        const gchar *p = safe;
        do {
            gchar *part = dcm_terminal_text(p, width);
            g_ptr_array_add(wrapped, part);
            p += strlen(part);
        } while (*p);
        g_free(safe);
    }
    g_ptr_array_unref(lines);
    return wrapped;
}
static const gchar *state_label(DcmComponentState state) {
    switch (state) {
        case DCM_COMPONENT_INSTALLED: return "ON Installed";
        case DCM_COMPONENT_PARTIAL: return "WARN Problem / service inactive";
        case DCM_COMPONENT_NOT_INSTALLED: return "OFF Not installed";
        default: return "? Unknown (available, no detection rule)";
    }
}
static void refresh_states(Cli *a) {
    g_array_set_size(a->states, 0);
    for (guint i = 0; i < a->components->len; i++) {
        DcmComponentState state = dcm_component_state(a->ctx, g_ptr_array_index(a->components, i));
        g_array_append_val(a->states, state);
    }
}
static void diagnostic(Cli *a) {
    refresh_states(a);
    log_add(a, "=== Component diagnosis (shared backend) ===");
    for (guint i = 0; i < a->components->len; i++) {
        DcmComponent *c = g_ptr_array_index(a->components, i);
        gchar *line = g_strdup_printf("%s: %s | %s", c->name,
            state_label(g_array_index(a->states, DcmComponentState, i)), c->required ? "Required" : "Optional");
        log_add(a, line); g_free(line);
    }
    page_set(a, LOGS); status_set(a, "Diagnosis complete. Scroll to review component states.");
}
static gpointer job_run(gpointer data) {
    Cli *a = data;
    const gchar *args[] = {a->job_arg, NULL};
    GError *error = NULL;
    DcmCommandResult *result = dcm_run_capture_bounded(a->ctx, "update.sh", args, a->cancel, &error);
    g_mutex_lock(&a->mutex);
    a->result = result; a->error = error; a->done = TRUE;
    g_mutex_unlock(&a->mutex);
    return NULL;
}
static void job_start(Cli *a, gboolean dry_run) {
    if (a->thread) { status_set(a, "A check is already running. You can browse other screens."); return; }
    a->job_arg = dry_run ? "--dry-run" : "--check";
    a->cancel = g_cancellable_new(); a->done = FALSE;
    status_set(a, dry_run ? "Simulating update... No changes will be applied." : "Checking for updates... You can keep browsing.");
    log_add(a, dry_run ? "=== update.sh --dry-run ===" : "=== update.sh --check ===");
    a->thread = g_thread_new("dcm-check", job_run, a);
    page_set(a, LOGS);
}
static gboolean job_collect(Cli *a) {
    if (!a->thread) return FALSE;
    g_mutex_lock(&a->mutex); gboolean done = a->done; g_mutex_unlock(&a->mutex);
    if (!done) return FALSE;
    g_thread_join(a->thread); a->thread = NULL;
    if (a->error) {
        status_set(a, "Check could not finish. See logs for the exact reason.");
        log_add(a, a->error->message); g_clear_error(&a->error);
    } else {
        const gchar *out = a->result->output;
        gchar *normal = dcm_normalize(out);
        if (strstr(normal, "checkout modifie")) {
            status_set(a, "Local changes detected. Check / dry-run remain available.");
            log_add(a, "WARN Update unavailable: local checkout changes. This read-only action did not apply an update.");
        } else if (strstr(normal, "divergent") || strstr(normal, "divergente")) {
            status_set(a, "Development checkout detected. Automatic update unavailable.");
            log_add(a, "WARN Local history differs from the update branch. No update was applied. Branch/revision details follow.");
        } else status_set(a, a->result->exit_code ?
            "Check could not finish. Read the reason in Logs; retry after resolving it." : "Read-only operation complete. Results are in Logs.");
        log_add(a, out); g_free(normal);
        dcm_command_result_free(a->result); a->result = NULL;
    }
    g_clear_object(&a->cancel);
    return TRUE;
}
static gchar *manager_update_wrapper(Cli *a) {
    gchar *canonical = g_build_filename(a->ctx->repo_root,
        "apps", "system-tools", "custom-manager", "scripts", "update-wrapper.sh", NULL);
    if (g_file_test(canonical, G_FILE_TEST_IS_REGULAR)) return canonical;
    g_free(canonical);
    return g_build_filename(a->ctx->repo_root, "manager", "scripts", "update-wrapper.sh", NULL);
}
static void prepare_launch(Cli *a, const gchar *script, gboolean rollback) {
    if (a->thread) { status_set(a, "Wait for the current check before starting an interactive operation."); return; }
    if (!script || !*script) { status_set(a, "This action is not registered for this component."); return; }
    g_free(a->pending_script); a->pending_script = g_strdup(script); a->rollback = rollback;
    a->previous = a->page; page_set(a, CONFIRM);
    status_set(a, "Review the action. Press y to launch; Esc cancels.");
}
static void launch_pending(Cli *a) {
    const gchar *args[] = {"--rollback", NULL};
    GError *error = NULL;
    gboolean ok = dcm_launch_interactive(a->ctx, a->pending_script, a->rollback ? args : NULL, &error);
    page_set(a, LOGS);
    if (ok) { status_set(a, "Launched in a separate terminal. Follow its prompts and result there.");
        log_add(a, "Interactive action launched (completion is reported in its terminal)."); }
    else { status_set(a, "Could not open a terminal. See Logs."); log_add(a, error->message); g_clear_error(&error); }
}
static void route(Cli *a, DcmRoute r) {
    switch (r.intent) {
        case DCM_OVERVIEW: page_set(a, OVERVIEW); break;
        case DCM_COMPONENTS: page_set(a, COMPONENTS); break;
        case DCM_CHECK: job_start(a, FALSE); break;
        case DCM_DRY_RUN: job_start(a, TRUE); break;
        case DCM_DEPENDENCIES: page_set(a, DEPENDENCIES); break;
        case DCM_DIAGNOSE: diagnostic(a); break;
        case DCM_LOGS: page_set(a, LOGS); break;
        case DCM_ASSISTANT: page_set(a, ASSISTANT); break;
        case DCM_HELP: page_set(a, HELP); break;
        case DCM_QUIT: a->running = FALSE; break;
        case DCM_INSTALL: {
            DcmComponent *c = g_ptr_array_index(a->components, r.component);
            a->component = r.component; prepare_launch(a, c->install_script, FALSE); break;
        }
        case DCM_OPEN:
            a->component = r.component; page_set(a, ACTIONS);
            status_set(a, "Component actions opened. No application launcher is registered."); break;
        case DCM_UPDATE: {
            gchar *script = manager_update_wrapper(a);
            prepare_launch(a, script, FALSE);
            g_free(script);
            break;
        }
        case DCM_ROLLBACK: {
            gchar *script = manager_update_wrapper(a);
            prepare_launch(a, script, TRUE);
            g_free(script);
            break;
        }
        default: status_set(a, "Unknown request. Try 'show components', 'check updates' or 'help'."); break;
    }
}
/* Entries map display rows to trusted action identifiers, never shell strings. */
static GPtrArray *content(Cli *a, GArray *ids) {
    GPtrArray *lines = g_ptr_array_new_with_free_func(g_free);
    if (a->page == MENU || a->page == COMPONENTS) {
        guint count = a->page == MENU ? G_N_ELEMENTS(menu) : a->components->len;
        for (guint i = 0; i < count; i++) {
            DcmComponent *c = a->page == COMPONENTS ? g_ptr_array_index(a->components, i) : NULL;
            const gchar *label = c ? c->name : menu[i];
            if (!matches(label, a->filter->str)) continue;
            gchar *line = c ? g_strdup_printf("%s | %s | %s", label,
                state_label(g_array_index(a->states, DcmComponentState, i)), c->required ? "Required" : "Optional") : g_strdup(label);
            g_ptr_array_add(lines, line); g_array_append_val(ids, i);
        }
        if (!lines->len) add(lines, "No matches. Esc clears the filter.");
    } else if (a->page == ACTIONS) {
        DcmComponent *c = g_ptr_array_index(a->components, a->component);
        add(lines, c->name); add(lines, c->description);
        add(lines, state_label(g_array_index(a->states, DcmComponentState, a->component)));
        add(lines, c->required ? "Required component" : "Optional component");
        add(lines, "");
        if (c->install_script && *c->install_script) add(lines, "[i] Install (opens existing installer)");
        if (c->repair_script && *c->repair_script) add(lines, "[r] Repair");
        if (!c->required && c->uninstall_script && *c->uninstall_script) add(lines, "[u] Uninstall");
        if (c->details && *c->details) add(lines, "[d] Details (read documentation)");
        add(lines, "[f] Refresh component states");
        add(lines, "Actions appear only when registered. Esc: components.");
    } else if (a->page == OVERVIEW) {
        add(lines, "Welcome. Manage your Debian + Hyprland desktop.");
        add(lines, a->ctx->repo_root); add(lines, "");
        for (guint i = 0; i < a->components->len; i++) {
            DcmComponent *c = g_ptr_array_index(a->components, i);
            gchar *line = g_strdup_printf("%s: %s", c->name,
                state_label(g_array_index(a->states, DcmComponentState, i)));
            g_ptr_array_add(lines, line);
        }
        add(lines, ""); add(lines, "[u] Apply update   [r] Rollback (external terminal)");
        add(lines, "[f] Refresh states   :check / :dry-run for preview");
    } else if (a->page == DEPENDENCIES) {
        const gchar *names[] = {"bash", "git", "systemctl", "pkg-config", "gcc", "cargo", "hyprctl"};
        add(lines, "System & dependencies");
        gchar *os = g_get_os_info(G_OS_INFO_KEY_PRETTY_NAME);
        add(lines, os ? os : "Linux"); g_free(os);
        for (guint i = 0; i < G_N_ELEMENTS(names); i++) {
            gchar *path = g_find_program_in_path(names[i]);
            gchar *line = g_strdup_printf("%s: %s%s", names[i], path ? "Available" : "Missing",
                i < 3 ? " (required by repository)" : " (optional / build tool)");
            g_ptr_array_add(lines, line); g_free(path);
        }
    } else if (a->page == LOGS) {
        gchar **rows = g_strsplit(a->logs->len ? a->logs->str : "No output yet. Try :check or :diagnose.", "\n", -1);
        for (guint i = 0; rows[i]; i++) add(lines, rows[i]);
        g_strfreev(rows);
    } else if (a->page == ASSISTANT) {
        add(lines, "local command router / no network AI");
        add(lines, "");
        add(lines, "Manager / current status");
        add(lines, a->status);
        add(lines, "");
        if (a->history->len) {
            add(lines, "You / recent requests");
            for (guint i = a->history->len > 2 ? a->history->len - 2 : 0; i < a->history->len; i++)
                add(lines, g_ptr_array_index(a->history, i));
        } else {
            add(lines, "Try: check updates / show components");
            add(lines, "Ou : montre les composants / aide");
        }
    } else if (a->page == HELP) {
        const gchar *help[] = {"Keyboard & local assistant", "Up/Down: navigate or scroll. Enter: select.",
            "Tab: Menu / Assistant. Esc: back; menu: exit.", "q: exit outside text fields. Ctrl+L: redraw.",
            "/: filter menu or components. Esc: cancel filter.", ": command palette. No shell commands are accepted.",
            "Logs: PageUp/PageDown, Home/End, Up/Down.", "", ":overview :components :check :dry-run",
            ":dependencies :diagnose :logs :assistant :help :quit", ":update / :rollback: review, then external terminal.",
            "", "Assistant accepts English and French phrases:", "check updates / verifie les mises a jour",
            "show logs / montre les journaux", "install mpvpaper / installer mpvpaper",
            "open mpvpaper opens its registered action panel.", "No app launcher is invented. No remote AI.",
            "", "--no-animation disables motion. NO_COLOR disables color."};
        for (guint i = 0; i < G_N_ELEMENTS(help); i++) add(lines, help[i]);
    } else if (a->page == CONFIRM) {
        add(lines, "Launch interactive repository action?"); add(lines, a->pending_script);
        if (a->rollback) add(lines, "Argument: --rollback");
        add(lines, ""); add(lines, "This may modify your installation.");
        add(lines, "The existing script handles sudo in another terminal.");
        add(lines, "[y] Launch     [Esc] Cancel");
    }
    return ids->len ? lines : wrap_lines(lines);
}
static void details(Cli *a, DcmComponent *c) {
    if (!c->details || !*c->details) return;
    gchar *path = g_build_filename(a->ctx->repo_root, c->details, NULL);
    GFile *file = g_file_new_for_path(path);
    GError *error = NULL;
    GFileInputStream *stream = g_file_read(file, NULL, &error);
    if (stream) {
        char buffer[65537]; gsize count = 0;
        if (g_input_stream_read_all(G_INPUT_STREAM(stream), buffer, sizeof(buffer)-1, &count, NULL, &error)) {
            buffer[count] = 0; gchar *valid = g_utf8_make_valid(buffer, count); log_add(a, valid); g_free(valid);
            if (count == sizeof(buffer)-1) log_add(a, "[Documentation preview limited to 64 KiB]");
        }
        g_object_unref(stream);
    }
    if (error) { log_add(a, error->message); g_clear_error(&error); }
    page_set(a, LOGS); status_set(a, "Documentation preview. Scroll with arrows / PageUp / PageDown.");
    g_object_unref(file); g_free(path);
}
static void text_key(Cli *a, int key) {
    if (key == 27) { a->field = 0; g_string_truncate(a->input, 0); g_string_truncate(a->filter, 0);
        if (a->page == ASSISTANT) page_set(a, MENU);
    } else if (key == 127 || key == 8) {
        if (a->input->len) {
            gchar *last = g_utf8_find_prev_char(a->input->str, a->input->str + a->input->len);
            g_string_truncate(a->input, last ? (gsize)(last - a->input->str) : 0);
        }
    } else if (key == '\r' || key == '\n') {
        if (!g_utf8_validate(a->input->str, -1, NULL)) { status_set(a, "Please enter valid UTF-8 text."); return; }
        if (a->field == '/') { a->field = 0; return; }
        gchar *request = g_strdup(a->input->str);
        DcmRoute r = dcm_assistant_route(request, a->components);
        if (a->history->len >= 5) g_ptr_array_remove_index(a->history, 0);
        g_ptr_array_add(a->history, g_strdup(request));
        gchar *notice = g_strdup_printf("Request: %s", request); log_add(a, notice); g_free(notice);
        g_string_truncate(a->input, 0); a->field = 0;
        route(a, r); g_free(request);
    } else if (key >= 32 && key < 256 && a->input->len < 512) g_string_append_c(a->input, (char)key);
    if (a->field == '/' && g_utf8_validate(a->input->str, -1, NULL)) {
        g_string_assign(a->filter, a->input->str); a->selected = 0; a->offset = 0;
    }
}
int dcm_cli_options(int argc, char **argv, gboolean *animate) {
    gboolean cli = FALSE, no_animation = FALSE;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--cli") || !strcmp(argv[i], "--interactive")) cli = TRUE;
        if (!strcmp(argv[i], "--no-animation")) no_animation = TRUE;
    }
    if (!cli && !no_animation) return 0;
    for (int i = 1; i < argc; i++)
        if (strcmp(argv[i], "--cli") && strcmp(argv[i], "--interactive") && strcmp(argv[i], "--no-animation")) return -1;
    *animate = !no_animation;
    return cli ? 1 : -1;
}
int dcm_cli_run(gboolean animate) {
    if (!isatty(STDIN_FILENO) || !isatty(STDOUT_FILENO) || !g_strcmp0(g_getenv("TERM"), "dumb")) {
        fputs("Interactive CLI requires a terminal (TERM other than dumb). Use --diagnose for plain output.\n", stderr);
        return 2;
    }
    Cli a = {0}; GError *error = NULL;
    a.ctx = dcm_context_new(&error);
    if (a.ctx) a.components = dcm_components_load(a.ctx->components_file, &error);
    if (!a.components) { fprintf(stderr, "%s\n", error->message); g_clear_error(&error); dcm_context_free(a.ctx); return 2; }
    a.states = g_array_new(FALSE, FALSE, sizeof(DcmComponentState)); refresh_states(&a);
    a.input = g_string_new(NULL); a.filter = g_string_new(NULL); a.logs = g_string_new(NULL);
    a.history = g_ptr_array_new_with_free_func(g_free); a.status = g_strdup("Ready. Select an action or press Tab for the local assistant.");
    a.running = TRUE; a.animate = animate;
    a.renderer.color = dcm_color_mode(g_getenv("TERM"), g_getenv("COLORTERM"), g_getenv("NO_COLOR"));
    g_mutex_init(&a.mutex);
    struct sigaction action = {0}, old_int, old_term, old_resize, old_hup;
    action.sa_handler = on_signal; sigemptyset(&action.sa_mask);
    stop_requested = 0; resized = 0;
    sigaction(SIGINT, &action, &old_int); sigaction(SIGTERM, &action, &old_term);
    sigaction(SIGHUP, &action, &old_hup); sigaction(SIGWINCH, &action, &old_resize);
    gboolean entered = dcm_terminal_enter();
    if (!entered) { fputs("Unable to configure terminal.\n", stderr); a.running = FALSE; }
    gboolean dirty = TRUE, full = TRUE; guint frame = 0;
    gint64 next_frame = g_get_monotonic_time();
    while (a.running && !stop_requested) {
        if (job_collect(&a)) dirty = TRUE;
        if (resized) { full = dirty = TRUE; resized = 0; }
        gint64 now = g_get_monotonic_time();
        if (animate && now >= next_frame) { frame++; dirty = TRUE; next_frame = now + 100000; }
        GArray *ids = g_array_new(FALSE, FALSE, sizeof(guint));
        GPtrArray *lines = content(&a, ids);
        int cols, height; dcm_terminal_size(&cols, &height);
        int visible = dcm_render_body_rows(height, a.field || a.page == ASSISTANT);
        a.selected = CLAMP(a.selected, 0, MAX(0, (int)ids->len - 1));
        if (ids->len) {
            if (a.selected < a.offset) a.offset = a.selected;
            if (a.selected >= a.offset + visible) a.offset = a.selected - visible + 1;
        }
        a.offset = CLAMP(a.offset, 0, MAX(0, (int)lines->len - visible));
        if (dirty) {
            const gchar *modes[] = {"MENU", "OVERVIEW", "COMPONENTS", "ACTIONS", "DEPENDENCIES", "LOGS", "ASSISTANT", "HELP", "CONFIRM"};
            gchar *prompt = (a.field || a.page == ASSISTANT) ? g_strdup_printf(" %s%s_", a.field == '/' ? "Filter / " : a.field == ':' ? ": " : "Ask > ", a.input->str) : NULL;
            dcm_render(&a.renderer, lines, modes[a.page], a.status, prompt,
                ids->len ? a.selected : -1, a.offset, frame, a.thread != NULL, full);
            g_free(prompt); dirty = full = FALSE;
        }
        int timeout = animate ? MAX(1, (int)((next_frame - g_get_monotonic_time() + 999) / 1000)) : a.thread ? 100 : -1;
        int key = dcm_key_read(timeout);
        if (key == DCM_KEY_EOF || key == 4) a.running = FALSE;
        else if (key == 12) full = dirty = TRUE;
        else if (key == '\t') { page_set(&a, a.page == ASSISTANT ? MENU : ASSISTANT); dirty = TRUE; }
        else if (key != DCM_KEY_NONE) {
            dirty = TRUE;
            if (a.field == '/' && key == DCM_KEY_DOWN) a.selected++;
            else if (a.field == '/' && key == DCM_KEY_UP) a.selected--;
            else if (a.field == '/' && (key == '\r' || key == '\n') && ids->len) {
                guint id = g_array_index(ids, guint, a.selected);
                a.field = 0;
                if (a.page == MENU) route(&a, (DcmRoute){menu_intents[id], -1});
                else { a.component = id; page_set(&a, ACTIONS); }
            }
            else if (a.field || a.page == ASSISTANT) text_key(&a, key);
            else if (key == 'q') a.running = FALSE;
            else if (key == 27) {
                if (a.filter->len) { g_string_truncate(a.filter, 0); g_string_truncate(a.input, 0); }
                else if (a.page == MENU) a.running = FALSE;
                else page_set(&a, a.page == ACTIONS ? COMPONENTS : a.page == CONFIRM ? a.previous : MENU);
            } else if (key == ':') { a.field = ':'; g_string_truncate(a.input, 0); }
            else if (key == '/' && (a.page == MENU || a.page == COMPONENTS)) { a.field = '/'; g_string_truncate(a.input, 0); }
            else if (key == '?') page_set(&a, HELP);
            else if (key == DCM_KEY_UP) { if (ids->len) a.selected--; else a.offset--; }
            else if (key == DCM_KEY_DOWN) { if (ids->len) a.selected++; else a.offset++; }
            else if (key == DCM_KEY_PAGE_UP) { if (ids->len) a.selected -= visible; else a.offset -= visible; }
            else if (key == DCM_KEY_PAGE_DOWN) { if (ids->len) a.selected += visible; else a.offset += visible; }
            else if (key == DCM_KEY_HOME) { a.selected = a.offset = 0; }
            else if (key == DCM_KEY_END) { a.selected = (int)ids->len - 1; a.offset = (int)lines->len - visible; }
            else if (a.page == CONFIRM && key == 'y') launch_pending(&a);
            else if (a.page == MENU && key >= '0' && key <= '9') route(&a, (DcmRoute){menu_intents[key == '0' ? 9 : key - '1'], -1});
            else if ((key == '\r' || key == '\n') && ids->len) {
                guint id = g_array_index(ids, guint, a.selected);
                if (a.page == MENU) route(&a, (DcmRoute){menu_intents[id], -1});
                else { a.component = id; page_set(&a, ACTIONS); }
            } else if (a.page == OVERVIEW) {
                if (key == 'u' || key == 'r') {
                    gchar *script = manager_update_wrapper(&a);
                    prepare_launch(&a, script, key == 'r');
                    g_free(script);
                }
                if (key == 'f') refresh_states(&a);
            } else if (a.page == ACTIONS) {
                DcmComponent *c = g_ptr_array_index(a.components, a.component);
                if (key == 'i') prepare_launch(&a, c->install_script, FALSE);
                if (key == 'r') prepare_launch(&a, c->repair_script, FALSE);
                if (key == 'u' && !c->required) prepare_launch(&a, c->uninstall_script, FALSE);
                if (key == 'd') details(&a, c);
                if (key == 'f') refresh_states(&a);
            }
        }
        g_ptr_array_unref(lines); g_array_unref(ids);
    }
    dcm_terminal_leave();
    if (a.thread) { g_cancellable_cancel(a.cancel); g_thread_join(a.thread);
        dcm_command_result_free(a.result); g_clear_error(&a.error); g_clear_object(&a.cancel); }
    sigaction(SIGINT, &old_int, NULL); sigaction(SIGTERM, &old_term, NULL);
    sigaction(SIGHUP, &old_hup, NULL); sigaction(SIGWINCH, &old_resize, NULL);
    dcm_renderer_clear(&a.renderer); g_mutex_clear(&a.mutex);
    g_free(a.status); g_free(a.pending_script);
    g_string_free(a.input, TRUE); g_string_free(a.filter, TRUE); g_string_free(a.logs, TRUE);
    g_ptr_array_unref(a.history); g_array_unref(a.states);
    g_ptr_array_unref(a.components); dcm_context_free(a.ctx);
    return stop_requested ? 128 + stop_requested : entered ? 0 : 2;
}
