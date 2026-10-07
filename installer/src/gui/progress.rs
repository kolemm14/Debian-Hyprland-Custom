use adw::prelude::*;
use gtk::prelude::*;
use crate::i18n::tr;
use super::verification;

pub fn build(nav: &adw::NavigationView, lang: &str) -> adw::NavigationPage {
    let header = adw::HeaderBar::new();
    
    let vbox = gtk::Box::builder()
        .orientation(gtk::Orientation::Vertical)
        .spacing(12)
        .build();
    vbox.append(&header);

    let progress_bar = gtk::ProgressBar::new();
    progress_bar.set_fraction(0.5);
    vbox.append(&progress_bar);

    let lbl = gtk::Label::new(Some("Copying files..."));
    vbox.append(&lbl);
    
    let expander = gtk::Expander::new(Some("Details"));
    let text_view = gtk::TextView::new();
    expander.set_child(Some(&text_view));
    vbox.append(&expander);

    let btn_next = gtk::Button::builder()
        .label("Simulate Next") // just for testing navigation
        .build();
    vbox.append(&btn_next);

    let page = adw::NavigationPage::builder()
        .title(tr("progress_title", lang))
        .child(&vbox)
        .tag("progress")
        .build();

    let nav_clone = nav.clone();
    let lang_clone = lang.to_string();
    btn_next.connect_clicked(move |_| {
        let p = verification::build(&nav_clone, &lang_clone);
        nav_clone.push(&p);
    });

    page
}
