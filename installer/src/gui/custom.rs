use adw::prelude::*;
use gtk::prelude::*;
use crate::i18n::tr;
use super::plan;

pub fn build(nav: &adw::NavigationView, lang: &str) -> adw::NavigationPage {
    let header = adw::HeaderBar::new();
    
    let vbox = gtk::Box::builder()
        .orientation(gtk::Orientation::Vertical)
        .spacing(12)
        .build();
    vbox.append(&header);

    let group = adw::PreferencesGroup::new();
    
    let row1 = adw::ActionRow::builder()
        .title("Hyprland Core")
        .subtitle("Window manager and essentials")
        .build();
    let sw1 = gtk::Switch::builder().active(true).build();
    row1.add_suffix(&sw1);
    group.add(&row1);

    vbox.append(&group);

    let btn_continue = gtk::Button::builder()
        .label(tr("continue", lang))
        .css_classes(vec!["suggested-action"])
        .build();
    vbox.append(&btn_continue);

    let scroll = gtk::ScrolledWindow::builder().child(&vbox).build();

    let page = adw::NavigationPage::builder()
        .title(tr("custom_title", lang))
        .child(&scroll)
        .tag("custom")
        .build();

    let nav_clone = nav.clone();
    let lang_clone = lang.to_string();
    btn_continue.connect_clicked(move |_| {
        let p = plan::build(&nav_clone, &lang_clone);
        nav_clone.push(&p);
    });

    page
}
