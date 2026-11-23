use crate::state::InstallerState;
use gtk4::{gio, glib};
use libadwaita::prelude::*;
use libadwaita::{Application, ApplicationWindow, NavigationPage, NavigationView};
use std::sync::{Arc, Mutex};

pub struct InstallerApp {
    app: Application,
    state: Arc<Mutex<InstallerState>>,
}

impl InstallerApp {
    pub fn new(app_id: &str, state: Arc<Mutex<InstallerState>>) -> Self {
        let app = Application::builder().application_id(app_id).build();

        Self { app, state }
    }

    pub fn setup_actions(&self) {
        let lang_action = gio::SimpleAction::new("switch-lang", Some(glib::VariantTy::STRING));

        let state_clone = self.state.clone();
        lang_action.connect_activate(move |_, parameter| {
            let Some(language) = parameter.and_then(|variant| variant.str()) else {
                tracing::warn!("Ignoring language action without a string parameter");
                return;
            };

            match state_clone.lock() {
                Ok(mut state) => {
                    state.language = language.to_string();
                    tracing::info!("Language switched to: {}", language);
                }
                Err(error) => {
                    tracing::error!("Cannot update installer language: {}", error);
                }
            }
        });

        self.app.add_action(&lang_action);
    }

    pub fn build_ui(&self) {
        let state = self.state.clone();
        self.app.connect_activate(move |app| {
            let (language, dry_run) = match state.lock() {
                Ok(state) => (state.language.clone(), state.dry_run),
                Err(error) => {
                    tracing::error!("Cannot read installer state: {}", error);
                    let state = error.into_inner();
                    (state.language.clone(), state.dry_run)
                }
            };

            let is_french = language.eq_ignore_ascii_case("fr");
            let title = if is_french {
                "Installateur Deblestia"
            } else {
                "Deblestia Installer"
            };
            let welcome_title = if is_french {
                "Bienvenue"
            } else {
                "Welcome"
            };
            let explanation = if is_french {
                "Cette interface est encore un prototype. Elle ne lance aucune installation et ne modifie pas votre système."
            } else {
                "This interface is still a prototype. It does not run an installation or modify your system."
            };
            let mode_description = if dry_run {
                if is_french {
                    "Option --dry-run détectée : aucune commande d’installation ne sera exécutée."
                } else {
                    "--dry-run detected: no installation commands will be executed."
                }
            } else if is_french {
                "Aucune opération n’a été démarrée. Utilisez ./install.sh à la racine du dépôt pour le parcours d’installation pris en charge."
            } else {
                "No operation has been started. Use ./install.sh at the repository root for the supported installation workflow."
            };

            let window = ApplicationWindow::builder()
                .application(app)
                .title(title)
                .default_width(800)
                .default_height(600)
                .build();

            let content = gtk4::Box::new(gtk4::Orientation::Vertical, 16);
            content.set_margin_top(24);
            content.set_margin_bottom(24);
            content.set_margin_start(24);
            content.set_margin_end(24);

            let heading = gtk4::Label::new(Some(welcome_title));
            heading.add_css_class("title-1");
            heading.set_wrap(true);

            let explanation_label = gtk4::Label::new(Some(explanation));
            explanation_label.set_wrap(true);
            explanation_label.set_xalign(0.0);

            let mode_label = gtk4::Label::new(Some(mode_description));
            mode_label.set_wrap(true);
            mode_label.set_xalign(0.0);

            content.append(&heading);
            content.append(&explanation_label);
            content.append(&mode_label);

            let navigation_view = NavigationView::new();
            let welcome_page = NavigationPage::builder()
                .title(welcome_title)
                .tag("welcome")
                .child(&content)
                .build();

            navigation_view.add(&welcome_page);
            window.set_content(Some(&navigation_view));
            window.present();
        });
    }

    pub fn run(&self) -> glib::ExitCode {
        self.app.run()
    }
}
