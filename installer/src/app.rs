use libadwaita::prelude::*;
use libadwaita::{Application, ApplicationWindow, NavigationView, NavigationPage};
use gtk4::{gio, glib};
use std::sync::{Arc, Mutex};
use crate::state::InstallerState;

pub struct InstallerApp {
    app: Application,
    state: Arc<Mutex<InstallerState>>,
}

impl InstallerApp {
    pub fn new(app_id: &str, state: Arc<Mutex<InstallerState>>) -> Self {
        let app = Application::builder()
            .application_id(app_id)
            .build();
            
        Self { app, state }
    }

    pub fn setup_actions(&self) {
        // Setup language switching actions
        let lang_action = gio::SimpleAction::new("switch-lang", Some(glib::VariantTy::STRING));
        
        let state_clone = self.state.clone();
        lang_action.connect_activate(move |_, parameter| {
            if let Some(variant) = parameter {
                if let Some(lang) = variant.str() {
                    let mut state = state_clone.lock().unwrap();
                    state.language = lang.to_string();
                    tracing::info!("Language switched to: {}", lang);
                }
            }
        });
        
        self.app.add_action(&lang_action);
    }

    pub fn build_ui(&self) {
        let _state = self.state.clone();
        self.app.connect_activate(move |app| {
            let window = ApplicationWindow::builder()
                .application(app)
                .title("Deblestia Installer")
                .default_width(800)
                .default_height(600)
                .build();
                
            let nav_view = NavigationView::new();
            
            // Example page
            let welcome_page = NavigationPage::builder()
                .title("Welcome")
                .tag("welcome")
                .child(&gtk4::Label::new(Some("Welcome to the Deblestia Installer")))
                .build();
                
            nav_view.add(&welcome_page);
            
            window.set_content(Some(&nav_view));
            window.present();
        });
    }

    pub fn run(&self) -> glib::ExitCode {
        self.app.run()
    }
}
