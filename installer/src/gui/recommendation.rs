use adw::prelude::*;
use gtk::prelude::*;
use crate::i18n::tr;
use super::custom;
use super::plan;

pub fn build(nav: &adw::NavigationView, lang: &str) -> adw::NavigationPage {
    let header = adw::HeaderBar::new();
    
    let vbox = gtk::Box::builder()
        .orientation(gtk::Orientation::Vertical)
        .spacing(12)
        .build();
    vbox.append(&header);
    
    let lbl_title = gtk::Label::builder()
        .label("Balanced Profile Recommended")
        .css_classes(vec!["title-1"])
        .build();
    vbox.append(&lbl_title);

    let btn_accept = gtk::Button::builder()
        .label(tr("accept_recommendation", lang))
        .css_classes(vec!["suggested-action"])
        .build();
        
    let btn_customize = gtk::Button::builder()
        .label(tr("customize", lang))
        .build();

    let bbox = gtk::Box::builder().spacing(12).build();
    bbox.append(&btn_accept);
    bbox.append(&btn_customize);
    vbox.append(&bbox);

    let page = adw::NavigationPage::builder()
        .title(tr("recommendation_title", lang))
        .child(&vbox)
        .tag("recommendation")
        .build();

    let nav_clone = nav.clone();
    let lang_clone = lang.to_string();
    btn_accept.connect_clicked(move |_| {
        let p = plan::build(&nav_clone, &lang_clone);
        nav_clone.push(&p);
    });

    let nav_clone2 = nav.clone();
    let lang_clone2 = lang.to_string();
    btn_customize.connect_clicked(move |_| {
        let p = custom::build(&nav_clone2, &lang_clone2);
        nav_clone2.push(&p);
    });

    page
}
