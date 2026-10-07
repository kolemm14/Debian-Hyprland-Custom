use adw::prelude::*;
use gtk::prelude::*;
use crate::i18n::tr;
use super::confirmation;

pub fn build(nav: &adw::NavigationView, lang: &str) -> adw::NavigationPage {
    let header = adw::HeaderBar::new();
    
    let vbox = gtk::Box::builder()
        .orientation(gtk::Orientation::Vertical)
        .spacing(12)
        .build();
    vbox.append(&header);

    let lbl = gtk::Label::new(Some("Will install: Hyprland, Waybar\nWill keep: GNOME\nEstimated space: 2GB"));
    vbox.append(&lbl);

    let btn_install = gtk::Button::builder()
        .label(tr("install", lang))
        .css_classes(vec!["suggested-action"])
        .build();
    vbox.append(&btn_install);

    let page = adw::NavigationPage::builder()
        .title(tr("plan_title", lang))
        .child(&vbox)
        .tag("plan")
        .build();

    let nav_clone = nav.clone();
    let lang_clone = lang.to_string();
    btn_install.connect_clicked(move |_| {
        let p = confirmation::build(&nav_clone, &lang_clone);
        nav_clone.push(&p);
    });

    page
}
