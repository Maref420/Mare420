// MODULE: atlas-feature-engine::strategy::primitives
// GOVERNANCE: Matrix A - Rust Compute Layer
// CONTRACT: Reusable market microstructure primitives.
// No business logic here — pure math on market data.
// WARNING: No unwrap/expect/panic. All errors via Result.
use std::collections::HashMap;
use crate::models::{OrderbookLevel, TradeRecord};
use crate::EngineError;

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct IcebergSignal {
    pub detected: bool,
    pub side: String,
    pub price_level: i64,
    pub visible_qty: f64,
    pub executed_qty: f64,
    pub hidden_ratio: f64,
    pub confidence: f64,
}

pub fn detect_iceberg(
    trades: &[TradeRecord],
    levels: &[OrderbookLevel],
) -> Result<IcebergSignal, EngineError> {
    if trades.is_empty() {
        return Err(EngineError::InvalidData("no trades for iceberg detection".into()));
    }
    let mut trades_by_price: HashMap<i64, (f64, String)> = HashMap::new();
    for t in trades {
        let entry = trades_by_price.entry(t.price_scaled).or_insert((0.0, t.side.clone()));
        entry.0 += t.quantity;
    }
    let mut best_iceberg: Option<IcebergSignal> = None;
    let mut best_ratio = 1.0_f64;
    for (price, (executed, side)) in &trades_by_price {
        let visible = levels.iter()
            .find(|l| l.price_scaled == *price)
            .map(|l| l.quantity)
            .unwrap_or(0.0);
        if visible > 0.0 && *executed > visible {
            let ratio = executed / visible;
            if ratio > best_ratio {
                best_ratio = ratio;
                best_iceberg = Some(IcebergSignal {
                    detected: true, side: side.clone(), price_level: *price,
                    visible_qty: visible, executed_qty: *executed,
                    hidden_ratio: ratio, confidence: (ratio / 5.0).min(1.0),
                });
            }
        }
    }
    Ok(best_iceberg.unwrap_or(IcebergSignal {
        detected: false, side: "none".into(), price_level: 0,
        visible_qty: 0.0, executed_qty: 0.0, hidden_ratio: 0.0, confidence: 0.0,
    }))
}

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct FvgSignal {
    pub detected: bool,
    pub gap_type: String,
    pub gap_size_scaled: i64,
    pub gap_bps: i32,
    pub confidence: f64,
}

pub fn detect_fvg(
    bids: &[OrderbookLevel], asks: &[OrderbookLevel],
) -> Result<FvgSignal, EngineError> {
    if bids.is_empty() || asks.is_empty() {
        return Err(EngineError::EmptyOrderbook("need bids and asks for FVG".into()));
    }
    let best_bid = bids.first().ok_or_else(|| EngineError::EmptyOrderbook("no bids".into()))?;
    let best_ask = asks.first().ok_or_else(|| EngineError::EmptyOrderbook("no asks".into()))?;
    let spread = best_ask.price_scaled - best_bid.price_scaled;
    if spread <= 0 || best_bid.price_scaled <= 0 {
        return Ok(FvgSignal { detected: false, gap_type: "none".into(), gap_size_scaled: 0, gap_bps: 0, confidence: 0.0 });
    }
    let second_bid = bids.get(1).map(|l| l.price_scaled).unwrap_or(best_bid.price_scaled);
    let second_ask = asks.get(1).map(|l| l.price_scaled).unwrap_or(best_ask.price_scaled);
    let bid_gap = best_bid.price_scaled - second_bid;
    let ask_gap = second_ask - best_ask.price_scaled;
    let mid = (best_bid.price_scaled + best_ask.price_scaled) as f64 / 2.0;
    let threshold_bps = 20_i64;
    if bid_gap > threshold_bps {
        let bps = ((bid_gap as f64 / mid) * 10_000.0).round() as i32;
        Ok(FvgSignal { detected: true, gap_type: "bullish".into(), gap_size_scaled: bid_gap, gap_bps: bps, confidence: (bps as f64 / 100.0).min(1.0) })
    } else if ask_gap > threshold_bps {
        let bps = ((ask_gap as f64 / mid) * 10_000.0).round() as i32;
        Ok(FvgSignal { detected: true, gap_type: "bearish".into(), gap_size_scaled: ask_gap, gap_bps: bps, confidence: (bps as f64 / 100.0).min(1.0) })
    } else {
        Ok(FvgSignal { detected: false, gap_type: "none".into(), gap_size_scaled: 0, gap_bps: 0, confidence: 0.0 })
    }
}

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct SweepSignal {
    pub detected: bool,
    pub direction: String,
    pub sweep_price: i64,
    pub volume_spike_ratio: f64,
    pub confidence: f64,
}

