//! Semantic validation of parsed module metadata.
//!
//! Rules derived from governance documents:
//! - identifier and non-empty rules — `docs/architecture_scaling_rules.md`
//! - agent artifacts are Python-only — no Rust/Go agent template exists
//! - hard stop on any violation — `governance/policies/security-policy.yaml`

use crate::errors::{SpecgenError, SpecgenResult};
use crate::metadata::Metadata;
use crate::module_types::{ArtifactKind, Language};

/// Validates parsed metadata.
///
/// All violations are collected and reported together; any violation
/// stops the pipeline before generation begins.
pub fn validate(metadata: &Metadata) -> SpecgenResult<()> {
    let module = &metadata.module;
    let mut violations: Vec<String> = Vec::new();

    if !is_valid_identifier(&module.name) {
        violations.push(format!(
            "name `{}` must be a snake_case identifier starting with a lowercase letter",
            module.name
        ));
    }

    if module.owner.trim().is_empty() {
        violations.push("owner must not be empty".to_string());
    }

    if module.purpose.trim().is_empty() {
        violations.push("purpose must not be empty".to_string());
    }

    if module.specification_id.trim().is_empty() {
        violations.push("specification_id must not be empty".to_string());
    }

    for (field, entries) in [
        ("responsibilities", &module.responsibilities),
        ("forbidden", &module.forbidden),
        ("dependencies", &module.dependencies),
    ] {
        for entry in entries {
            if entry.trim().is_empty() {
                violations.push(format!("{field} must not contain empty entries"));
            }
        }
    }

    // Governed: agent artifacts are Python-only
    if module.artifact == ArtifactKind::Agent && module.language != Language::Python {
        violations.push(format!(
            "artifact `agent` requires language `python`, got `{}`",
            module.language
        ));
    }

    if violations.is_empty() {
        Ok(())
    } else {
        Err(SpecgenError::MetadataValidation {
            reason: violations.join("; "),
        })
    }
}

fn is_valid_identifier(value: &str) -> bool {
    let mut chars = value.chars();
    let first_ok = chars.next().is_some_and(|c| c.is_ascii_lowercase());
    first_ok && chars.all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '_')
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::Path;

    const VALID_TOML: &str = r#"
[module]
name = "market_data_engine"
artifact = "module"
language = "rust"
profile = "production"
owner = "Rust Core"
purpose = "Exchange websocket connections"
specification_id = "SPEC-0001"
"#;

    fn parse(content: &str) -> SpecgenResult<Metadata> {
        Metadata::parse(content, Path::new("test.toml"))
    }

    fn toml_with_name(name: &str) -> String {
        format!(
            "[module]\nname = \"{name}\"\nartifact = \"module\"\nlanguage = \"rust\"\nprofile = \"production\"\nowner = \"Rust Core\"\npurpose = \"p\"\nspecification_id = \"S-1\"\n"
        )
    }

    fn toml_with(artifact: &str, language: &str) -> String {
        format!(
            "[module]\nname = \"agent_x\"\nartifact = \"{artifact}\"\nlanguage = \"{language}\"\nprofile = \"production\"\nowner = \"Python AI\"\npurpose = \"p\"\nspecification_id = \"S-1\"\n"
        )
    }

    #[test]
    fn valid_metadata_passes() -> SpecgenResult<()> {
        let metadata = parse(VALID_TOML)?;
        validate(&metadata)?;
        Ok(())
    }

    #[test]
    fn rejects_invalid_identifiers() {
        for bad in ["", "Market", "9lives", "_hidden", "dash-name", "space name"] {
            let metadata = parse(&toml_with_name(bad));
            if let Ok(metadata) = metadata {
                assert!(
                    matches!(validate(&metadata), Err(SpecgenError::MetadataValidation { .. })),
                    "expected violation for name `{bad}`"
                );
            }
        }
    }

    #[test]
    fn agent_artifact_requires_python() -> SpecgenResult<()> {
        // Rust agent rejected
        let rust_agent = parse(&toml_with("agent", "rust"))?;
        assert!(matches!(
            validate(&rust_agent),
            Err(SpecgenError::MetadataValidation { .. })
        ));
        // Go agent rejected
        let go_agent = parse(&toml_with("agent", "go"))?;
        assert!(matches!(
            validate(&go_agent),
            Err(SpecgenError::MetadataValidation { .. })
        ));
        // Python agent accepted
        let python_agent = parse(&toml_with("agent", "python"))?;
        validate(&python_agent)?;
        Ok(())
    }

    #[test]
    fn go_module_is_valid() -> SpecgenResult<()> {
        let content = "[module]\nname = \"data_pipeline\"\nartifact = \"module\"\nlanguage = \"go\"\nprofile = \"production\"\nowner = \"Go Team\"\npurpose = \"Data processing\"\nspecification_id = \"SPEC-GO-001\"\n";
        let metadata = parse(content)?;
        validate(&metadata)?;
        Ok(())
    }
}
