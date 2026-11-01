use anyhow::{anyhow, Context, Result};
use std::path::{Path, PathBuf};
use std::process::Command;

use super::planner::InstallPlan;

/// Resolve the source tree without depending on a developer-specific home directory.
///
/// Packagers and test environments can set DEBLESTIA_REPO_DIR explicitly. Otherwise,
/// use the current working directory, which is useful when running from a checkout.
fn repository_root() -> Result<PathBuf> {
    if let Some(root) = std::env::var_os("DEBLESTIA_REPO_DIR") {
        let path = PathBuf::from(root);
        if path.is_dir() {
            return Ok(path);
        }
        return Err(anyhow!(
            "DEBLESTIA_REPO_DIR does not point to a directory: {}",
            path.display()
        ));
    }

    let current_dir = std::env::current_dir().context("Cannot determine current directory")?;
    if current_dir.is_dir() {
        Ok(current_dir)
    } else {
        Err(anyhow!(
            "Current directory is not a directory: {}",
            current_dir.display()
        ))
    }
}

fn installer_script(root: &Path, component: &str) -> Result<PathBuf> {
    if component.is_empty()
        || !component
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || byte == b'-' || byte == b'_')
    {
        return Err(anyhow!("Invalid component identifier: {component:?}"));
    }

    let script = root.join(format!("install-{component}.sh"));
    if !script.is_file() {
        return Err(anyhow!(
            "Installer script for component {component:?} was not found at {}",
            script.display()
        ));
    }

    Ok(script)
}

pub fn execute(plan: &InstallPlan) -> Result<()> {
    if plan.is_dry_run {
        println!(
            "Dry run: would install components: {:?}",
            plan.components_to_install
        );
        return Ok(());
    }

    let root = repository_root()?;

    for component in &plan.components_to_install {
        let script = installer_script(&root, component)?;
        let status = Command::new("bash")
            .arg(&script)
            .status()
            .with_context(|| format!("Failed to execute {}", script.display()))?;

        if !status.success() {
            return Err(anyhow!(
                "Installer script {} failed with status {}",
                script.display(),
                status
            ));
        }
    }

    Ok(())
}
