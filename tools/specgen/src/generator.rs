//! Core generation orchestrator.
//!
//! Coordinates template selection, rendering, and file output.
//! Pipeline: metadata → validate → select template → render → write files.

use std::path::{Path, PathBuf};

use crate::contract_generator;
use crate::errors::SpecgenResult;
use crate::filesystem;
use crate::go_generator;
use crate::metadata::ModuleMetadata;
use crate::module_types::Language;
use crate::python_generator;
use crate::readme_generator;
use crate::rust_generator;
use crate::template;
use crate::template_selector;

/// Result of a successful generation run.
#[derive(Debug)]
pub struct GenerationResult {
    /// Files that were written.
    pub files_written: Vec<PathBuf>,
}

/// Runs the full generation pipeline for a validated module.
pub fn generate(
    module: &ModuleMetadata,
    output_dir: &Path,
    templates_dir: &Path,
) -> SpecgenResult<GenerationResult> {
    let mut files_written = Vec::new();

    // 1. Generate main module file
    let main_content = generate_main(module, templates_dir)?;
    let main_path = compute_main_path(module, output_dir);
    filesystem::write_file(&main_path, &main_content)?;
    files_written.push(main_path);

    // 2. Generate test file
    let test_content = generate_test(module, templates_dir)?;
    let test_path = compute_test_path(module, output_dir);
    filesystem::write_file(&test_path, &test_content)?;
    files_written.push(test_path);

    // 3. Generate README
    let readme = readme_generator::generate_readme(module);
    let readme_path = output_dir.join("README.md");
    filesystem::write_file(&readme_path, &readme)?;
    files_written.push(readme_path);

    // 4. Language-specific extras
    match module.language {
        Language::Rust => {
            let cargo = rust_generator::generate_cargo_toml(module);
            let cargo_path = output_dir.join("Cargo.toml");
            filesystem::write_file(&cargo_path, &cargo)?;
            files_written.push(cargo_path);
        }
        Language::Go => {
            let go_mod = generate_go_mod(module);
            let go_mod_path = output_dir.join("go.mod");
            filesystem::write_file(&go_mod_path, &go_mod)?;
            files_written.push(go_mod_path);
        }
        Language::Python => {}
    }

    Ok(GenerationResult { files_written })
}

fn generate_main(
    module: &ModuleMetadata,
    templates_dir: &Path,
) -> SpecgenResult<String> {
    let template_path =
        template_selector::select_template(templates_dir, module.language, module.artifact);

    let template_content = if template_path.exists() {
        template::load_template(&template_path)?
    } else {
        generate_fallback(module)
    };

    match module.language {
        Language::Python => python_generator::generate_module(&template_content, module),
        Language::Rust => rust_generator::generate_module(&template_content, module),
        Language::Go => go_generator::generate_module(&template_content, module),
    }
}

fn generate_test(
    module: &ModuleMetadata,
    templates_dir: &Path,
) -> SpecgenResult<String> {
    let template_path = template_selector::select_test_template(templates_dir, module.language);

    let template_content = if template_path.exists() {
        template::load_template(&template_path)?
    } else {
        generate_test_fallback(module)
    };

    match module.language {
        Language::Python => python_generator::generate_test(&template_content, module),
        Language::Rust => rust_generator::generate_test(&template_content, module),
        Language::Go => go_generator::generate_test(&template_content, module),
    }
}

fn compute_main_path(module: &ModuleMetadata, output_dir: &Path) -> PathBuf {
    match module.language {
        Language::Python => output_dir.join(format!("{}.py", module.name)),
        Language::Rust => output_dir.join("src").join(format!("{}.rs", module.name)),
        Language::Go => output_dir.join(format!("{}.go", module.name)),
    }
}

fn compute_test_path(module: &ModuleMetadata, output_dir: &Path) -> PathBuf {
    match module.language {
        Language::Python => output_dir.join(format!("test_{}.py", module.name)),
        Language::Rust => output_dir.join("src").join(format!("{}_test.rs", module.name)),
        Language::Go => output_dir.join(format!("{}_test.go", module.name)),
    }
}

/// Minimal scaffold when no template file exists.
fn generate_fallback(module: &ModuleMetadata) -> String {
    let contract = contract_generator::generate_contract_block(module, module.language.as_str());
    match module.language {
        Language::Python => format!(
            "{}\n\"\"\"{}\"\"\"\n\n\ndef main() -> None:\n    \"\"\"Entry point.\"\"\"\n    pass\n\n\nif __name__ == \"__main__\":\n    main()\n",
            contract, module.purpose
        ),
        Language::Rust => format!(
            "{}\n/// {}\npub fn main() {{\n    // TODO: implement\n}}\n",
            contract, module.purpose
        ),
        Language::Go => format!(
            "{}\npackage {}\n\n// {}\nfunc main() {{\n\t// TODO: implement\n}}\n",
            contract, module.name, module.purpose
        ),
    }
}

/// Minimal test scaffold when no template file exists.
fn generate_test_fallback(module: &ModuleMetadata) -> String {
    match module.language {
        Language::Python => format!(
            "\"\"\"Tests for {}.\"\"\"\nimport unittest\n\n\nclass Test{}(unittest.TestCase):\n    def test_placeholder(self) -> None:\n        self.assertTrue(True)\n\n\nif __name__ == \"__main__\":\n    unittest.main()\n",
            module.name,
            to_pascal_case(&module.name),
        ),
        Language::Rust => "\
#[cfg(test)]\n\
mod tests {\n\
    #[test]\n\
    fn placeholder() {\n\
        assert!(true);\n\
    }\n\
}\n"
            .to_string(),
        Language::Go => format!(
            "package {}\n\nimport \"testing\"\n\nfunc TestPlaceholder(t *testing.T) {{\n\t// TODO: implement\n}}\n",
            module.name
        ),
    }
}

/// Generates a minimal go.mod file.
fn generate_go_mod(module: &ModuleMetadata) -> String {
    format!(
        "// Governed by: {}\n// Owner: {}\nmodule {}\n\ngo 1.22\n",
        module.specification_id, module.owner, module.name,
    )
}

fn to_pascal_case(snake: &str) -> String {
    snake
        .split('_')
        .map(|part| {
            let mut chars = part.chars();
            match chars.next() {
                Some(c) => c.to_uppercase().to_string() + &chars.collect::<String>(),
                None => String::new(),
            }
        })
        .collect()
}
