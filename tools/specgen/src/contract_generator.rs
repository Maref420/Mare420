//! Contract stub generator.
//!
//! Generates contract compliance markers in generated code.
//! Governance source: `contracts/schemas/` JSON schemas.

use crate::metadata::ModuleMetadata;

/// Generates a contract compliance doc-comment block.
pub fn generate_contract_block(module: &ModuleMetadata, language: &str) -> String {
    let comment_prefix = match language {
        "python" => "#",
        "rust" => "//",
        "go" => "//",
        _ => "//",
    };

    format!(
        r#"{p} Contract Compliance
{p} Specification: {spec_id}
{p} Artifact:      {artifact}
{p} Language:      {language}
{p} Profile:       {profile}
{p} Owner:         {owner}
{p}
{p} Responsibilities:
{resp}
{p}
{p} Forbidden:
{forb}
"#,
        p = comment_prefix,
        spec_id = module.specification_id,
        artifact = module.artifact.as_str(),
        language = module.language.as_str(),
        profile = module.profile.as_str(),
        owner = module.owner,
        resp = format_list(comment_prefix, &module.responsibilities),
        forb = format_list(comment_prefix, &module.forbidden),
    )
}

fn format_list(prefix: &str, items: &[String]) -> String {
    if items.is_empty() {
        format!("{}   _None_", prefix)
    } else {
        items
            .iter()
            .map(|item| format!("{}   - {}", prefix, item))
            .collect::<Vec<_>>()
            .join("\n")
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::metadata::Metadata;
    use std::path::Path;

    #[test]
    fn python_contract_block_uses_hash() {
        let meta = Metadata::parse(
            "[module]\nname=\"x\"\nartifact=\"module\"\nlanguage=\"python\"\nprofile=\"production\"\nowner=\"T\"\npurpose=\"p\"\nspecification_id=\"S1\"\n",
            Path::new("t.toml"),
        ).unwrap();
        let block = generate_contract_block(&meta.module, "python");
        assert!(block.starts_with("# Contract Compliance"));
    }

    #[test]
    fn rust_contract_block_uses_slash() {
        let meta = Metadata::parse(
            "[module]\nname=\"x\"\nartifact=\"module\"\nlanguage=\"rust\"\nprofile=\"production\"\nowner=\"T\"\npurpose=\"p\"\nspecification_id=\"S1\"\n",
            Path::new("t.toml"),
        ).unwrap();
        let block = generate_contract_block(&meta.module, "rust");
        assert!(block.starts_with("// Contract Compliance"));
    }
}
