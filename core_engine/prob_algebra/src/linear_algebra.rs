//! Linear Algebra Operations using nalgebra.

use crate::{AlgebraError, AlgebraRequest, AlgebraResponse};
use nalgebra::DMatrix;
use serde_json::json;

pub fn multiply(req: &AlgebraRequest) -> Result<AlgebraResponse, AlgebraError> {
    let params = &req.parameters;

    let a_data = params.get("matrix_a")
        .and_then(|v| v.as_array())
        .ok_or_else(|| AlgebraError::ComputationFailed("missing matrix_a".into()))?;
    let b_data = params.get("matrix_b")
        .and_then(|v| v.as_array())
        .ok_or_else(|| AlgebraError::ComputationFailed("missing matrix_b".into()))?;

    let rows_a = params.get("rows_a").and_then(|v| v.as_u64()).unwrap_or(0) as usize;
    let cols_a = params.get("cols_a").and_then(|v| v.as_u64()).unwrap_or(0) as usize;
    let rows_b = params.get("rows_b").and_then(|v| v.as_u64()).unwrap_or(0) as usize;
    let cols_b = params.get("cols_b").and_then(|v| v.as_u64()).unwrap_or(0) as usize;

    if rows_a == 0 || cols_a == 0 || rows_b == 0 || cols_b == 0 {
        return Err(AlgebraError::InvalidDimensions {
            expected: "non-zero dimensions".into(),
            actual: format!("{}x{}, {}x{}", rows_a, cols_a, rows_b, cols_b),
        });
    }

    if cols_a != rows_b {
        return Err(AlgebraError::InvalidDimensions {
            expected: format!("cols_a ({}) == rows_b ({})", cols_a, rows_b),
            actual: "dimension mismatch".into(),
        });
    }

    let parse_matrix = |data: &[serde_json::Value], rows: usize, cols: usize| -> Result<Vec<f64>, AlgebraError> {
        if data.len() != rows * cols {
            return Err(AlgebraError::InvalidDimensions {
                expected: format!("{}", rows * cols),
                actual: format!("{}", data.len()),
            });
        }
        let mut elements = Vec::with_capacity(rows * cols);
        for val in data {
            let num = val.as_f64().ok_or_else(|| {
                AlgebraError::ComputationFailed("non-float in matrix".into())
            })?;
            elements.push(num);
        }
        Ok(elements)
    };

    let a_elements = parse_matrix(a_data, rows_a, cols_a)?;
    let b_elements = parse_matrix(b_data, rows_b, cols_b)?;

    let mat_a = DMatrix::from_row_slice(rows_a, cols_a, &a_elements);
    let mat_b = DMatrix::from_row_slice(rows_b, cols_b, &b_elements);

    let result = mat_a * mat_b;

    let result_vec: Vec<f64> = result.iter().copied().collect();

    Ok(AlgebraResponse {
        success: true,
        request_id: req.request_id.clone(),
        result: Some(json!({
            "result_matrix": result_vec,
            "rows": rows_a,
            "cols": cols_b,
        })),
        error: None,
    })
}
