use anyhow::{Result, Context};
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::Path;
use std::time::{SystemTime, UNIX_EPOCH};

#[derive(Debug, Serialize, Deserialize)]
pub struct BackupManifest {
    pub schema_version: u32,
    pub installation_id: String,
    pub profile: String,
    pub components: Vec<String>,
    pub files: Vec<String>,
}

pub fn create_backup(profile: &str, components: &[String]) -> Result<String> {
    let timestamp = SystemTime::now().duration_since(UNIX_EPOCH)?.as_secs();
    let backup_dir = format!("/home/mouhamet/.local/share/deblestia/backups/{}", timestamp);
    fs::create_dir_all(&backup_dir)?;
    
    let manifest = BackupManifest {
        schema_version: 1,
        installation_id: format!("inst_{}", timestamp),
        profile: profile.to_string(),
        components: components.to_vec(),
        files: vec![],
    };
    
    let manifest_path = format!("{}/manifest.json", backup_dir);
    fs::write(manifest_path, serde_json::to_string_pretty(&manifest)?)?;
    
    let config_dirs = ["hypr", "waybar", "caelestia"];
    for dir in &config_dirs {
        let src = format!("/home/mouhamet/.config/{}", dir);
        let dst = format!("{}/{}", backup_dir, dir);
        if Path::new(&src).exists() {
            let _ = Command::new("cp").arg("-r").arg(&src).arg(&dst).status();
        }
    }
    
    Ok(backup_dir)
}

use std::process::Command;

pub fn list_backups() -> Result<Vec<String>> {
    let mut backups = Vec::new();
    let base_dir = "/home/mouhamet/.local/share/deblestia/backups/";
    if Path::new(base_dir).exists() {
        for entry in fs::read_dir(base_dir)? {
            let entry = entry?;
            if entry.path().is_dir() {
                backups.push(entry.file_name().into_string().unwrap_or_default());
            }
        }
    }
    Ok(backups)
}

pub fn restore_backup(timestamp: &str) -> Result<()> {
    let backup_dir = format!("/home/mouhamet/.local/share/deblestia/backups/{}", timestamp);
    if !Path::new(&backup_dir).exists() {
        return Err(anyhow::anyhow!("Backup not found"));
    }
    
    let config_dirs = ["hypr", "waybar", "caelestia"];
    for dir in &config_dirs {
        let src = format!("{}/{}", backup_dir, dir);
        let dst = format!("/home/mouhamet/.config/{}", dir);
        if Path::new(&src).exists() {
            let _ = Command::new("cp").arg("-r").arg(&src).arg(&dst).status();
        }
    }
    
    Ok(())
}
