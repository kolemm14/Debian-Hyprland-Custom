mod state;
mod app;

use std::sync::{Arc, Mutex};
use state::InstallerState;
use app::InstallerApp;

fn main() {
    tracing_subscriber::fmt::init();
    tracing::info!("Starting Deblestia Installer version 0.1.0");

    let mut dry_run = false;
    let mut language = "en".to_string();

    let args: Vec<String> = std::env::args().collect();
    for arg in args {
        if arg == "--version" {
            println!("Deblestia Installer 0.1.0");
            return;
        } else if arg == "--dry-run" {
            dry_run = true;
        } else if arg.starts_with("--lang=") {
            language = arg.trim_start_matches("--lang=").to_string();
        }
    }

    let mut initial_state = InstallerState::new();
    initial_state.dry_run = dry_run;
    initial_state.language = language;

    let state = Arc::new(Mutex::new(initial_state));
    
    // Create and run the application
    let app = InstallerApp::new("org.deblestia.installer", state);
    app.setup_actions();
    app.build_ui();
    
    app.run();
}
