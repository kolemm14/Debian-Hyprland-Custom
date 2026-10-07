use anyhow::Result;
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::Path;

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct ProfileDef {
    pub id: String,
    pub name: String,
    pub display_name_en: String,
    pub display_name_fr: String,
    pub description_en: String,
    pub description_fr: String,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct ComponentsConfig {
    pub hyprland: bool,
    pub deblestia_bar: bool,
    pub nova_lite: bool,
    pub notifications: bool,
    pub launcher: bool,
    pub lockscreen: bool,
    pub mpvpaper_engine: bool,
    pub periphx: bool,
    pub mirrorbridge: bool,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct VisualConfig {
    pub animations: String,
    pub blur: String,
    pub heavy_effects: bool,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct PerformanceConfig {
    pub default_wallpaper_profile: String,
    pub optional_background_services: bool,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct Profile {
    pub profile: ProfileDef,
    pub components: ComponentsConfig,
    pub visual: VisualConfig,
    pub performance: PerformanceConfig,
}

pub fn load_profile<P: AsRef<Path>>(path: P) -> Result<Profile> {
    let content = fs::read_to_string(path)?;
    let profile: Profile = toml::from_str(&content)?;
    Ok(profile)
}
