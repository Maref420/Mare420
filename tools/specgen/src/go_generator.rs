//! Go code generator.
//!
//! Produces governance-compliant Go module scaffolds from templates.
//! Governance source: `governance/policies/go-policy.yaml`.

use std::collections::HashMap;

use crate::constants;
use crate::errors::SpecgenResult;
use crate::metadata::ModuleMetadata;
use crate::template;

/// Generates Go module source code from a template.
pub fn generate_module(
    template_content: &str,
    module: &ModuleMetadata,
) -> SpecgenResult<String> {
    let vars = build_vars(module);
    let header = render_header(constants::GO_HEADER, module);
    let body = template::render(template_content, &vars);
    Ok(format!("{}\n{}", header, body))
}

/// Generates Go test file from a template.
pub fn generate_test(
    template_content: &str,
    module: &ModuleMetadata,
) -> SpecgenResult<String> {
    let vars = build_vars(module);
    let header = render_header(constants::GO_HEADER, module);
    let body = template::render(template_content, &vars);
    Ok(format!("{}\n{}", header, body))
}

fn build_vars(module: &ModuleMetadata) -> HashMap<String, String> {
    let mut vars = HashMap::new();
    vars.insert("module_name".into(), module.name.clone());
    vars.insert("owner".into(), module.owner.clone());
    vars.insert("purpose".into(), module.purpose.clone());
    vars.insert("specification_id".into(), module.specification_id.clone());
    vars.insert("profile".into(), module.profile.as_str().to_string());
    vars.insert(
        "responsibilities".into(),
        module.responsibilities.join(", "),
    );
    vars.insert("forbidden".into(), module.forbidden.join(", "));
    vars.insert(
        "dependencies".into(),
        module.dependencies.join(", "),
    );
    vars
}

fn render_header(header_template: &str, module: &ModuleMetadata) -> String {
    let mut vars = HashMap::new();
    vars.insert("specification_id".into(), module.specification_id.clone());
    vars.insert("owner".into(), module.owner.clone());
    vars.insert("language".into(), "go".to_string());
    vars.insert("profile".into(), module.profile.as_str().to_string());
    template::render(header_template, &vars)
}
