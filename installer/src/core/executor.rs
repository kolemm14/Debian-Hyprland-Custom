use anyhow::{Result, anyhow};
use std::process::Command;
use super::planner::InstallPlan;

pub fn execute(plan: &InstallPlan) -> Result<()> {
    if plan.is_dry_run {
        println!("Dry run: would install components: {:?}", plan.components_to_install);
        return Ok(());
    }

    for component in &plan.components_to_install {
        // Find installer script
        let script = format!("/home/mouhamet/Debian-Hyprland-Custom/install-{}.sh", component);
        if std::path::Path::new(&script).exists() {
            let status = Command::new("bash")
                .arg(&script)
                .status()
                .map_err(|e| anyhow!("Failed to execute {}: {}", script, e))?;
            
            if !status.success() {
                return Err(anyhow!("Installer script {} failed with status {}", script, status));
            }
        } else {
            // Just simulate
            println!("Simulating installation of {}", component);
        }
    }

    Ok(())
}
