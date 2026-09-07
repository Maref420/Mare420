// MODULE: atlas-feature-engine
// GOVERNANCE: Matrix A - Rust Compute Layer
// CONTRACT: Composite Arbitrage Quality Score 0-100.

/// Computes composite AQS from microstructure features.
pub fn compute_aqs(obi: f64, vpin: f64, spread_bps: i32, latency_var: f64) -> i32 {
    let mut score: i32 = 50;

    // Strong directional signal
    if obi.abs() > 0.5 {
        score += 15;
    }

    // Low toxicity = safe to trade
    if vpin < 0.3 {
        score += 15;
    }

    // Tight spread
    if spread_bps < 30 {
        score += 10;
    }

    // Stable latency
    if latency_var < 5.0 {
        score += 10;
    }

    // Penalties
    if vpin > 0.7 {
        score -= 20;
    }
    if spread_bps > 100 {
        score -= 15;
    }

    score.clamp(0, 100)
}

/// Derives confidence from AQS and VPIN.
pub fn compute_confidence(aqs: i32, vpin: f64) -> f64 {
    let conf: f64 = if aqs >= 70 && vpin < 0.3 {
        0.85
    } else if aqs >= 50 {
        0.65
    } else {
        0.4
    };
    conf.clamp(0.0, 1.0)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_perfect_conditions() {
        let aqs = compute_aqs(0.7, 0.1, 10, 1.0);
        assert_eq!(aqs, 100); // 50+15+15+10+10 = 100
    }

    #[test]
    fn test_worst_conditions() {
        let aqs = compute_aqs(0.1, 0.9, 200, 50.0);
        assert_eq!(aqs, 15); // 50-20-15 = 15
    }

    #[test]
    fn test_mixed_conditions() {
        let aqs = compute_aqs(0.6, 0.25, 25, 3.0);
        assert!(aqs >= 70);
    }

    #[test]
    fn test_confidence_high() {
        assert!((compute_confidence(80, 0.2) - 0.85).abs() < 1e-9);
    }

    #[test]
    fn test_confidence_medium() {
        assert!((compute_confidence(55, 0.5) - 0.65).abs() < 1e-9);
    }

    #[test]
    fn test_confidence_low() {
        assert!((compute_confidence(30, 0.8) - 0.4).abs() < 1e-9);
    }
}