pub fn detect_liquidity_sweep(trades: &[TradeRecord]) -> Result<SweepSignal, EngineError> {
    if trades.len() < 5 {
        return Err(EngineError::InvalidData("need >= 5 trades for sweep detection".into()));
    }
    let avg_qty: f64 = trades.iter().map(|t| t.quantity).sum::<f64>() / trades.len() as f64;
    if avg_qty <= 0.0 {
        return Err(EngineError::InvalidData("zero average volume".into()));
    }
    let first = &trades[0];
    let last = trades.last().unwrap_or(first);
    let prices: Vec<i64> = trades.iter().map(|t| t.price_scaled).collect();
    let min_price = prices.iter().copied().min().unwrap_or(0);
    let max_price = prices.iter().copied().max().unwrap_or(0);
    if first.price_scaled == min_price && first.quantity > avg_qty * 2.0 {
        let later_buys: f64 = trades[1..].iter().filter(|t| t.side.to_lowercase() == "buy").map(|t| t.quantity).sum();
        let later_sells: f64 = trades[1..].iter().filter(|t| t.side.to_lowercase() == "sell").map(|t| t.quantity).sum();
        if later_buys > later_sells {
            return Ok(SweepSignal { detected: true, direction: "sweep_low".into(), sweep_price: first.price_scaled, volume_spike_ratio: first.quantity / avg_qty, confidence: ((first.quantity / avg_qty) / 5.0).min(1.0) });
        }
    }
    if last.price_scaled == max_price && last.quantity > avg_qty * 2.0 {
        let earlier_sells: f64 = trades[..trades.len()-1].iter().filter(|t| t.side.to_lowercase() == "sell").map(|t| t.quantity).sum();
        let earlier_buys: f64 = trades[..trades.len()-1].iter().filter(|t| t.side.to_lowercase() == "buy").map(|t| t.quantity).sum();
        if earlier_sells > earlier_buys {
            return Ok(SweepSignal { detected: true, direction: "sweep_high".into(), sweep_price: last.price_scaled, volume_spike_ratio: last.quantity / avg_qty, confidence: ((last.quantity / avg_qty) / 5.0).min(1.0) });
        }
    }
    Ok(SweepSignal { detected: false, direction: "none".into(), sweep_price: 0, volume_spike_ratio: 0.0, confidence: 0.0 })
}

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct DisplacementSignal {
    pub detected: bool,
    pub direction: String,
    pub acceleration: f64,
    pub confidence: f64,
}

pub fn detect_displacement(trades: &[TradeRecord]) -> Result<DisplacementSignal, EngineError> {
    if trades.len() < 4 {
        return Err(EngineError::InvalidData("need >= 4 trades for displacement".into()));
    }
    let prices: Vec<f64> = trades.iter().map(|t| t.price_scaled as f64).collect();
    let n = prices.len();
    let mut velocities = Vec::with_capacity(n - 1);
    for i in 1..n { velocities.push(prices[i] - prices[i - 1]); }
    let mut accelerations = Vec::with_capacity(velocities.len().saturating_sub(1));
    for i in 1..velocities.len() { accelerations.push(velocities[i] - velocities[i - 1]); }
    if accelerations.is_empty() {
        return Ok(DisplacementSignal { detected: false, direction: "none".into(), acceleration: 0.0, confidence: 0.0 });
    }
    let max_accel = accelerations.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
    let min_accel = accelerations.iter().cloned().fold(f64::INFINITY, f64::min);
    let first_price = prices.first().copied().unwrap_or(1.0);
    if first_price <= 0.0 {
        return Err(EngineError::InvalidData("first price must be positive".into()));
    }
    let threshold = first_price * 0.001;
    if max_accel > threshold {
        Ok(DisplacementSignal { detected: true, direction: "up".into(), acceleration: max_accel, confidence: (max_accel / (threshold * 5.0)).min(1.0) })
    } else if min_accel < -threshold {
        Ok(DisplacementSignal { detected: true, direction: "down".into(), acceleration: min_accel, confidence: (min_accel.abs() / (threshold * 5.0)).min(1.0) })
    } else {
        Ok(DisplacementSignal { detected: false, direction: "none".into(), acceleration: 0.0, confidence: 0.0 })
    }
}

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct VolumeProfileSignal {
    pub poc_price: i64,
    pub poc_volume: f64,
    pub value_area_high: i64,
    pub value_area_low: i64,
    pub current_vs_poc: String,
    pub confidence: f64,
}

