//! Central error definitions for SpecGen.

use std::path::PathBuf;
use thiserror::Error;

#[derive(Debug, Error)]
pub enum SpecgenError {
    #[error("unknown {kind} value: `{value}`")]
    UnknownValue { kind: &'static str, value: String },

    #[error("failed to read metadata file `{path}`: {source}")]
    MetadataRead { path: PathBuf, source: std::io::Error },

    #[error("failed to parse metadata file `{path}`: {message}")]
    MetadataParse { path: PathBuf, message: String },

    #[error("metadata validation failed: {reason}")]
    MetadataValidation { reason: String },

    #[error("failed to read template `{path}`: {source}")]
    TemplateRead { path: PathBuf, source: std::io::Error },

    #[error("failed to create directory `{path}`: {source}")]
    DirectoryCreate { path: PathBuf, source: std::io::Error },

    #[error("failed to write file `{path}`: {source}")]
    FileWrite { path: PathBuf, source: std::io::Error },
}

pub type SpecgenResult<T> = Result<T, SpecgenError>;
