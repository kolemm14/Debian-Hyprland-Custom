#include "ui.h"

#include "component.h"
#include "paths.h"
#include "runner.h"

#include <gio/gio.h>
#include <string.h>

typedef struct {
    GtkApplication *application;
    DcmContext *ctx;
    GPtrArray *components;
    GtkWidget *window;
    GtkWidget *summary_label;
    GtkWidget *update_label;
    GtkWidget *component_list;
    GtkTextBuffer *log_buffer;
    gint ref_count;
    gboolean closing;
} DcmApp;

typedef struct {
    DcmApp *app;
    DcmComponent *component;
} ComponentAction;

typedef struct {
    DcmApp *app;
    gchar *program;
    gchar **args;
    gchar *title;
} AsyncCommand;

static DcmApp *app_ref(DcmApp *app) {
    g_atomic_int_inc(&app->ref_count);
    return app;
}

static void app_unref(DcmApp *app) {
    if (!app) return;
    if (!g_atomic_int_dec_and_test(&app->ref_count)) return;
    if (app->components) g_ptr_array_unref(app->components);
    dcm_context_free(app->ctx);
    g_free(app);
}

static void append_log(DcmApp *app, const gchar *title, const gchar *text) {
    GtkTextIter end;
    gtk_text_buffer_get_end_iter(app->log_buffer, &end);
    gchar *header = g_strdup_printf("\n=== %s ===\n", title ? title : "Commande");
    gtk_text_buffer_insert(app->log_buffer, &end, header, -1);
    gtk_text_buffer_insert(app->log_buffer, &end, text ? text : "", -1);
    if (text && *text && text[strlen(text) - 1] != '\n')
        gtk_text_buffer_insert(app->log_buffer, &end, "\n", -1);
    g_free(header);
}

static void show_error(DcmApp *app, const gchar *message) {
    GtkWidget *dialog = gtk_message_dialog_new(GTK_WINDOW(app->window),
        GTK_DIALOG_MODAL | GTK_DIALOG_DESTROY_WITH_PARENT,
        GTK_MESSAGE_ERROR, GTK_BUTTONS_CLOSE, "%s", message);
    gtk_dialog_run(GTK_DIALOG(dialog));
    gtk_widget_destroy(dialog);
}

static GtkWidget *section_title(const gchar *text) {
    GtkWidget *label = gtk_label_new(NULL);
    gchar *markup = g_markup_printf_escaped("<span size='x-large' weight='bold'>%s</span>", text);
    gtk_label_set_markup(GTK_LABEL(label), markup);
    gtk_label_set_xalign(GTK_LABEL(label), 0.0f);
    g_free(markup);
    return label;
}

static GtkWidget *muted_label(const gchar *text) {
    GtkWidget *label = gtk_label_new(text);
    gtk_label_set_xalign(GTK_LABEL(label), 0.0f);
    gtk_label_set_line_wrap(GTK_LABEL(label), TRUE);
    gtk_style_context_add_class(gtk_widget_get_style_context(label), "dim-label");
    return label;
}

static void open_details(GtkButton *button, gpointer user_data) {
    (void)button;
    ComponentAction *action = user_data;
    const gchar *details = action->component->details;
    if (!details || !*details) return;

    gchar *uri = NULL;
    if (g_str_has_prefix(details, "http://") || g_str_has_prefix(details, "https://")) {
        uri = g_strdup(details);
    } else {
        gchar *path = g_build_filename(action->app->ctx->repo_root, details, NULL);
        uri = g_filename_to_uri(path, NULL, NULL);
        g_free(path);
    }
    if (uri) {
        GError *error = NULL;
        if (!gtk_show_uri_on_window(GTK_WINDOW(action->app->window), uri,
                                    GDK_CURRENT_TIME, &error)) {
            show_error(action->app, error->message);
            g_clear_error(&error);
        }
        g_free(uri);
    }
}

static void launch_component_script(GtkButton *button, gpointer user_data) {
    ComponentAction *action = user_data;
    const gchar *kind = g_object_get_data(G_OBJECT(button), "dcm-action-kind");
    const gchar *script = NULL;

    if (g_strcmp0(kind, "install") == 0) script = action->component->install_script;
    else if (g_strcmp0(kind, "uninstall") == 0) script = action->component->uninstall_script;
    else if (g_strcmp0(kind, "repair") == 0) script = action->component->repair_script;

    if (!script || !*script) return;
    GError *error = NULL;
    if (!dcm_launch_interactive(action->app->ctx, script, NULL, &error)) {
        show_error(action->app, error->message);
        g_clear_error(&error);
    }
}

