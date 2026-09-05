//! Exposure Control: limit total market exposure.
//!
//! Governed by: docs/task_specs/risk/exposure_control.md

/// Configuration for exposure limits.
#[derive(Debug, Clone)]
pub struct ExposureConfig {
    /// Maximum total exposure in scaled units.
    pub max_exposure_scaled: u64,
}

impl Default for ExposureConfig {
    fn default() -> Self {
        Self {
            max_exposure_scaled: 1_000_000, // conservative default
        }
    }
}

/// Check if proposed exposure is within limits.
pub fn check_exposure(
    current_exposure_scaled: u64,
    proposed_exposure_scaled: u64,
    config: &ExposureConfig,
) -> Result<(), String> {
    let total = current_exposure_scaled.saturating_add(proposed_exposure_scaled);
    if total > config.max_exposure_scaled {
        return Err(format!(
            "exposure limit exceeded: current={current_exposure_scaled}, proposed={proposed_exposure_scaled}, max={}",
            config.max_exposure_scaled
        ));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_within_limit() {
        let config = ExposureConfig { max_exposure_scaled: 1000 };
        assert!(check_exposure(400, 500, &config).is_ok());
    }

    #[test]
    fn test_exceeds_limit() {
        let config = ExposureConfig { max_exposure_scaled: 1000 };
        assert!(check_exposure(600, 500, &config).is_err());
    }

    #[test]
    fn test_overflow_protection() {
        let config = ExposureConfig { max_exposure_scaled: 100 };
        // saturating_add prevents overflow; total > limit still caught
        assert!(check_exposure(u64::MAX, 1, &config).is_err());
    }
}
