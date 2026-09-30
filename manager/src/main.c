#include <gtk/gtk.h>
#include <stdio.h>
#include <string.h>

#include "component.h"
#include "paths.h"
#include "ui.h"

#define DCM_VERSION "0.1.0"

static int diagnose(void) {
    GError *error = NULL;
    DcmContext *ctx = dcm_context_new(&error);
    if (!ctx) {
        fprintf(stderr, "ERREUR: %s\n", error ? error->message : "contexte indisponible");
        g_clear_error(&error);
        return 2;
    }

    GPtrArray *components = dcm_components_load(ctx->components_file, &error);
    if (!components) {
        fprintf(stderr, "ERREUR: %s\n", error ? error->message : "manifest indisponible");
        g_clear_error(&error);
        dcm_context_free(ctx);
        return 3;
    }

    printf("Debian Custom Manager %s\n", DCM_VERSION);
    printf("Dépôt   : %s\n", ctx->repo_root);
    printf("Manifest: %s\n\n", ctx->components_file);

    for (guint i = 0; i < components->len; ++i) {
        DcmComponent *component = g_ptr_array_index(components, i);
        DcmComponentState state = dcm_component_state(ctx, component);
        printf("%-20s %-14s %s\n", component->id,
               dcm_component_state_label(state),
               component->required ? "indispensable" : "optionnel");
    }

    g_ptr_array_unref(components);
    dcm_context_free(ctx);
    return 0;
}

int main(int argc, char **argv) {
    if (argc == 2 && strcmp(argv[1], "--version") == 0) {
        printf("debian-custom-manager %s\n", DCM_VERSION);
        return 0;
    }
    if (argc == 2 && strcmp(argv[1], "--diagnose") == 0) {
        return diagnose();
    }

    GtkApplication *app = gtk_application_new(
        "io.github.debianhyprland.CustomManager",
        G_APPLICATION_FLAGS_NONE);
    g_signal_connect(app, "activate", G_CALLBACK(dcm_activate), NULL);
    int status = g_application_run(G_APPLICATION(app), argc, argv);
    g_object_unref(app);
    return status;
}