static GtkWidget *component_row(DcmApp *app, DcmComponent *component) {
    DcmComponentState state = dcm_component_state(app->ctx, component);
    GtkWidget *row = gtk_list_box_row_new();
    GtkWidget *box = gtk_box_new(GTK_ORIENTATION_VERTICAL, 6);
    gtk_container_set_border_width(GTK_CONTAINER(box), 14);
    gtk_container_add(GTK_CONTAINER(row), box);

    GtkWidget *top = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 10);
    gtk_box_pack_start(GTK_BOX(box), top, FALSE, FALSE, 0);

    GtkWidget *name = gtk_label_new(NULL);
    gchar *name_markup = g_markup_printf_escaped("<b>%s</b>%s", component->name,
        component->required ? "  <small>(indispensable)</small>" : "");
    gtk_label_set_markup(GTK_LABEL(name), name_markup);
    gtk_label_set_xalign(GTK_LABEL(name), 0.0f);
    gtk_box_pack_start(GTK_BOX(top), name, TRUE, TRUE, 0);
    g_free(name_markup);

    GtkWidget *state_label = gtk_label_new(dcm_component_state_label(state));
    gtk_style_context_add_class(gtk_widget_get_style_context(state_label), "dim-label");
    gtk_box_pack_end(GTK_BOX(top), state_label, FALSE, FALSE, 0);

    GtkWidget *desc = muted_label(component->description);
    gtk_box_pack_start(GTK_BOX(box), desc, FALSE, FALSE, 0);

    GtkWidget *actions = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 6);
    gtk_box_pack_start(GTK_BOX(box), actions, FALSE, FALSE, 0);

    ComponentAction *ctx = g_new0(ComponentAction, 1);
    ctx->app = app;
    ctx->component = component;
    g_object_set_data_full(G_OBJECT(row), "dcm-component-action", ctx, g_free);

    if (component->install_script && *component->install_script &&
        state != DCM_COMPONENT_INSTALLED) {
        GtkWidget *button = gtk_button_new_with_label("Installer");
        g_object_set_data(G_OBJECT(button), "dcm-action-kind", "install");
        g_signal_connect(button, "clicked", G_CALLBACK(launch_component_script), ctx);
        gtk_box_pack_start(GTK_BOX(actions), button, FALSE, FALSE, 0);
    }
    if (component->repair_script && *component->repair_script &&
        state == DCM_COMPONENT_PARTIAL) {
        GtkWidget *button = gtk_button_new_with_label("Réparer");
        g_object_set_data(G_OBJECT(button), "dcm-action-kind", "repair");
        g_signal_connect(button, "clicked", G_CALLBACK(launch_component_script), ctx);
        gtk_box_pack_start(GTK_BOX(actions), button, FALSE, FALSE, 0);
    }
    if (!component->required && component->uninstall_script && *component->uninstall_script &&
        (state == DCM_COMPONENT_INSTALLED || state == DCM_COMPONENT_PARTIAL)) {
        GtkWidget *button = gtk_button_new_with_label("Désinstaller");
        g_object_set_data(G_OBJECT(button), "dcm-action-kind", "uninstall");
        g_signal_connect(button, "clicked", G_CALLBACK(launch_component_script), ctx);
        gtk_box_pack_start(GTK_BOX(actions), button, FALSE, FALSE, 0);
    }
    if (component->details && *component->details) {
        GtkWidget *button = gtk_button_new_with_label("En savoir plus");
        g_signal_connect(button, "clicked", G_CALLBACK(open_details), ctx);
        gtk_box_pack_end(GTK_BOX(actions), button, FALSE, FALSE, 0);
    }

    return row;
}

