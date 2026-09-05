//! Position Management: limit number of open positions.
//!
//! Governed by: docs/task_specs/risk/position_management.md

/// Configuration for position limits.
#[derive(Debug, Clone)]
pub struct PositionConfig {
    /// Maximum number of open positions.
    pub max_open_positions: u32,
}

impl Default for PositionConfig {
    fn default() -> Self {
        Self {
            max_open_positions: 10, // conservative default
        }
    }
}

/// Check if a new position is allowed.
pub fn check_position_limit(
    current_open_positions: u32,
    config: &PositionConfig,
) -> Result<(), String> {
    if current_open_positions >= config.max_open_positions {
        return Err(format!(
            "position limit reached: current={current_open_positions}, max={}",
            config.max_open_positions
        ));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_within_limit() {
        let config = PositionConfig { max_open_positions: 10 };
        assert!(check_position_limit(5, &config).is_ok());
    }

    #[test]
    fn test_at_limit() {
        let config = PositionConfig { max_open_positions: 10 };
        assert!(check_position_limit(10, &config).is_err());
    }
}
