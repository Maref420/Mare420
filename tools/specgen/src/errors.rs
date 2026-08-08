//! Central error definitions for SpecGen.
//!
//! This module is the dependency root of the crate: it references no
//! other SpecGen module, keeping the dependency graph acyclic.

use std::path::PathBuf;
use thiserror::Error;

/// Central error type for all SpecGen operations.
#[derive(Debug, Error)]
pub enum SpecgenError {
    /// A scalar value matched no known enumeration variant.
    #[error("unknown {kind} value: `{value}`")]
    UnknownValue { kind: &'static str, value: String },

    /// The metadata file could not be read from disk.
    #[error("failed to read metadata file `{path}`: {source}")]
    MetadataRead {
        path: PathBuf,
        source: std::io::Error,
    },

    /// The metadata content is not valid SpecGen TOML.
    #[error("failed to parse metadata file `{path}`: {message}")]
    MetadataParse { path: PathBuf, message: String },

    /// Parsed metadata failed semantic validation.
    #[error("metadata validation failed: {reason}")]
    MetadataValidation { reason: String },
}

/// Result alias used across SpecGen modules.
pub type SpecgenResult<T> = Result<T, SpecgenError>;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn unknown_value_message_is_stable() {
        let error = SpecgenError::UnknownValue {
            kind: "language",
            value: "go".to_string(),
        };
        assert_eq!(error.to_string(), "unknown language value: `go`");
    }
}
