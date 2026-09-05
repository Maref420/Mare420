//! Selects the correct template file based on language and artifact kind.
//!
//! Governance source: template layout under `tools/specgen/templates/`.
//! Agent artifacts are Python-only (enforced by validator).

use std::path::{Path, PathBuf};

use crate::module_types::{ArtifactKind, Language};

/// Returns the template file path for a given language + artifact combination.
pub fn select_template(
    templates_dir: &Path,
    language: Language,
    artifact: ArtifactKind,
) -> PathBuf {
    let lang_dir = language_dir(language);
    let filename = match artifact {
        ArtifactKind::Module => "module",
        ArtifactKind::Service => "service",
        ArtifactKind::Agent => "agent",
        _ => "module",
    };
    let ext = language_ext(language);
    templates_dir.join(lang_dir).join(format!("{}.{}", filename, ext))
}

/// Returns the test template path for a given language.
pub fn select_test_template(templates_dir: &Path, language: Language) -> PathBuf {
    let lang_dir = language_dir(language);
    let ext = language_ext(language);
    templates_dir.join(lang_dir).join(format!("test.{}", ext))
}

fn language_dir(language: Language) -> &'static str {
    match language {
        Language::Python => "python",
        Language::Rust => "rust",
        Language::Go => "go",
    }
}

fn language_ext(language: Language) -> &'static str {
    match language {
        Language::Python => "py",
        Language::Rust => "rs",
        Language::Go => "go",
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn all_language_template_paths() {
        let dir = Path::new("/tpl");
        assert_eq!(
            select_template(dir, Language::Python, ArtifactKind::Module),
            PathBuf::from("/tpl/python/module.py")
        );
        assert_eq!(
            select_template(dir, Language::Rust, ArtifactKind::Service),
            PathBuf::from("/tpl/rust/service.rs")
        );
        assert_eq!(
            select_template(dir, Language::Go, ArtifactKind::Module),
            PathBuf::from("/tpl/go/module.go")
        );
    }

    #[test]
    fn all_test_template_paths() {
        let dir = Path::new("/tpl");
        assert_eq!(
            select_test_template(dir, Language::Python),
            PathBuf::from("/tpl/python/test.py")
        );
        assert_eq!(
            select_test_template(dir, Language::Rust),
            PathBuf::from("/tpl/rust/test.rs")
        );
        assert_eq!(
            select_test_template(dir, Language::Go),
            PathBuf::from("/tpl/go/test.go")
        );
    }
}
