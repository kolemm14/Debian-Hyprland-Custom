#include "assistant_router.h"
#include <string.h>

gchar *dcm_normalize(const gchar *text) {
    gchar *ascii = g_str_to_ascii(text ? text : "", "en");
    gchar *lower = g_ascii_strdown(ascii, -1);
    GString *out = g_string_new(NULL);
    gboolean space = FALSE;
    for (const gchar *p = lower; *p; p++) {
        if (g_ascii_isspace(*p)) { space = out->len > 0; continue; }
        if (space) g_string_append_c(out, ' ');
        space = FALSE;
        g_string_append_c(out, *p);
    }
    g_free(ascii);
    g_free(lower);
    return g_string_free(out, FALSE);
}

gint dcm_component_lookup(GPtrArray *components, const gchar *name) {
    gchar *key = dcm_normalize(name);
    gint found = -1;
    for (guint i = 0; components && i < components->len; i++) {
        DcmComponent *c = g_ptr_array_index(components, i);
        gchar *label = dcm_normalize(c->name);
        gboolean match = !strcmp(key, c->id) || !strcmp(key, label) ||
            (!strcmp(key, "mpvpaper") && !strcmp(c->id, "mpvpaper-engine"));
        g_free(label);
        if (match) { found = (gint)i; break; }
    }
    g_free(key);
    return found;
}

DcmRoute dcm_assistant_route(const gchar *text, GPtrArray *components) {
    static const struct { const gchar *phrase; DcmIntent intent; } phrases[] = {
        {"overview", DCM_OVERVIEW}, {"accueil", DCM_OVERVIEW},
        {"components", DCM_COMPONENTS}, {"show components", DCM_COMPONENTS},
        {"montre les composants", DCM_COMPONENTS},
        {"check", DCM_CHECK}, {"check updates", DCM_CHECK}, {"check for updates", DCM_CHECK},
        {"verifie les mises a jour", DCM_CHECK},
        {"dry-run", DCM_DRY_RUN}, {"dry run", DCM_DRY_RUN}, {"simulate update", DCM_DRY_RUN},
        {"simule la mise a jour", DCM_DRY_RUN},
        {"dependencies", DCM_DEPENDENCIES}, {"show dependencies", DCM_DEPENDENCIES},
        {"voir les dependances", DCM_DEPENDENCIES},
        {"diagnose", DCM_DIAGNOSE}, {"diagnose system", DCM_DIAGNOSE},
        {"diagnostique le systeme", DCM_DIAGNOSE},
        {"logs", DCM_LOGS}, {"show logs", DCM_LOGS}, {"montre les journaux", DCM_LOGS},
        {"assistant", DCM_ASSISTANT}, {"help", DCM_HELP}, {"aide", DCM_HELP},
        {"quit", DCM_QUIT}, {"exit", DCM_QUIT}, {"quitter", DCM_QUIT},
        {"update", DCM_UPDATE}, {"rollback", DCM_ROLLBACK}
    };
    DcmRoute route = { DCM_UNKNOWN, -1 };
    gchar *normalized = dcm_normalize(text);
    const gchar *key = normalized + (normalized[0] == ':');
    for (guint i = 0; i < G_N_ELEMENTS(phrases); i++) {
        if (!strcmp(key, phrases[i].phrase)) { route.intent = phrases[i].intent; break; }
    }
    static const struct { const gchar *prefix; DcmIntent intent; } verbs[] = {
        {"install ", DCM_INSTALL}, {"installer ", DCM_INSTALL},
        {"open ", DCM_OPEN}, {"ouvrir ", DCM_OPEN}
    };
    for (guint i = 0; route.intent == DCM_UNKNOWN && i < G_N_ELEMENTS(verbs); i++) {
        if (g_str_has_prefix(key, verbs[i].prefix)) {
            route.component = dcm_component_lookup(components, key + strlen(verbs[i].prefix));
            if (route.component >= 0) route.intent = verbs[i].intent;
        }
    }
    g_free(normalized);
    return route;
}