static void refresh_components(DcmApp *app) {
    GList *children = gtk_container_get_children(GTK_CONTAINER(app->component_list));
    for (GList *it = children; it; it = it->next) gtk_widget_destroy(GTK_WIDGET(it->data));
    g_list_free(children);

    guint installed = 0, partial = 0, optional_missing = 0;
    for (guint i = 0; i < app->components->len; ++i) {
        DcmComponent *component = g_ptr_array_index(app->components, i);
        DcmComponentState state = dcm_component_state(app->ctx, component);
        if (state == DCM_COMPONENT_INSTALLED) installed++;
        else if (state == DCM_COMPONENT_PARTIAL) partial++;
        else if (!component->required && state == DCM_COMPONENT_NOT_INSTALLED) optional_missing++;
        GtkWidget *row = component_row(app, component);
        gtk_container_add(GTK_CONTAINER(app->component_list), row);
    }
    gtk_widget_show_all(app->component_list);

    gchar *summary = g_strdup_printf(
        "%u composant(s) installé(s) • %u à vérifier • %u optionnel(s) non installé(s)",
        installed, partial, optional_missing);
    gtk_label_set_text(GTK_LABEL(app->summary_label), summary);
    g_free(summary);
}

static void async_command_free(AsyncCommand *cmd) {
    if (!cmd) return;
    app_unref(cmd->app);
    g_free(cmd->program);
    g_strfreev(cmd->args);
    g_free(cmd->title);
    g_free(cmd);
}

static void command_thread(GTask *task, gpointer source_object, gpointer task_data,
                           GCancellable *cancellable) {
    (void)source_object;
    (void)cancellable;
    AsyncCommand *cmd = task_data;
    GError *error = NULL;
    DcmCommandResult *result = dcm_run_capture(cmd->app->ctx, cmd->program,
                                               (const gchar *const *)cmd->args, &error);
    if (error) g_task_return_error(task, error);
    else g_task_return_pointer(task, result, (GDestroyNotify)dcm_command_result_free);
}

static void command_done(GObject *source, GAsyncResult *res, gpointer user_data) {
    (void)source;
    AsyncCommand *cmd = user_data;
    GError *error = NULL;
    DcmCommandResult *result = g_task_propagate_pointer(G_TASK(res), &error);
    if (error) {
        if (!cmd->app->closing) {
            show_error(cmd->app, error->message);
            append_log(cmd->app, cmd->title, error->message);
        }
        g_clear_error(&error);
    } else {
        if (!cmd->app->closing) {
            append_log(cmd->app, cmd->title, result->output);
            if (g_strcmp0(cmd->title, "Vérification des mises à jour") == 0) {
                if (strstr(result->output, "Mise à jour disponible"))
                    gtk_label_set_text(GTK_LABEL(cmd->app->update_label), "Mise à jour disponible");
                else if (strstr(result->output, "à jour") || strstr(result->output, "Aucune mise à jour"))
                    gtk_label_set_text(GTK_LABEL(cmd->app->update_label), "Système à jour");
                else
                    gtk_label_set_text(GTK_LABEL(cmd->app->update_label), "Résultat disponible dans les journaux");
            }
        }
        dcm_command_result_free(result);
    }
    async_command_free(cmd);
}

static void run_async(DcmApp *app, const gchar *program, const gchar *const *args,
                      const gchar *title) {
    AsyncCommand *cmd = g_new0(AsyncCommand, 1);
    cmd->app = app_ref(app);
    cmd->program = g_strdup(program);
    cmd->args = args ? g_strdupv((gchar **)args) : NULL;
    cmd->title = g_strdup(title);

    GTask *task = g_task_new(NULL, NULL, command_done, cmd);
    g_task_set_task_data(task, cmd, NULL);
    g_task_run_in_thread(task, command_thread);
    g_object_unref(task);
}

static void check_updates(GtkButton *button, gpointer user_data) {
    (void)button;
    DcmApp *app = user_data;
    const gchar *args[] = {"--check", NULL};
    gtk_label_set_text(GTK_LABEL(app->update_label), "Vérification…");
    run_async(app, "update.sh", args, "Vérification des mises à jour");
}

static void dry_run(GtkButton *button, gpointer user_data) {
    (void)button;
    DcmApp *app = user_data;
    const gchar *args[] = {"--dry-run", NULL};
    run_async(app, "update.sh", args, "Simulation de mise à jour");
}

static void interactive_update(GtkButton *button, gpointer user_data) {
    DcmApp *app = user_data;
    const gchar *mode = g_object_get_data(G_OBJECT(button), "dcm-update-mode");
    const gchar *args_apply[] = {NULL};
    const gchar *args_rollback[] = {"--rollback", NULL};
    const gchar *const *args = g_strcmp0(mode, "rollback") == 0 ? args_rollback : args_apply;
    GError *error = NULL;
    if (!dcm_launch_interactive(app->ctx, "apps/system-tools/custom-apps/system-tools/custom-manager/scripts/update-wrapper.sh", args, &error)) {
        show_error(app, error->message);
        g_clear_error(&error);
    }
}

