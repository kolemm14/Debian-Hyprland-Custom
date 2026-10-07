use adw::prelude::*;
use gtk::prelude::*;
use crate::i18n::tr;
use super::finish;

pub fn build(nav: &adw::NavigationView, lang: &str) -> adw::NavigationPage {
    let header = adw::HeaderBar::new();
    
    let vbox = gtk::Box::builder()
        .orientation(gtk::Orientation::Vertical)
        .spacing(12)
        .build();
    vbox.append(&header);

    let lbl = gtk::Label::new(Some("Everything looks good."));
    vbox.append(&lbl);

    let btn_continue = gtk::Button::builder()
        .label(tr("continue", lang))
        .css_classes(vec!["suggested-action"])
        .build();
    vbox.append(&btn_continue);

    let page = adw::NavigationPage::builder()
        .title(tr("verification_title", lang))
        .child(&vbox)
        .tag("verification")
        .build();

    let nav_clone = nav.clone();
    let lang_clone = lang.to_string();
    btn_continue.connect_clicked(move |_| {
        let p = finish::build(&nav_clone, &lang_clone);
        nav_clone.push(&p);
    });

    page
}
