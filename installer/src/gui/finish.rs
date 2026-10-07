use adw::prelude::*;
use gtk::prelude::*;
use crate::i18n::tr;

pub fn build(_nav: &adw::NavigationView, lang: &str) -> adw::NavigationPage {
    let status_page = adw::StatusPage::builder()
        .title(tr("finish_title", lang))
        .description(tr("finish_desc", lang))
        .build();
        
    let vbox = gtk::Box::builder()
        .orientation(gtk::Orientation::Vertical)
        .spacing(12)
        .build();
        
    let btn_logout = gtk::Button::builder()
        .label(tr("logout", lang))
        .css_classes(vec!["suggested-action"])
        .build();
        
    let btn_close = gtk::Button::builder()
        .label(tr("close", lang))
        .build();
        
    vbox.append(&btn_logout);
    vbox.append(&btn_close);
    
    status_page.set_child(Some(&vbox));

    let page = adw::NavigationPage::builder()
        .title(tr("finish_title", lang))
        .child(&status_page)
        .tag("finish")
        .build();

    page
}
