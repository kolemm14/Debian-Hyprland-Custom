use anyhow::Result;
use serde::{Deserialize, Serialize};
use std::env;
use std::fs;
use std::path::Path;
use std::process::Command;

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct SystemInfo {
    pub distribution: String,
    pub version: String,
    pub codename: String,
    pub architecture: String,
    pub kernel: String,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct HardwareDetails {
    pub cpu: String,
    pub cpu_threads: u32,
    pub ram_mb: u32,
    pub gpu: Vec<String>,
    pub gpu_type: String,
    pub storage_free_mb: u32,
    pub battery: bool,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct SoftwareInfo {
    pub session: String,
    pub wayland: bool,
    pub display_manager: String,
    pub hyprland_installed: bool,
    pub gnome_installed: bool,
    pub current_desktop: String,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct HardwareInfo {
    pub schema_version: u32,
    pub status: String,
    pub system: SystemInfo,
    pub hardware: HardwareDetails,
    pub software: SoftwareInfo,
    pub virtualization: String,
}

impl Default for HardwareInfo {
    fn default() -> Self {
        Self {
            schema_version: 1,
            status: "ok".to_string(),
            system: SystemInfo {
                distribution: "unknown".to_string(),
                version: "unknown".to_string(),
                codename: "unknown".to_string(),
                architecture: "unknown".to_string(),
                kernel: "unknown".to_string(),
            },
            hardware: HardwareDetails {
                cpu: "unknown".to_string(),
                cpu_threads: 0,
                ram_mb: 0,
                gpu: vec![],
                gpu_type: "unknown".to_string(),
                storage_free_mb: 0,
                battery: false,
            },
            software: SoftwareInfo {
                session: "unknown".to_string(),
                wayland: false,
                display_manager: "unknown".to_string(),
                hyprland_installed: false,
                gnome_installed: false,
                current_desktop: "unknown".to_string(),
            },
            virtualization: "none".to_string(),
        }
    }
}

fn command_output(cmd: &str, args: &[&str]) -> String {
    Command::new(cmd)
        .args(args)
        .output()
        .ok()
        .and_then(|o| if o.status.success() { Some(String::from_utf8_lossy(&o.stdout).trim().to_string()) } else { None })
        .unwrap_or_default()
}

fn which(cmd: &str) -> bool {
    Command::new("which").arg(cmd).output().map(|o| o.status.success()).unwrap_or(false)
}

pub fn detect() -> Result<HardwareInfo> {
    let mut info = HardwareInfo::default();

    // OS Release
    if let Ok(content) = fs::read_to_string("/etc/os-release") {
        for line in content.lines() {
            if line.starts_with("ID=") {
                info.system.distribution = line[3..].trim_matches('"').to_string();
            } else if line.starts_with("VERSION_ID=") {
                info.system.version = line[11..].trim_matches('"').to_string();
            } else if line.starts_with("VERSION_CODENAME=") {
                info.system.codename = line[17..].trim_matches('"').to_string();
            }
        }
    }

    // Architecture and Kernel
    info.system.architecture = command_output("uname", &["-m"]);
    info.system.kernel = command_output("uname", &["-r"]);

    // RAM
    if let Ok(content) = fs::read_to_string("/proc/meminfo") {
        for line in content.lines() {
            if line.starts_with("MemTotal:") {
                let parts: Vec<&str> = line.split_whitespace().collect();
                if parts.len() >= 2 {
                    if let Ok(kb) = parts[1].parse::<u32>() {
                        info.hardware.ram_mb = kb / 1024;
                    }
                }
                break;
            }
        }
    }

    // CPU
    if let Ok(content) = fs::read_to_string("/proc/cpuinfo") {
        for line in content.lines() {
            if line.starts_with("model name") {
                let parts: Vec<&str> = line.split(':').collect();
                if parts.len() == 2 {
                    info.hardware.cpu = parts[1].trim().to_string();
                    break;
                }
            }
        }
    }
    info.hardware.cpu_threads = std::thread::available_parallelism().map(|n| n.get() as u32).unwrap_or(1);

    // GPU
    let lspci = command_output("lspci", &[]);
    for line in lspci.lines() {
        if line.to_lowercase().contains("vga compatible") || line.to_lowercase().contains("3d controller") {
            info.hardware.gpu.push(line.to_string());
        }
    }
    
    // Check graphics acceleration
    if Path::new("/dev/dri").exists() {
        info.hardware.gpu_type = "hw_accelerated".to_string();
    } else {
        info.hardware.gpu_type = "software".to_string();
    }

    // Battery
    info.hardware.battery = Path::new("/sys/class/power_supply").read_dir().map(|mut d| d.any(|e| e.ok().map_or(false, |p| p.file_name().to_string_lossy().starts_with("BAT")))).unwrap_or(false);

    // Storage
    let statvfs_cmd = command_output("df", &["-m", "/"]);
    let df_lines: Vec<&str> = statvfs_cmd.lines().collect();
    if df_lines.len() >= 2 {
        let parts: Vec<&str> = df_lines[1].split_whitespace().collect();
        if parts.len() >= 4 {
            if let Ok(mb) = parts[3].parse::<u32>() {
                info.hardware.storage_free_mb = mb;
            }
        }
    }

    // Software
    info.software.session = env::var("XDG_SESSION_TYPE").unwrap_or_else(|_| "unknown".to_string());
    info.software.current_desktop = env::var("XDG_CURRENT_DESKTOP").unwrap_or_else(|_| "unknown".to_string());
    info.software.wayland = env::var("WAYLAND_DISPLAY").is_ok() || info.software.session == "wayland";
    
    info.software.hyprland_installed = which("Hyprland") || which("hyprctl");
    info.software.gnome_installed = info.software.current_desktop.to_lowercase().contains("gnome") || 
        Path::new("/usr/share/xsessions/gnome.desktop").exists();

    // Virtualization
    let virt = command_output("systemd-detect-virt", &[]);
    if !virt.is_empty() && virt != "none" {
        info.virtualization = virt;
    } else {
        info.virtualization = "none".to_string();
    }

    Ok(info)
}
