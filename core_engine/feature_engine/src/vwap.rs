// MODULE: atlas-feature-engine
// GOVERNANCE: Matrix A - Rust Compute Layer
// CONTRACT: VWAP and OBV computation from trade records.
use crate::models::TradeRecord;
use crate::EngineError;

pub fn compute_vwap(trades: &[TradeRecord]) -> Result<i64, EngineError> {
    if trades.is_empty() { return Err(EngineError::InvalidData("no trades for VWAP".into())); }
    let mut cum_vol = 0.0_f64;
    let mut cum_pv = 0.0_f64;
    for t in trades {
        if t.quantity <= 0.0 { continue; }
        if t.price_scaled <= 0 { return Err(EngineError::InvalidData(format!("invalid price: {}", t.price_scaled))); }
        cum_vol += t.quantity;
        cum_pv += t.price_scaled as f64 * t.quantity;
    }
    if cum_vol == 0.0 { return Err(EngineError::InvalidData("zero volume".into())); }
    Ok((cum_pv / cum_vol).round() as i64)
}

pub fn compute_obv(trades: &[TradeRecord]) -> Result<f64, EngineError> {
    if trades.is_empty() { return Err(EngineError::InvalidData("no trades for OBV".into())); }
    let mut obv = 0.0_f64;
    for t in trades {
        if t.quantity <= 0.0 { continue; }
        match t.side.to_lowercase().as_str() {
            "buy" | "b" => obv += t.quantity,
            "sell" | "s" => obv -= t.quantity,
            _ => {}
        }
    }
    Ok(obv)
}

pub fn compute_vwap_deviation_bps(current_price_scaled: i64, vwap_scaled: i64) -> Result<i32, EngineError> {
    if vwap_scaled <= 0 { return Err(EngineError::InvalidData("vwap must be positive".into())); }
    if current_price_scaled <= 0 { return Err(EngineError::InvalidData("price must be positive".into())); }
    let dev = ((current_price_scaled as f64 - vwap_scaled as f64) / vwap_scaled as f64) * 10_000.0;
    Ok(dev.round() as i32)
}

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct VwapSignal {
    pub symbol: String,
    pub vwap_scaled: i64,
    pub current_price_scaled: i64,
    pub deviation_bps: i32,
    pub obv: f64,
    pub direction: String,
    pub confidence: f64,
    pub trade_count: usize,
    pub timestamp_ns: u64,
}

pub fn generate_vwap_signal(
    symbol: &str,
    trades: &[TradeRecord],
    current_price_scaled: i64,
    timestamp_ns: u64,
) -> Result<VwapSignal, EngineError> {
    let vwap = compute_vwap(trades)?;
    let obv = compute_obv(trades)?;
    let dev_bps = compute_vwap_deviation_bps(current_price_scaled, vwap)?;
    let direction = if dev_bps < -50 && obv > 0.0 {
        "BUY"
    } else if dev_bps > 50 && obv < 0.0 {
        "SELL"
    } else {
        "NEUTRAL"
    };
    let dev_abs = dev_bps.unsigned_abs() as f64;
    let base_conf = (dev_abs / 500.0).min(1.0);
    let obv_boost = if (dev_bps < 0 && obv > 0.0) || (dev_bps > 0 && obv < 0.0) {
        0.2
    } else {
        0.0
    };
    let confidence = (base_conf + obv_boost).min(1.0);
    Ok(VwapSignal {
        symbol: symbol.to_string(),
        vwap_scaled: vwap,
        current_price_scaled,
        deviation_bps: dev_bps,
        obv,
        direction: direction.to_string(),
        confidence,
        trade_count: trades.len(),
        timestamp_ns,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::models::TradeRecord;

    fn mk(price: i64, qty: f64, side: &str) -> TradeRecord {
        TradeRecord { price_scaled: price, quantity: qty, side: side.into() }
    }

    #[test]
    fn test_vwap_basic() {
        let t = vec![mk(100_000, 1.0, "buy"), mk(101_000, 2.0, "buy")];
        let v = compute_vwap(&t).unwrap();
        assert_eq!(v, 100_667);
    }

    #[test]
    fn test_vwap_empty() {
        assert!(compute_vwap(&[]).is_err());
    }

    #[test]
    fn test_obv_net() {
        let t = vec![mk(100_000, 1.0, "buy"), mk(100_000, 0.5, "sell")];
        assert!((compute_obv(&t).unwrap() - 0.5).abs() < 0.001);
    }

    #[test]
    fn test_deviation_bps() {
        assert_eq!(compute_vwap_deviation_bps(105_000, 100_000).unwrap(), 500);
        assert_eq!(compute_vwap_deviation_bps(95_000, 100_000).unwrap(), -500);
    }

    #[test]
    fn test_signal_buy() {
        let t = vec![mk(90_000, 5.0, "buy"), mk(91_000, 3.0, "buy")];
        let sig = generate_vwap_signal("BTC", &t, 85_000, 1_000).unwrap();
        assert_eq!(sig.direction, "BUY");
        assert!(sig.confidence > 0.0);
    }

    #[test]
    fn test_signal_neutral() {
        let t = vec![mk(100_000, 1.0, "buy"), mk(100_100, 1.0, "sell")];
        let sig = generate_vwap_signal("ETH", &t, 100_050, 1_000).unwrap();
        assert_eq!(sig.direction, "NEUTRAL");
    }
}
