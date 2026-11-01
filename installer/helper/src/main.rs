use serde::{Deserialize, Serialize};
use std::io::{self, Read};
use std::process::Command;

#[derive(Deserialize)]
#[serde(tag = "action")]
enum HelperCommand {
    #[serde(rename = "install_packages")]
    InstallPackages { packages: Vec<String> },
    #[serde(rename = "run_backend_install")]
    RunBackendInstall { args: Vec<String> },
    #[serde(rename = "write_session_file")]
    WriteSessionFile { content: String },
    #[serde(rename = "enable_service")]
    EnableService { service: String },
    #[serde(rename = "remove_packages")]
    RemovePackages { packages: Vec<String> },
}

#[derive(Serialize)]
struct HelperResponse {
    success: bool,
    stdout: String,
    stderr: String,
}

fn validate_package_name(pkg: &str) -> bool {
    if pkg.is_empty() {
        return false;
    }
    let mut chars = pkg.chars();
    let first = chars.next().unwrap();
    if !first.is_ascii_lowercase() && !first.is_ascii_digit() {
        return false;
    }
    chars.all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '.' || c == '+' || c == '-')
}

fn validate_service_name(svc: &str) -> bool {
    if svc.is_empty() {
        return false;
    }
    svc.chars()
        .all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_' || c == '.')
}

fn main() {
    let mut input = String::new();
    if let Err(e) = io::stdin().read_to_string(&mut input) {
        eprintln!("Failed to read stdin: {}", e);
        std::process::exit(1);
    }

    let cmd: HelperCommand = match serde_json::from_str(&input) {
        Ok(c) => c,
        Err(e) => {
            eprintln!("Invalid command JSON: {}", e);
            std::process::exit(1);
        }
    };

    let result = match cmd {
        HelperCommand::InstallPackages { packages } => {
            if !packages.iter().all(|p| validate_package_name(p)) {
                eprintln!("Invalid package name in list");
                std::process::exit(1);
            }
            Command::new("apt-get")
                .arg("install")
                .arg("-y")
                .arg("--no-install-recommends")
                .args(&packages)
                .output()
        }
        HelperCommand::RemovePackages { packages } => {
            if !packages.iter().all(|p| validate_package_name(p)) {
                eprintln!("Invalid package name in list");
                std::process::exit(1);
            }
            Command::new("apt-get")
                .arg("remove")
                .arg("-y")
                .args(&packages)
                .output()
        }
        HelperCommand::RunBackendInstall { args } => {
            // Validate arguments to avoid arbitrary command execution
            for arg in &args {
                if arg.contains(";")
                    || arg.contains("&")
                    || arg.contains("|")
                    || arg.contains("`")
                    || arg.contains("$")
                {
                    eprintln!("Invalid character in arguments");
                    std::process::exit(1);
                }
            }
            let script_path = "/usr/share/deblestia/install.sh"; // Assume backend script is installed here, or use validated absolute path
            Command::new("bash").arg(script_path).args(&args).output()
        }
        HelperCommand::WriteSessionFile { content } => {
            let path = "/usr/share/wayland-sessions/deblestia.desktop";
            match std::fs::write(path, content) {
                Ok(_) => Command::new("true").output(),
                Err(e) => {
                    eprintln!("Failed to write session file: {}", e);
                    std::process::exit(1);
                }
            }
        }
        HelperCommand::EnableService { service } => {
            if !validate_service_name(&service) {
                eprintln!("Invalid service name");
                std::process::exit(1);
            }
            let _ = Command::new("systemctl")
                .arg("enable")
                .arg(&service)
                .output();

            Command::new("systemctl")
                .arg("start")
                .arg(&service)
                .output()
        }
    };

    match result {
        Ok(output) => {
            let response = HelperResponse {
                success: output.status.success(),
                stdout: String::from_utf8_lossy(&output.stdout).into_owned(),
                stderr: String::from_utf8_lossy(&output.stderr).into_owned(),
            };
            println!("{}", serde_json::to_string(&response).unwrap());
        }
        Err(e) => {
            eprintln!("Command execution failed: {}", e);
            std::process::exit(1);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::{validate_package_name, validate_service_name, HelperCommand};

    #[test]
    fn package_names_accept_debian_safe_characters() {
        for package in [
            "hyprland",
            "libgtk-3-0",
            "python3-gi",
            "libfoo+bar1",
            "x11-utils",
        ] {
            assert!(validate_package_name(package), "rejected {package:?}");
        }
    }

    #[test]
    fn package_names_reject_empty_uppercase_and_argument_injection() {
        for package in ["", "Hyprland", "foo/bar", "foo;touch", "-y", "foo bar"] {
            assert!(!validate_package_name(package), "accepted {package:?}");
        }
    }

    #[test]
    fn service_names_accept_unit_safe_characters() {
        for service in ["pericored.service", "user-session_2.target", "a-b"] {
            assert!(validate_service_name(service), "rejected {service:?}");
        }
    }

    #[test]
    fn service_names_reject_empty_and_command_syntax() {
        for service in ["", "foo/bar.service", "foo;touch", "foo bar"] {
            assert!(!validate_service_name(service), "accepted {service:?}");
        }
    }

    #[test]
    fn helper_command_deserializes_supported_wire_actions() {
        let install: HelperCommand =
            serde_json::from_str(r#"{"action":"install_packages","packages":["hyprland"]}"#)
                .unwrap();
        assert!(matches!(install, HelperCommand::InstallPackages { .. }));

        let remove: HelperCommand =
            serde_json::from_str(r#"{"action":"remove_packages","packages":["hyprland"]}"#)
                .unwrap();
        assert!(matches!(remove, HelperCommand::RemovePackages { .. }));

        let run: HelperCommand =
            serde_json::from_str(r#"{"action":"run_backend_install","args":["--dry-run"]}"#)
                .unwrap();
        assert!(matches!(run, HelperCommand::RunBackendInstall { .. }));

        let write: HelperCommand =
            serde_json::from_str(r#"{"action":"write_session_file","content":"[Desktop Entry]"}"#)
                .unwrap();
        assert!(matches!(write, HelperCommand::WriteSessionFile { .. }));

        let service: HelperCommand =
            serde_json::from_str(r#"{"action":"enable_service","service":"pericored.service"}"#)
                .unwrap();
        assert!(matches!(service, HelperCommand::EnableService { .. }));
    }

    #[test]
    fn unknown_helper_action_is_rejected() {
        assert!(serde_json::from_str::<HelperCommand>(r#"{"action":"run_shell"}"#).is_err());
    }
}
