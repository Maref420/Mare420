//! Probability Distribution Evaluations using statrs.

use crate::{AlgebraError, AlgebraRequest, AlgebraResponse};
use serde_json::json;
use statrs::distribution::{Continuous, ContinuousCDF, Normal};

pub fn evaluate_pdf(req: &AlgebraRequest) -> Result<AlgebraResponse, AlgebraError> {
    let params = &req.parameters;

    let dist_type = params.get("distribution")
        .and_then(|v| v.as_str())
        .ok_or_else(|| AlgebraError::ComputationFailed("missing distribution type".into()))?;

    let x = params.get("x")
        .and_then(|v| v.as_f64())
        .ok_or_else(|| AlgebraError::ComputationFailed("missing x value".into()))?;

    match dist_type {
        "normal" => {
            let mean = params.get("mean").and_then(|v| v.as_f64()).unwrap_or(0.0);
            let std_dev = params.get("std_dev").and_then(|v| v.as_f64()).unwrap_or(1.0);

            if std_dev <= 0.0 {
                return Err(AlgebraError::InvalidProbability(std_dev));
            }

            let normal = Normal::new(mean, std_dev)
                .map_err(|e| AlgebraError::ComputationFailed(format!("normal init: {}", e)))?;

            let pdf = normal.pdf(x);
            let cdf = normal.cdf(x);

            Ok(AlgebraResponse {
                success: true,
                request_id: req.request_id.clone(),
                result: Some(json!({
                    "pdf": pdf,
                    "cdf": cdf,
                    "distribution": "normal",
                    "x": x,
                })),
                error: None,
            })
        }
        _ => Err(AlgebraError::ComputationFailed(format!(
            "unsupported distribution: {}",
            dist_type
        ))),
    }
}
