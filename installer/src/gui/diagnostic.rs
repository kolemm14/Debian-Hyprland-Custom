use adw::prelude::*;
use gtk::prelude::*;
use crate::i18n::tr;

pub fn build(nav: &adw::NavigationView, lang: &str) -> adw::NavigationPage {
    let header = adw::HeaderBar::new();
    
    let spinner = gtk::Spinner::new();
    spinner.start();
    
    let group = adw::PreferencesGroup::new();
    
    let row_os = adw::ActionRow::builder()
        .title("OS")
        .subtitle("Debian 13 (Trixie)")
        .build();
    let row_cpu = adw::ActionRow::builder()
        .title("CPU")
        .subtitle("Scanning...")
        .build();
    
    group.add(&row_os);
    group.add(&row_cpu);

    let btn_continue = gtk::Button::builder()
        .label(tr("continue", lang))
        .css_classes(vec!["suggested-action"])
        .build();
    
    let vbox = gtk::Box::builder()
        .orientation(gtk::Orientation::Vertical)
        .spacing(12)
        .build();
    
    vbox.append(&header);
    vbox.append(&spinner);
    vbox.append(&group);
    vbox.append(&btn_continue);

    let scroll = gtk::ScrolledWindow::builder()
        .child(&vbox)
        .build();

    let page = adw::NavigationPage::builder()
        .title(tr("diagnostic_title", lang))
        .child(&scroll)
        .tag("diagnostic")
        .build();
        
    let nav_clone = nav.clone();
    btn_continue.connect_clicked(move |_| {
        nav_clone.pop();
    });

    page
}
