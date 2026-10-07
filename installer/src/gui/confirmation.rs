use adw::prelude::*;
use gtk::prelude::*;
use crate::i18n::tr;
use super::progress;

pub fn build(nav: &adw::NavigationView, lang: &str) -> adw::NavigationPage {
    let header = adw::HeaderBar::new();
    
    let vbox = gtk::Box::builder()
        .orientation(gtk::Orientation::Vertical)
        .spacing(12)
        .build();
    vbox.append(&header);

    let lbl = gtk::Label::new(Some(&tr("confirm_desc", lang)));
    vbox.append(&lbl);

    let btn_confirm = gtk::Button::builder()
        .label(tr("confirm", lang))
        .css_classes(vec!["suggested-action"])
        .build();
    vbox.append(&btn_confirm);

    let page = adw::NavigationPage::builder()
        .title(tr("confirm_title", lang))
        .child(&vbox)
        .tag("confirmation")
        .build();

    let nav_clone = nav.clone();
    let lang_clone = lang.to_string();
    btn_confirm.connect_clicked(move |_| {
        let p = progress::build(&nav_clone, &lang_clone);
        nav_clone.push(&p);
    });

    page
}
