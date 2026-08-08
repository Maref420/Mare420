//! Core domain enumerations for SpecGen.
//!
//! Variant sets are derived from locked governance artifacts:
//! - `Language` — source: `governance/registry/languages.yaml`
//! - `Profile` — source: `governance/registry/profiles.yaml`
//! - `ArtifactKind` — source: the template layout under
//!   `tools/specgen/templates/`

use std::fmt;
use std::str::FromStr;

use serde::{Deserialize, Serialize};

use crate::errors::{SpecgenError, SpecgenResult};

/// Implementation languages approved for Atlas AI modules.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Language {
    Rust,
    Python,
}

/// Deployment/quality profiles registered for Atlas AI.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Profile {
    Production,
    Research,
    Benchmark,
    Legacy,
}

/// Artifact families addressable through metadata.
///
/// `error` and `test` templates are auxiliary inputs consumed by
/// generators and are intentionally not metadata-addressable.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ArtifactKind {
    Module,
    Service,
    Agent,
    Api,
    Event,
    Schema,
    Foundation,
    ArchitectureRules,
}

impl Language {
    /// Canonical identifier as registered in `languages.yaml`.
    pub fn as_str(self) -> &'static str {
        match self {
            Language::Rust => "rust",
            Language::Python => "python",
        }
    }
}

impl Profile {
    /// Canonical identifier as registered in `profiles.yaml`.
    pub fn as_str(self) -> &'static str {
        match self {
            Profile::Production => "production",
            Profile::Research => "research",
            Profile::Benchmark => "benchmark",
            Profile::Legacy => "legacy",
        }
    }
}

impl ArtifactKind {
    /// Canonical identifier matching the template layout.
    pub fn as_str(self) -> &'static str {
        match self {
            ArtifactKind::Module => "module",
            ArtifactKind::Service => "service",
            ArtifactKind::Agent => "agent",
            ArtifactKind::Api => "api",
            ArtifactKind::Event => "event",
            ArtifactKind::Schema => "schema",
            ArtifactKind::Foundation => "foundation",
            ArtifactKind::ArchitectureRules => "architecture_rules",
        }
    }
}

impl FromStr for Language {
    type Err = SpecgenError;

    fn from_str(value: &str) -> SpecgenResult<Self> {
        match value {
            "rust" => Ok(Language::Rust),
            "python" => Ok(Language::Python),
            other => Err(SpecgenError::UnknownValue {
                kind: "language",
                value: other.to_string(),
            }),
        }
    }
}

impl FromStr for Profile {
    type Err = SpecgenError;

    fn from_str(value: &str) -> SpecgenResult<Self> {
        match value {
            "production" => Ok(Profile::Production),
            "research" => Ok(Profile::Research),
            "benchmark" => Ok(Profile::Benchmark),
            "legacy" => Ok(Profile::Legacy),
            other => Err(SpecgenError::UnknownValue {
                kind: "profile",
                value: other.to_string(),
            }),
        }
    }
}

impl FromStr for ArtifactKind {
    type Err = SpecgenError;

    fn from_str(value: &str) -> SpecgenResult<Self> {
        match value {
            "module" => Ok(ArtifactKind::Module),
            "service" => Ok(ArtifactKind::Service),
            "agent" => Ok(ArtifactKind::Agent),
            "api" => Ok(ArtifactKind::Api),
            "event" => Ok(ArtifactKind::Event),
            "schema" => Ok(ArtifactKind::Schema),
            "foundation" => Ok(ArtifactKind::Foundation),
            "architecture_rules" => Ok(ArtifactKind::ArchitectureRules),
            other => Err(SpecgenError::UnknownValue {
                kind: "artifact",
                value: other.to_string(),
            }),
        }
    }
}

impl fmt::Display for Language {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.as_str())
    }
}

impl fmt::Display for Profile {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.as_str())
    }
}

impl fmt::Display for ArtifactKind {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.as_str())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn language_round_trip() -> SpecgenResult<()> {
        for (text, expected) in [("rust", Language::Rust), ("python", Language::Python)] {
            let parsed = Language::from_str(text)?;
            assert_eq!(parsed, expected);
            assert_eq!(parsed.as_str(), text);
            assert_eq!(parsed.to_string(), text);
        }
        Ok(())
    }

    #[test]
    fn profile_round_trip() -> SpecgenResult<()> {
        for (text, expected) in [
            ("production", Profile::Production),
            ("research", Profile::Research),
            ("benchmark", Profile::Benchmark),
            ("legacy", Profile::Legacy),
        ] {
            let parsed = Profile::from_str(text)?;
            assert_eq!(parsed, expected);
            assert_eq!(parsed.as_str(), text);
        }
        Ok(())
    }

    #[test]
    fn artifact_round_trip() -> SpecgenResult<()> {
        for (text, expected) in [
            ("module", ArtifactKind::Module),
            ("service", ArtifactKind::Service),
            ("agent", ArtifactKind::Agent),
            ("api", ArtifactKind::Api),
            ("event", ArtifactKind::Event),
            ("schema", ArtifactKind::Schema),
            ("foundation", ArtifactKind::Foundation),
            ("architecture_rules", ArtifactKind::ArchitectureRules),
        ] {
            let parsed = ArtifactKind::from_str(text)?;
            assert_eq!(parsed, expected);
            assert_eq!(parsed.as_str(), text);
        }
        Ok(())
    }

    #[test]
    fn unknown_values_are_rejected() {
        assert!(matches!(
            Language::from_str("go"),
            Err(SpecgenError::UnknownValue { kind: "language", .. })
        ));
        assert!(matches!(
            Profile::from_str("nightly"),
            Err(SpecgenError::UnknownValue { kind: "profile", .. })
        ));
        assert!(matches!(
            ArtifactKind::from_str("widget"),
            Err(SpecgenError::UnknownValue { kind: "artifact", .. })
        ));
    }
}