static void refresh_clicked(GtkButton *button, gpointer user_data) {
    (void)button;
    DcmApp *app = user_data;
    refresh_components(app);
}

static GtkWidget *build_dashboard(DcmApp *app) {
    GtkWidget *box = gtk_box_new(GTK_ORIENTATION_VERTICAL, 14);
    gtk_container_set_border_width(GTK_CONTAINER(box), 20);
    gtk_box_pack_start(GTK_BOX(box), section_title("Vue d’ensemble"), FALSE, FALSE, 0);

    gchar *repo_text = g_strdup_printf("Dépôt : %s", app->ctx->repo_root);
    gtk_box_pack_start(GTK_BOX(box), muted_label(repo_text), FALSE, FALSE, 0);
    g_free(repo_text);

    app->summary_label = muted_label("Analyse des composants…");
    gtk_box_pack_start(GTK_BOX(box), app->summary_label, FALSE, FALSE, 0);

    GtkWidget *separator = gtk_separator_new(GTK_ORIENTATION_HORIZONTAL);
    gtk_box_pack_start(GTK_BOX(box), separator, FALSE, FALSE, 6);

    gtk_box_pack_start(GTK_BOX(box), section_title("Mises à jour"), FALSE, FALSE, 0);
    app->update_label = gtk_label_new("État non vérifié");
    gtk_label_set_xalign(GTK_LABEL(app->update_label), 0.0f);
    gtk_box_pack_start(GTK_BOX(box), app->update_label, FALSE, FALSE, 0);

    GtkWidget *buttons = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 8);
    GtkWidget *check = gtk_button_new_with_label("Vérifier");
    GtkWidget *simulate = gtk_button_new_with_label("Simuler");
    GtkWidget *apply = gtk_button_new_with_label("Mettre à jour");
    GtkWidget *rollback = gtk_button_new_with_label("Rollback");
    g_object_set_data(G_OBJECT(apply), "dcm-update-mode", "apply");
    g_object_set_data(G_OBJECT(rollback), "dcm-update-mode", "rollback");
    g_signal_connect(check, "clicked", G_CALLBACK(check_updates), app);
    g_signal_connect(simulate, "clicked", G_CALLBACK(dry_run), app);
    g_signal_connect(apply, "clicked", G_CALLBACK(interactive_update), app);
    g_signal_connect(rollback, "clicked", G_CALLBACK(interactive_update), app);
    gtk_box_pack_start(GTK_BOX(buttons), check, FALSE, FALSE, 0);
    gtk_box_pack_start(GTK_BOX(buttons), simulate, FALSE, FALSE, 0);
    gtk_box_pack_start(GTK_BOX(buttons), apply, FALSE, FALSE, 0);
    gtk_box_pack_start(GTK_BOX(buttons), rollback, FALSE, FALSE, 0);
    gtk_box_pack_start(GTK_BOX(box), buttons, FALSE, FALSE, 0);

    GtkWidget *hint = muted_label(
        "Les simulations restent dans l’interface. Les opérations susceptibles de demander sudo "
        "s’ouvrent dans un terminal afin de conserver une authentification sûre et interactive.");
    gtk_box_pack_start(GTK_BOX(box), hint, FALSE, FALSE, 0);
    return box;
}

static GtkWidget *build_components_page(DcmApp *app) {
    GtkWidget *outer = gtk_box_new(GTK_ORIENTATION_VERTICAL, 10);
    gtk_container_set_border_width(GTK_CONTAINER(outer), 20);
    GtkWidget *header = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 8);
    gtk_box_pack_start(GTK_BOX(header), section_title("Composants"), TRUE, TRUE, 0);
    GtkWidget *refresh = gtk_button_new_with_label("Actualiser");
    g_signal_connect(refresh, "clicked", G_CALLBACK(refresh_clicked), app);
    gtk_box_pack_end(GTK_BOX(header), refresh, FALSE, FALSE, 0);
    gtk_box_pack_start(GTK_BOX(outer), header, FALSE, FALSE, 0);
    gtk_box_pack_start(GTK_BOX(outer), muted_label(
        "Chaque composant reste indépendant. Le Manager détecte son état et appelle son installateur sans intégrer son code."),
        FALSE, FALSE, 0);

    GtkWidget *scroll = gtk_scrolled_window_new(NULL, NULL);
    gtk_scrolled_window_set_policy(GTK_SCROLLED_WINDOW(scroll), GTK_POLICY_NEVER, GTK_POLICY_AUTOMATIC);
    app->component_list = gtk_list_box_new();
    gtk_list_box_set_selection_mode(GTK_LIST_BOX(app->component_list), GTK_SELECTION_NONE);
    gtk_container_add(GTK_CONTAINER(scroll), app->component_list);
    gtk_box_pack_start(GTK_BOX(outer), scroll, TRUE, TRUE, 0);
    return outer;
}

