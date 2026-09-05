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
    Go,
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
    pub fn as_str(self) -> &'static str {
        match self {
            Language::Rust => "rust",
            Language::Python => "python",
            Language::Go => "go",
        }
    }
}

impl Profile {
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
            "go" => Ok(Language::Go),
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
        for (text, expected) in [
            ("rust", Language::Rust),
            ("python", Language::Python),
            ("go", Language::Go),
        ] {
            let parsed = Language::from_str(text)?;
            assert_eq!(parsed, expected);
            assert_eq!(parsed.as_str(), text);
        }
        Ok(())
    }

    #[test]
    fn unknown_values_are_rejected() {
        assert!(matches!(
            Language::from_str("java"),
            Err(SpecgenError::UnknownValue { kind: "language", .. })
        ));
    }
}