pub fn compute_volume_profile(trades: &[TradeRecord], current_price: i64) -> Result<VolumeProfileSignal, EngineError> {
    if trades.is_empty() {
        return Err(EngineError::InvalidData("no trades for volume profile".into()));
    }
    let mut vol_map: HashMap<i64, f64> = HashMap::new();
    let mut total_vol = 0.0_f64;
    for t in trades {
        *vol_map.entry(t.price_scaled).or_insert(0.0) += t.quantity;
        total_vol += t.quantity;
    }
    if total_vol <= 0.0 {
        return Err(EngineError::InvalidData("zero total volume".into()));
    }
    let poc = vol_map.iter()
        .max_by(|a, b| a.1.partial_cmp(b.1).unwrap_or(std::cmp::Ordering::Equal))
        .map(|(p, v)| (*p, *v)).unwrap_or((0, 0.0));
    let mut sorted_levels: Vec<(i64, f64)> = vol_map.into_iter().collect();
    sorted_levels.sort_by_key(|(p, _)| *p);
    let target_vol = total_vol * 0.70;
    let mut accumulated = poc.1;
    let mut va_low = poc.0;
    let mut va_high = poc.0;
    let low_idx_init = sorted_levels.iter().position(|(p, _)| *p == poc.0).unwrap_or(0);
    let mut low_idx = low_idx_init;
    let mut high_idx = low_idx_init;
    while accumulated < target_vol {
        let can_go_low = low_idx > 0;
        let can_go_high = high_idx < sorted_levels.len() - 1;
        if !can_go_low && !can_go_high { break; }
        let low_vol = if can_go_low { sorted_levels[low_idx - 1].1 } else { 0.0 };
        let high_vol = if can_go_high { sorted_levels[high_idx + 1].1 } else { 0.0 };
        if low_vol >= high_vol && can_go_low {
            low_idx -= 1; va_low = sorted_levels[low_idx].0; accumulated += low_vol;
        } else if can_go_high {
            high_idx += 1; va_high = sorted_levels[high_idx].0; accumulated += high_vol;
        } else if can_go_low {
            low_idx -= 1; va_low = sorted_levels[low_idx].0; accumulated += low_vol;
        }
    }
    let vs_poc = if current_price > poc.0 + 100 { "above" } else if current_price < poc.0 - 100 { "below" } else { "at" };
    Ok(VolumeProfileSignal {
        poc_price: poc.0, poc_volume: poc.1, value_area_high: va_high, value_area_low: va_low,
        current_vs_poc: vs_poc.into(), confidence: (poc.1 / total_vol).min(1.0),
    })
}

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct SlippageSignal {
    pub estimated_slippage_bps: i32,
    pub depth_at_1pct: f64,
    pub impact_per_unit: f64,
    pub confidence: f64,
}

pub fn estimate_slippage(bids: &[OrderbookLevel], asks: &[OrderbookLevel], order_size: f64) -> Result<SlippageSignal, EngineError> {
    if bids.is_empty() || asks.is_empty() {
        return Err(EngineError::EmptyOrderbook("need orderbook for slippage".into()));
    }
    if order_size <= 0.0 {
        return Err(EngineError::InvalidData("order size must be positive".into()));
    }
    let best_ask = asks.first().ok_or_else(|| EngineError::EmptyOrderbook("no asks".into()))?.price_scaled as f64;
    let best_bid = bids.first().ok_or_else(|| EngineError::EmptyOrderbook("no bids".into()))?.price_scaled as f64;
    let mid = (best_ask + best_bid) / 2.0;
    if mid <= 0.0 {
        return Err(EngineError::InvalidData("mid price must be positive".into()));
    }
    let mut remaining = order_size;
    let mut total_cost = 0.0_f64;
    for level in asks {
        if remaining <= 0.0 { break; }
        let fill = remaining.min(level.quantity);
        total_cost += fill * level.price_scaled as f64;
        remaining -= fill;
    }
    let filled_qty = order_size - remaining;
    if filled_qty <= 0.0 {
        return Err(EngineError::InvalidData("insufficient depth to fill order".into()));
    }
    let avg_fill_price = total_cost / filled_qty;
    let slippage_bps = (((avg_fill_price - best_ask) / mid) * 10_000.0).round() as i32;
    let threshold = mid * 0.01;
    let depth_1pct: f64 = asks.iter().filter(|l| (l.price_scaled as f64) <= best_ask + threshold).map(|l| l.quantity).sum();
    Ok(SlippageSignal {
        estimated_slippage_bps: slippage_bps.max(0), depth_at_1pct: depth_1pct,
        impact_per_unit: slippage_bps as f64 / order_size,
        confidence: if depth_1pct > order_size * 2.0 { 0.9 } else { 0.5 },
    })
}