static GtkWidget *dependency_line(const gchar *name, const gchar *purpose, gboolean required) {
    gchar *path = g_find_program_in_path(name);
    const gchar *state = path ? "Disponible" : (required ? "MANQUANT" : "Optionnel absent");
    gchar *text = g_strdup_printf("%s — %s\n%s", name, state, purpose);
    GtkWidget *label = gtk_label_new(text);
    gtk_label_set_xalign(GTK_LABEL(label), 0.0f);
    gtk_label_set_line_wrap(GTK_LABEL(label), TRUE);
    g_free(path);
    g_free(text);
    return label;
}

static GtkWidget *build_dependencies_page(void) {
    GtkWidget *box = gtk_box_new(GTK_ORIENTATION_VERTICAL, 12);
    gtk_container_set_border_width(GTK_CONTAINER(box), 20);
    gtk_box_pack_start(GTK_BOX(box), section_title("Dépendances"), FALSE, FALSE, 0);
    gtk_box_pack_start(GTK_BOX(box), muted_label(
        "Le Manager lui-même reste léger. Les outils ci-dessous servent aux composants et aux opérations du dépôt."),
        FALSE, FALSE, 0);

    struct { const gchar *name; const gchar *purpose; gboolean required; } deps[] = {
        {"bash", "scripts d’installation et de mise à jour", TRUE},
        {"git", "références et mises à jour du dépôt", TRUE},
        {"systemctl", "services utilisateur systemd", TRUE},
        {"pkg-config", "compilation du Manager", FALSE},
        {"gcc", "compilation native", FALSE},
        {"cargo", "composants Rust tels que Pericored/MirrorBridge", FALSE},
        {"hyprctl", "intégration Hyprland", FALSE},
        {NULL, NULL, FALSE}
    };
    for (guint i = 0; deps[i].name; ++i)
        gtk_box_pack_start(GTK_BOX(box), dependency_line(deps[i].name, deps[i].purpose, deps[i].required),
                           FALSE, FALSE, 0);
    return box;
}

static GtkWidget *build_logs_page(DcmApp *app) {
    GtkWidget *box = gtk_box_new(GTK_ORIENTATION_VERTICAL, 10);
    gtk_container_set_border_width(GTK_CONTAINER(box), 20);
    gtk_box_pack_start(GTK_BOX(box), section_title("Journaux"), FALSE, FALSE, 0);
    GtkWidget *scroll = gtk_scrolled_window_new(NULL, NULL);
    GtkWidget *view = gtk_text_view_new();
    gtk_text_view_set_editable(GTK_TEXT_VIEW(view), FALSE);
    gtk_text_view_set_monospace(GTK_TEXT_VIEW(view), TRUE);
    gtk_text_view_set_wrap_mode(GTK_TEXT_VIEW(view), GTK_WRAP_WORD_CHAR);
    app->log_buffer = gtk_text_view_get_buffer(GTK_TEXT_VIEW(view));
    gtk_text_buffer_set_text(app->log_buffer,
        "Les sorties de --check et --dry-run apparaîtront ici.\n", -1);
    gtk_container_add(GTK_CONTAINER(scroll), view);
    gtk_box_pack_start(GTK_BOX(box), scroll, TRUE, TRUE, 0);
    return box;
}

static GtkWidget *build_about_page(DcmApp *app) {
    GtkWidget *box = gtk_box_new(GTK_ORIENTATION_VERTICAL, 12);
    gtk_container_set_border_width(GTK_CONTAINER(box), 20);
    gtk_box_pack_start(GTK_BOX(box), section_title("Debian Custom Manager"), FALSE, FALSE, 0);
    gtk_box_pack_start(GTK_BOX(box), muted_label(
        "Interface centrale de Debian-Hyprland-Custom. Elle orchestre les composants, mais ne remplace ni leurs moteurs ni leurs installateurs."),
        FALSE, FALSE, 0);
    gtk_box_pack_start(GTK_BOX(box), muted_label(
        "Architecture : application native C + GTK3/GLib, sans Electron et sans serveur local. Objectif : faible consommation mémoire et compatibilité avec du matériel ancien."),
        FALSE, FALSE, 0);
    gchar *manifest = g_strdup_printf("Manifest : %s", app->ctx->components_file);
    gtk_box_pack_start(GTK_BOX(box), muted_label(manifest), FALSE, FALSE, 0);
    g_free(manifest);
    return box;
}

