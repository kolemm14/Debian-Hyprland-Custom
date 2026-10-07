pub mod welcome;
pub mod diagnostic;
pub mod recommendation;
pub mod custom;
pub mod plan;
pub mod confirmation;
pub mod progress;
pub mod verification;
pub mod finish;

use adw::prelude::*;
use gtk::prelude::*;
use std::rc::Rc;
use std::cell::RefCell;

pub fn build_main_window(app: &adw::Application) {
    let navigation_view = adw::NavigationView::new();
    
    let window = adw::ApplicationWindow::builder()
        .application(app)
        .title("Deblestia Installer")
        .default_width(800)
        .default_height(600)
        .content(&navigation_view)
        .build();

    let lang = "en"; // Or dynamically detect
    let welcome_page = welcome::build(&navigation_view, lang);
    navigation_view.add(&welcome_page);
    
    window.present();
}
