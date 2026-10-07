use anyhow::{Result, Context};
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::Path;
use super::profiles::Profile;

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct InstallPlan {
    pub profile_id: String,
    pub components_to_install: Vec<String>,
    pub packages_needed: Vec<String>,
    pub files_to_create: Vec<String>,
    pub services_to_enable: Vec<String>,
    pub is_dry_run: bool,
}

pub fn create_plan(profile: &Profile, manifest_path: &Path, dry_run: bool) -> Result<InstallPlan> {
    let mut plan = InstallPlan {
        profile_id: profile.profile.id.clone(),
        components_to_install: Vec::new(),
        packages_needed: Vec::new(),
        files_to_create: Vec::new(),
        services_to_enable: Vec::new(),
        is_dry_run: dry_run,
    };

    if manifest_path.exists() {
        let content = fs::read_to_string(manifest_path).context("Failed to read manifest")?;
        for line in content.lines().skip(1) {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() >= 4 {
                let id = parts[0];
                let _profiles = parts[3];
                // For simplicity, add if it matches our basic components
                if (id == "deblestia-bar" && profile.components.deblestia_bar) ||
                   (id == "deblestia-nova-lite" && profile.components.nova_lite) ||
                   (id == "mpvpaper-engine" && profile.components.mpvpaper_engine) ||
                   (id == "periphx" && profile.components.periphx) ||
                   (id == "mirrorbridge" && profile.components.mirrorbridge) {
                    plan.components_to_install.push(id.to_string());
                }
            }
        }
    }

    Ok(plan)
}
