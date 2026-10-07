use anyhow::Result;
use serde::{Deserialize, Serialize};
use super::hardware::HardwareInfo;

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct CompatibilityResult {
    pub compatibility: String,
    pub profile: String,
    pub performance_score: u32,
    pub reasons: Vec<String>,
}

pub fn evaluate(info: &HardwareInfo) -> Result<CompatibilityResult> {
    let mut reasons = Vec::new();
    let supported_arch = matches!(info.system.architecture.as_str(), "x86_64" | "amd64" | "aarch64" | "arm64");
    let debian = info.system.distribution == "debian";
    
    let restricted_environment = info.virtualization.starts_with("container");
    let graphics = info.hardware.gpu_type == "hw_accelerated" || (restricted_environment && !info.hardware.gpu.is_empty() && info.software.hyprland_installed);
    let software = info.hardware.gpu_type == "software";
    
    let mut compatibility = "RECOMMENDED";
    
    if !debian || !supported_arch || !graphics {
        compatibility = "UNSUPPORTED";
    } else if software || (info.virtualization != "none" && !restricted_environment) {
        compatibility = "LIMITED";
    } else if !info.software.hyprland_installed {
        compatibility = "COMPATIBLE";
    }
    
    if !debian {
        reasons.push("distribution non Debian".to_string());
    }
    if !supported_arch {
        reasons.push("architecture non prise en charge".to_string());
    }
    if !graphics {
        reasons.push("accélération graphique non détectée".to_string());
    }
    if software {
        reasons.push("rendu logiciel llvmpipe".to_string());
    }
    if info.virtualization != "none" && !restricted_environment {
        reasons.push("machine virtuelle détectée (profil LITE recommandé)".to_string());
    }
    
    let ram_gib = info.hardware.ram_mb / 1024;
    let threads = info.hardware.cpu_threads;
    
    if (ram_gib < 4 || threads < 4) && compatibility != "UNSUPPORTED" {
        reasons.push("ressources matérielles limitées (profil LITE recommandé)".to_string());
    }
    
    let profile = if compatibility == "UNSUPPORTED" {
        "LEGACY"
    } else if (info.virtualization != "none" && !restricted_environment) || software || ram_gib < 4 || threads < 4 {
        "LITE"
    } else if ram_gib >= 12 && threads >= 8 {
        "FULL"
    } else {
        "BALANCED"
    };
    
    let score = std::cmp::min(100, (ram_gib * 3 + threads * 4) as u32);
    
    Ok(CompatibilityResult {
        compatibility: compatibility.to_string(),
        profile: profile.to_string(),
        performance_score: score,
        reasons,
    })
}
