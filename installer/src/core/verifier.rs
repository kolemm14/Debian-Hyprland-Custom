use anyhow::Result;
use serde::{Deserialize, Serialize};
use std::path::Path;
use std::process::Command;

#[derive(Debug, Serialize, Deserialize)]
pub struct VerificationResult {
    pub hyprland_ok: bool,
    pub components_status: std::collections::HashMap<String, bool>,
}

pub fn verify() -> Result<VerificationResult> {
    let hyprland_ok = Command::new("which").arg("Hyprland").output().map(|o| o.status.success()).unwrap_or(false);
    
    let mut components_status = std::collections::HashMap::new();
    components_status.insert("deblestia-bar".to_string(), Path::new("/home/mouhamet/.config/waybar").exists());
    
    Ok(VerificationResult {
        hyprland_ok,
        components_status,
    })
}
