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


#[cfg(test)]
mod tests {
    use super::installer_script;
    use std::fs;
    use std::path::PathBuf;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn temporary_root() -> PathBuf {
        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|duration| duration.as_nanos())
            .unwrap_or_default();
        std::env::temp_dir().join(format!(
            "deblestia-installer-executor-{}-{nonce}",
            std::process::id()
        ))
    }

    #[test]
    fn rejects_component_identifiers_that_could_escape_repository_root() {
        let root = temporary_root();

        let error = installer_script(&root, "../outside").unwrap_err();

        assert!(error.to_string().contains("Invalid component identifier"));
    }

    #[test]
    fn reports_a_missing_installer_script_instead_of_simulating_success() {
        let root = temporary_root();
        fs::create_dir_all(&root).unwrap();

        let result = installer_script(&root, "missing-component");

        assert!(result.is_err());
        assert!(result
            .unwrap_err()
            .to_string()
            .contains("was not found"));

        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn resolves_an_existing_installer_script_inside_the_repository() {
        let root = temporary_root();
        fs::create_dir_all(&root).unwrap();
        let expected = root.join("install-demo-component.sh");
        fs::write(&expected, "#!/usr/bin/env bash\nexit 0\n").unwrap();

        let result = installer_script(&root, "demo-component").unwrap();

        assert_eq!(result, expected);
        fs::remove_dir_all(root).unwrap();
    }
}