static void app_destroy(GtkWidget *widget, gpointer user_data) {
    (void)widget;
    DcmApp *app = user_data;
    app->closing = TRUE;
    app_unref(app);
}

void dcm_activate(GtkApplication *application, gpointer user_data) {
    (void)user_data;
    GError *error = NULL;
    DcmContext *ctx = dcm_context_new(&error);
    if (!ctx) {
        GtkWidget *dialog = gtk_message_dialog_new(NULL, GTK_DIALOG_MODAL,
            GTK_MESSAGE_ERROR, GTK_BUTTONS_CLOSE, "%s", error->message);
        gtk_dialog_run(GTK_DIALOG(dialog));
        gtk_widget_destroy(dialog);
        g_clear_error(&error);
        return;
    }

    GPtrArray *components = dcm_components_load(ctx->components_file, &error);
    if (!components) {
        GtkWidget *dialog = gtk_message_dialog_new(NULL, GTK_DIALOG_MODAL,
            GTK_MESSAGE_ERROR, GTK_BUTTONS_CLOSE, "%s", error->message);
        gtk_dialog_run(GTK_DIALOG(dialog));
        gtk_widget_destroy(dialog);
        g_clear_error(&error);
        dcm_context_free(ctx);
        return;
    }

    DcmApp *app = g_new0(DcmApp, 1);
    app->ref_count = 1;
    app->application = application;
    app->ctx = ctx;
    app->components = components;

    app->window = gtk_application_window_new(application);
    gtk_window_set_default_size(GTK_WINDOW(app->window), 940, 650);
    gtk_window_set_title(GTK_WINDOW(app->window), "Debian Custom Manager");

    GtkWidget *header = gtk_header_bar_new();
    gtk_header_bar_set_title(GTK_HEADER_BAR(header), "Debian Custom Manager");
    gtk_header_bar_set_subtitle(GTK_HEADER_BAR(header), "Debian-Hyprland-Custom");
    gtk_header_bar_set_show_close_button(GTK_HEADER_BAR(header), TRUE);
    gtk_window_set_titlebar(GTK_WINDOW(app->window), header);

    GtkWidget *root = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 0);
    GtkWidget *stack = gtk_stack_new();
    gtk_stack_set_transition_type(GTK_STACK(stack), GTK_STACK_TRANSITION_TYPE_CROSSFADE);
    gtk_stack_set_transition_duration(GTK_STACK(stack), 120);
    GtkWidget *sidebar = gtk_stack_sidebar_new();
    gtk_stack_sidebar_set_stack(GTK_STACK_SIDEBAR(sidebar), GTK_STACK(stack));
    gtk_widget_set_size_request(sidebar, 185, -1);
    gtk_box_pack_start(GTK_BOX(root), sidebar, FALSE, FALSE, 0);
    gtk_box_pack_start(GTK_BOX(root), stack, TRUE, TRUE, 0);

    GtkWidget *dashboard = build_dashboard(app);
    GtkWidget *components_page = build_components_page(app);
    GtkWidget *deps = build_dependencies_page();
    GtkWidget *logs = build_logs_page(app);
    GtkWidget *about = build_about_page(app);
    gtk_stack_add_titled(GTK_STACK(stack), dashboard, "dashboard", "Accueil");
    gtk_stack_add_titled(GTK_STACK(stack), components_page, "components", "Composants");
    gtk_stack_add_titled(GTK_STACK(stack), deps, "dependencies", "Dépendances");
    gtk_stack_add_titled(GTK_STACK(stack), logs, "logs", "Journaux");
    gtk_stack_add_titled(GTK_STACK(stack), about, "about", "À propos");

    gtk_container_add(GTK_CONTAINER(app->window), root);
    g_signal_connect(app->window, "destroy", G_CALLBACK(app_destroy), app);
    refresh_components(app);
    gtk_widget_show_all(app->window);
}
