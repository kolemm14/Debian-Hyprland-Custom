use std::path::PathBuf;
use std::sync::{Arc, Mutex};

#[derive(Debug, Clone)]
pub enum InstallerPage {
    Welcome,
    Diagnostic,
    Recommendation,
    Custom,
    Plan,
    Confirmation,
    Progress,
    Verification,
    Finish,
}

#[derive(Debug, Clone)]
pub struct HardwareInfo {
    pub cpu: String,
    pub ram: u64,
}

#[derive(Debug, Clone)]
pub struct CompatibilityResult {
    pub is_compatible: bool,
    pub issues: Vec<String>,
}

#[derive(Debug, Clone)]
pub struct InstallerState {
    pub current_page: InstallerPage,
    pub hardware_info: Option<HardwareInfo>,
    pub compatibility: Option<CompatibilityResult>,
    pub selected_profile: Option<String>,
    pub selected_components: Vec<String>,
    pub dry_run: bool,
    pub language: String,
    pub repo_dir: PathBuf,
    pub installation_log: Vec<String>,
}

impl InstallerState {
    pub fn new() -> Self {
        Self {
            current_page: InstallerPage::Welcome,
            hardware_info: None,
            compatibility: None,
            selected_profile: None,
            selected_components: Vec::new(),
            dry_run: false,
            language: "en".to_string(),
            repo_dir: PathBuf::from("/home/mouhamet/Debian-Hyprland-Custom"),
            installation_log: Vec::new(),
        }
    }
}
