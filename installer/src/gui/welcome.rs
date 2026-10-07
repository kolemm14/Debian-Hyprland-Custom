use adw::prelude::*;
use gtk::prelude::*;
use crate::i18n::tr;
use super::diagnostic;
use super::recommendation;
use super::custom;

pub fn build(nav: &adw::NavigationView, lang: &str) -> adw::NavigationPage {
    let status_page = adw::StatusPage::builder()
        .title(tr("title", lang))
        .description(tr("subtitle", lang))
        .build();

    let box_container = gtk::Box::builder()
        .orientation(gtk::Orientation::Vertical)
        .spacing(12)
        .halign(gtk::Align::Center)
        .build();

    // Recommended
    let btn_recommended = gtk::Button::builder()
        .label(tr("recommended_install", lang))
        .css_classes(vec!["suggested-action"])
        .build();
    let desc_recommended = gtk::Label::builder()
        .label(tr("recommended_desc", lang))
        .wrap(true)
        .build();
    let box_rec = gtk::Box::builder().orientation(gtk::Orientation::Vertical).build();
    box_rec.append(&btn_recommended);
    box_rec.append(&desc_recommended);

    // Custom
    let btn_custom = gtk::Button::builder()
        .label(tr("custom_install", lang))
        .css_classes(vec!["flat"])
        .build();
    let desc_custom = gtk::Label::builder()
        .label(tr("custom_desc", lang))
        .wrap(true)
        .build();
    let box_cus = gtk::Box::builder().orientation(gtk::Orientation::Vertical).build();
    box_cus.append(&btn_custom);
    box_cus.append(&desc_custom);

    // Diagnose
    let btn_diagnose = gtk::Button::builder()
        .label(tr("diagnostic_pc", lang))
        .css_classes(vec!["flat"])
        .build();
    let desc_diagnose = gtk::Label::builder()
        .label(tr("diagnostic_desc", lang))
        .wrap(true)
        .build();
    let box_diag = gtk::Box::builder().orientation(gtk::Orientation::Vertical).build();
    box_diag.append(&btn_diagnose);
    box_diag.append(&desc_diagnose);

    box_container.append(&box_rec);
    box_container.append(&box_cus);
    box_container.append(&box_diag);

    let clamp = adw::Clamp::builder()
        .maximum_size(600)
        .child(&box_container)
        .build();

    let scroll = gtk::ScrolledWindow::builder()
        .child(&clamp)
        .build();

    let vbox = gtk::Box::builder()
        .orientation(gtk::Orientation::Vertical)
        .build();
    vbox.append(&status_page);
    vbox.append(&scroll);

    let page = adw::NavigationPage::builder()
        .title(tr("title", lang))
        .child(&vbox)
        .tag("welcome")
        .build();

    let nav_clone1 = nav.clone();
    let lang_clone1 = lang.to_string();
    btn_recommended.connect_clicked(move |_| {
        let p = recommendation::build(&nav_clone1, &lang_clone1);
        nav_clone1.push(&p);
    });

    let nav_clone2 = nav.clone();
    let lang_clone2 = lang.to_string();
    btn_custom.connect_clicked(move |_| {
        let p = custom::build(&nav_clone2, &lang_clone2);
        nav_clone2.push(&p);
    });

    let nav_clone3 = nav.clone();
    let lang_clone3 = lang.to_string();
    btn_diagnose.connect_clicked(move |_| {
        let p = diagnostic::build(&nav_clone3, &lang_clone3);
        nav_clone3.push(&p);
    });

    page
}
