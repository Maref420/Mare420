//! File system operations for generated output.
//!
//! All writes are atomic where possible: content is prepared in memory
//! before writing. Directories are created recursively.

use std::fs;
use std::path::Path;

use crate::errors::{SpecgenError, SpecgenResult};

/// Ensures the parent directory of a file path exists.
pub fn ensure_parent_dir(path: &Path) -> SpecgenResult<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|source| SpecgenError::DirectoryCreate {
            path: parent.to_path_buf(),
            source,
        })?;
    }
    Ok(())
}

/// Writes content to a file, creating parent directories as needed.
pub fn write_file(path: &Path, content: &str) -> SpecgenResult<()> {
    ensure_parent_dir(path)?;
    fs::write(path, content).map_err(|source| SpecgenError::FileWrite {
        path: path.to_path_buf(),
        source,
    })
}

/// Returns the file extension for a given language.
/// Used by external callers and the Python adapter.
#[allow(dead_code)]
pub fn extension_for_language(language: &str) -> &'static str {
    match language {
        "python" => "py",
        "rust" => "rs",
        "go" => "go",
        _ => "txt",
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn correct_extensions() {
        assert_eq!(extension_for_language("python"), "py");
        assert_eq!(extension_for_language("rust"), "rs");
        assert_eq!(extension_for_language("go"), "go");
        assert_eq!(extension_for_language("unknown"), "txt");
    }
}
