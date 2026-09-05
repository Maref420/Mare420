//! Metadata loading and deserialization for SpecGen.
//!
//! The field set is assembled exclusively from governance documents:
//! - `owner`, `responsibilities`, `forbidden`: `02_MODULE_OWNERSHIP.md`
//! - `name`, `purpose`, `dependencies`: `architecture_scaling_rules.md`
//! - `specification_id`: `engine-contract-v1.json` (`metadata.required`)
//! - `language` / `profile`: governance registries
//!
//! Unknown fields are rejected, mirroring the engine-contract rule
//! `unknown_fields_rejected: true`.

use std::fs;
use std::path::Path;

use serde::{Deserialize, Serialize};

use crate::errors::{SpecgenError, SpecgenResult};
use crate::module_types::{ArtifactKind, Language, Profile};

/// Top-level metadata document supplied via `--metadata`.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Metadata {
    /// The module specification to generate.
    pub module: ModuleMetadata,
}

/// Specification of a single generated module.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ModuleMetadata {
    /// Unique module identifier (snake_case).
    pub name: String,
    /// Artifact family to generate.
    pub artifact: ArtifactKind,
    /// Approved implementation language.
    pub language: Language,
    /// Registered profile.
    pub profile: Profile,
    /// Accountable owner group.
    pub owner: String,
    /// Operational purpose of the module.
    pub purpose: String,
    /// Reference to the governing specification document.
    pub specification_id: String,
    /// Declared responsibilities; empty when unspecified.
    #[serde(default)]
    pub responsibilities: Vec<String>,
    /// Explicitly forbidden capabilities; empty when unspecified.
    #[serde(default)]
    pub forbidden: Vec<String>,
    /// Declared dependencies; empty when unspecified.
    #[serde(default)]
    pub dependencies: Vec<String>,
}

impl Metadata {
    /// Reads and deserializes a TOML metadata document from disk.
    pub fn load(path: &Path) -> SpecgenResult<Self> {
        let content = fs::read_to_string(path).map_err(|source| SpecgenError::MetadataRead {
            path: path.to_path_buf(),
            source,
        })?;
        Self::parse(&content, path)
    }

    /// Deserializes TOML content into [`Metadata`].
    pub fn parse(content: &str, path: &Path) -> SpecgenResult<Self> {
        toml::from_str(content).map_err(|err| SpecgenError::MetadataParse {
            path: path.to_path_buf(),
            message: err.to_string(),
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const VALID_TOML: &str = r#"
[module]
name = "market_data_engine"
artifact = "module"
language = "rust"
profile = "production"
owner = "Rust Core"
purpose = "Exchange websocket connections and orderbook processing"
specification_id = "SPEC-0001"
responsibilities = ["Orderbook processing"]
forbidden = ["AI decisions"]
"#;

    #[test]
    fn parses_valid_metadata() -> SpecgenResult<()> {
        let metadata = Metadata::parse(VALID_TOML, Path::new("test.toml"))?;
        assert_eq!(metadata.module.name, "market_data_engine");
        assert_eq!(metadata.module.artifact, ArtifactKind::Module);
        assert_eq!(metadata.module.language, Language::Rust);
        assert_eq!(metadata.module.profile, Profile::Production);
        assert_eq!(metadata.module.owner, "Rust Core");
        assert_eq!(metadata.module.responsibilities.len(), 1);
        assert!(metadata.module.dependencies.is_empty());
        Ok(())
    }

    #[test]
    fn rejects_unknown_fields() {
        let content = "[module]\nname = \"x\"\nunexpected = 1\n";
        let result = Metadata::parse(content, Path::new("test.toml"));
        assert!(matches!(result, Err(SpecgenError::MetadataParse { .. })));
    }

    #[test]
    fn missing_file_reports_read_error() {
        let result = Metadata::load(Path::new("nonexistent-metadata.toml"));
        assert!(matches!(result, Err(SpecgenError::MetadataRead { .. })));
    }
}
