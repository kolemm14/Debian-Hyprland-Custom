#[derive(Debug, Clone)]
pub struct InstallerState {
    /// Requests simulation mode in the command-line interface.
    pub dry_run: bool,
    /// Interface language selected at startup or through the application action.
    pub language: String,
}

impl InstallerState {
    pub fn new() -> Self {
        Self::default()
    }
}

impl Default for InstallerState {
    fn default() -> Self {
        Self {
            dry_run: false,
            language: "en".to_string(),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::InstallerState;

    #[test]
    fn default_state_uses_english_without_dry_run() {
        let state = InstallerState::default();

        assert_eq!(state.language, "en");
        assert!(!state.dry_run);
    }
}
