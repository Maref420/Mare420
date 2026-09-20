//! Monte Carlo Simulation Engine.
//! Uses ChaCha RNG for deterministic, reproducible simulations.

use crate::{AlgebraError, AlgebraRequest, AlgebraResponse};
use rand::SeedableRng;
use rand_chacha::ChaCha8Rng;
use serde_json::json;

pub fn simulate(req: &AlgebraRequest) -> Result<AlgebraResponse, AlgebraError> {
    let params = &req.parameters;

    let iterations = params.get("iterations")
        .and_then(|v| v.as_u64())
        .ok_or_else(|| AlgebraError::ComputationFailed("missing iterations".into()))?;

    if iterations > 1_000_000 {
        return Err(AlgebraError::ComputationFailed(
            "iterations capped at 1,000,000 for latency safety".into(),
        ));
    }

    let seed = params.get("seed")
        .and_then(|v| v.as_u64())
        .unwrap_or(42);

    let mean = params.get("mean")
        .and_then(|v| v.as_f64())
        .ok_or_else(|| AlgebraError::ComputationFailed("missing mean".into()))?;

    let std_dev = params.get("std_dev")
        .and_then(|v| v.as_f64())
        .ok_or_else(|| AlgebraError::ComputationFailed("missing std_dev".into()))?;

    if std_dev <= 0.0 {
        return Err(AlgebraError::InvalidProbability(std_dev));
    }

    // Deterministic RNG per governance rule PA-3
    let mut rng = ChaCha8Rng::seed_from_u64(seed);

    use rand::Rng;
    let mut sum = 0.0f64;
    let mut min_val = f64::MAX;
    let mut max_val = f64::MIN;

    for _ in 0..iterations {
        // Box-Muller transform for normal distribution (no external dep needed)
        let u1: f64 = rng.gen_range(0.0001..1.0);
        let u2: f64 = rng.gen_range(0.0001..1.0);
        let z = (-2.0 * u1.ln()).sqrt() * (2.0 * std::f64::consts::PI * u2).cos();
        let sample = mean + std_dev * z;

        sum += sample;
        if sample < min_val { min_val = sample; }
        if sample > max_val { max_val = sample; }
    }

    let iter_f64 = iterations as f64;
    let avg = sum / iter_f64;

    Ok(AlgebraResponse {
        success: true,
        request_id: req.request_id.clone(),
        result: Some(json!({
            "mean_result": avg,
            "min": min_val,
            "max": max_val,
            "iterations": iterations,
            "seed": seed,
        })),
        error: None,
    })
}
