//! Project structure model.
//!
//! Defines the output layout for each language/artifact combination.
//! Governance source: `architecture_scaling_rules.md` module boundaries.
//!
//! `compute_layout` is part of the public API for external callers
//! (e.g., the Python adapter) to predict output structure.

use std::path::{Path, PathBuf};

use crate::metadata::ModuleMetadata;
use crate::module_types::Language;

/// Computes the output file layout for a module.
/// Used by external callers to predict generated file paths.
#[allow(dead_code)]
pub fn compute_layout(module: &ModuleMetadata, output_dir: &Path) -> Vec<PathBuf> {
    let name = &module.name;
    let mut files = Vec::new();

    match module.language {
        Language::Python => {
            files.push(output_dir.join(format!("{}.py", name)));
            files.push(output_dir.join(format!("test_{}.py", name)));
        }
        Language::Rust => {
            files.push(output_dir.join("src").join(format!("{}.rs", name)));
            files.push(output_dir.join("src").join(format!("{}_test.rs", name)));
            files.push(output_dir.join("Cargo.toml"));
        }
        Language::Go => {
            files.push(output_dir.join(format!("{}.go", name)));
            files.push(output_dir.join(format!("{}_test.go", name)));
            files.push(output_dir.join("go.mod"));
        }
    }

    files.push(output_dir.join("README.md"));
    files
}
