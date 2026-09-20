//! Markov Chain Transition Engine.
//! Uses nalgebra for deterministic matrix operations.

use crate::{AlgebraError, AlgebraRequest, AlgebraResponse};
use nalgebra::DMatrix;
use serde_json::json;

pub fn compute_transition(req: &AlgebraRequest) -> Result<AlgebraResponse, AlgebraError> {
    let params = &req.parameters;

    let states = params.get("states")
        .and_then(|v| v.as_u64())
        .ok_or_else(|| AlgebraError::ComputationFailed("missing 'states' parameter".into()))?
        as usize;

    let matrix_data = params.get("transition_matrix")
        .and_then(|v| v.as_array())
        .ok_or_else(|| AlgebraError::ComputationFailed("missing 'transition_matrix'".into()))?;

    if matrix_data.len() != states * states {
        return Err(AlgebraError::InvalidDimensions {
            expected: format!("{}x{}", states, states),
            actual: format!("{}", matrix_data.len()),
        });
    }

    let mut elements = Vec::with_capacity(states * states);
    for val in matrix_data {
        let num = val.as_f64().ok_or_else(|| {
            AlgebraError::ComputationFailed("non-float value in matrix".into())
        })?;
        if !(0.0..=1.0).contains(&num) {
            return Err(AlgebraError::InvalidProbability(num));
        }
        elements.push(num);
    }

    let transition_matrix = DMatrix::from_row_slice(states, states, &elements);

    let current_state = params.get("current_state")
        .and_then(|v| v.as_u64())
        .ok_or_else(|| AlgebraError::ComputationFailed("missing 'current_state'".into()))?
        as usize;

    if current_state >= states {
        return Err(AlgebraError::InvalidDimensions {
            expected: format!("state < {}", states),
            actual: format!("{}", current_state),
        });
    }

    // Extract row for current state (next step probabilities)
    let next_probs: Vec<f64> = (0..states)
        .map(|col| transition_matrix[(current_state, col)])
        .collect();

    Ok(AlgebraResponse {
        success: true,
        request_id: req.request_id.clone(),
        result: Some(json!({
            "next_state_probabilities": next_probs,
            "states_count": states,
        })),
        error: None,
    })
}
