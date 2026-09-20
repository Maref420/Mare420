//! Atlas AI Probability & Algebra Engine
//!
//! GOVERNANCE: Matrix A - Rust Compute Layer
//! CONTRACT: ipc-binary-v1.spec.yaml compatible responses
//! SAFETY: No unsafe code, no unwrap, no expect, no panic.

#![forbid(unsafe_code)]
#![deny(clippy::unwrap_used)]
#![deny(clippy::expect_used)]
#![deny(clippy::panic)]

pub mod distributions;
pub mod linear_algebra;
pub mod markov;
pub mod monte_carlo;

use serde::{Deserialize, Serialize};
use thiserror::Error;

#[derive(Debug, Error)]
pub enum AlgebraError {
    #[error("invalid matrix dimensions: expected {expected}, got {actual}")]
    InvalidDimensions { expected: String, actual: String },
    #[error("probability out of bounds: {0}")]
    InvalidProbability(f64),
    #[error("computation failed: {0}")]
    ComputationFailed(String),
    #[error("serialization error: {0}")]
    SerializationError(String),
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AlgebraRequest {
    pub request_id: String,
    pub operation: String,
    pub parameters: serde_json::Value,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AlgebraResponse {
    pub success: bool,
    pub request_id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub result: Option<serde_json::Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
}

/// Main dispatch function for probability and algebra operations.
/// Returns Result to enforce explicit error handling (no unwrap).
pub fn process_algebra_request(req: &AlgebraRequest) -> Result<AlgebraResponse, AlgebraError> {
    match req.operation.as_str() {
        "markov_transition" => markov::compute_transition(req),
        "matrix_multiply" => linear_algebra::multiply(req),
        "monte_carlo_sim" => monte_carlo::simulate(req),
        "distribution_pdf" => distributions::evaluate_pdf(req),
        _ => Err(AlgebraError::ComputationFailed(format!(
            "unknown operation: {}",
            req.operation
        ))),
    }
}
