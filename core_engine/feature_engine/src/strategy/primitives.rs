// MODULE: atlas-feature-engine::strategy::primitives
// GOVERNANCE: Matrix A - Rust Compute Layer
// CONTRACT: Reusable market microstructure primitives.
// No business logic here — pure math on market data.
// WARNING: No unwrap/expect/panic. All errors via Result.
use std::collections::HashMap;
use crate::models::{OrderbookLevel, TradeRecord};
use crate::EngineError;

// ============================================================
// TEMPORAL PRIMITIVE MEMORY (TPM)
// Lock-free ring buffer for bounded historical context.
// Each symbol gets one ring. Capacity is configurable.
// Memory: capacity * ~2KB per symbol.
// ============================================================
#[derive(Debug, Clone)]
pub struct SnapshotRing {
    buffer: Vec<Option<crate::models::MarketSnapshot>>,
    capacity: usize,
    head: usize,
    count: usize,
}

impl SnapshotRing {
    pub fn new(capacity: usize) -> Self {
        let cap = capacity.clamp(1, 10_000); // safety bounds
        Self {
            buffer: vec![None; cap],
            capacity: cap,
            head: 0,
            count: 0,
        }
    }

    /// Push a new snapshot. O(1). Overwrites oldest if full.
    pub fn push(&mut self, snap: crate::models::MarketSnapshot) {
        self.buffer[self.head] = Some(snap);
        self.head = (self.head + 1) % self.capacity;
        if self.count < self.capacity {
            self.count += 1;
        }
    }

    /// Return up to `n` most recent snapshots, newest first.
    pub fn last_n(&self, n: usize) -> Vec<&crate::models::MarketSnapshot> {
        let take = n.min(self.count);
        let mut result = Vec::with_capacity(take);
        for i in 0..take {
            let idx = (self.head + self.capacity - 1 - i) % self.capacity;
            if let Some(ref snap) = self.buffer[idx] {
                result.push(snap);
            }
        }
        result
    }

    pub fn len(&self) -> usize { self.count }
    pub fn is_empty(&self) -> bool { self.count == 0 }
    pub fn capacity(&self) -> usize { self.capacity }
}

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct IcebergSignal {
    pub detected: bool,
    pub side: String,
    pub price_level: i64,
    pub visible_qty: f64,
    pub executed_qty: f64,
    pub hidden_ratio: f64,
    pub confidence: f64,
    pub duration_snapshots: usize,
    pub trend: String,
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
                    duration_snapshots: 1,
                    trend: "unknown".into(),
                });
            }
        }
    }
    Ok(best_iceberg.unwrap_or(IcebergSignal {
        detected: false, side: "none".into(), price_level: 0,
        visible_qty: 0.0, executed_qty: 0.0, hidden_ratio: 0.0, confidence: 0.0, duration_snapshots: 0, trend: "none".into(),
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
    pub reversal_confirmed: bool,
    pub post_sweep_direction: String,
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
            return Ok(SweepSignal { detected: true, direction: "sweep_low".into(), sweep_price: first.price_scaled, volume_spike_ratio: first.quantity / avg_qty, confidence: ((first.quantity / avg_qty) / 5.0).min(1.0), reversal_confirmed: false, post_sweep_direction: "pending".into(), });
        }
    }
    if last.price_scaled == max_price && last.quantity > avg_qty * 2.0 {
        let earlier_sells: f64 = trades[..trades.len()-1].iter().filter(|t| t.side.to_lowercase() == "sell").map(|t| t.quantity).sum();
        let earlier_buys: f64 = trades[..trades.len()-1].iter().filter(|t| t.side.to_lowercase() == "buy").map(|t| t.quantity).sum();
        if earlier_sells > earlier_buys {
            return Ok(SweepSignal { detected: true, direction: "sweep_high".into(), sweep_price: last.price_scaled, volume_spike_ratio: last.quantity / avg_qty, confidence: ((last.quantity / avg_qty) / 5.0).min(1.0), reversal_confirmed: false, post_sweep_direction: "pending".into(), });
        }
    }
    Ok(SweepSignal { detected: false, direction: "none".into(), sweep_price: 0, volume_spike_ratio: 0.0, confidence: 0.0, reversal_confirmed: false, post_sweep_direction: "pending".into(), })
}

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct DisplacementSignal {
    pub detected: bool,
    pub direction: String,
    pub acceleration: f64,
    pub confidence: f64,
    pub sustained_bars: usize,
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
        return Ok(DisplacementSignal { detected: false, direction: "none".into(), acceleration: 0.0, confidence: 0.0, sustained_bars: 0, });
    }
    let max_accel = accelerations.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
    let min_accel = accelerations.iter().cloned().fold(f64::INFINITY, f64::min);
    let first_price = prices.first().copied().unwrap_or(1.0);
    if first_price <= 0.0 {
        return Err(EngineError::InvalidData("first price must be positive".into()));
    }
    let threshold = first_price * 0.001;
    if max_accel > threshold {
        Ok(DisplacementSignal { detected: true, direction: "up".into(), acceleration: max_accel, confidence: (max_accel / (threshold * 5.0)).min(1.0), sustained_bars: 0, })
    } else if min_accel < -threshold {
        Ok(DisplacementSignal { detected: true, direction: "down".into(), acceleration: min_accel, confidence: (min_accel.abs() / (threshold * 5.0)).min(1.0), sustained_bars: 0, })
    } else {
        Ok(DisplacementSignal { detected: false, direction: "none".into(), acceleration: 0.0, confidence: 0.0, sustained_bars: 0, })
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
    pub poc_migration_rate: f64,
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
        poc_migration_rate: 0.0,
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

// ============================================================
// TEMPORAL PRIMITIVES — use history ring buffer
// These upgrade stateless signals with temporal context.
// ============================================================

/// Temporal iceberg: detect if hidden orders persist across snapshots
pub fn detect_iceberg_temporal(
    current: &crate::models::MarketSnapshot,
    history: &[&crate::models::MarketSnapshot],
) -> Result<IcebergSignal, EngineError> {
    let mut levels = Vec::new();
    levels.extend(current.bids.iter().cloned());
    levels.extend(current.asks.iter().cloned());
    let mut base = detect_iceberg(&current.trades, &levels)?;

    if !base.detected || history.is_empty() {
        return Ok(base);
    }

    // Count how many historical snapshots also had iceberg at same price level
    let mut duration = 1_usize;
    let target_price = base.price_level;

    for snap in history {
        let mut h_levels = Vec::new();
        h_levels.extend(snap.bids.iter().cloned());
        h_levels.extend(snap.asks.iter().cloned());
        if let Ok(h_sig) = detect_iceberg(&snap.trades, &h_levels) {
            if h_sig.detected && h_sig.price_level == target_price {
                duration += 1;
            }
        }
    }

    base.duration_snapshots = duration;
    base.trend = if duration >= 5 {
        "accumulating".into()
    } else if duration >= 2 {
        "stable".into()
    } else {
        "transient".into()
    };

    // Boost confidence for persistent icebergs
    let trend_boost = match base.trend.as_str() {
        "accumulating" => 0.15,
        "stable" => 0.08,
        _ => 0.0,
    };
    base.confidence = (base.confidence + trend_boost).min(1.0);

    Ok(base)
}

/// Temporal sweep: check if reversal was confirmed after the sweep
pub fn detect_sweep_temporal(
    current: &crate::models::MarketSnapshot,
    history: &[&crate::models::MarketSnapshot],
) -> Result<SweepSignal, EngineError> {
    let mut base = detect_liquidity_sweep(&current.trades)?;

    if !base.detected || history.is_empty() {
        return Ok(base);
    }

    // Check if price reversed in the expected direction after sweep
    let current_mid = if !current.bids.is_empty() && !current.asks.is_empty() {
        (current.bids[0].price_scaled + current.asks[0].price_scaled) as f64 / 2.0
    } else {
        return Ok(base);
    };

    let mut reversals = 0_usize;
    let mut checks = 0_usize;

    for snap in history.iter().take(3) {
        if snap.bids.is_empty() || snap.asks.is_empty() { continue; }
        let hist_mid = (snap.bids[0].price_scaled + snap.asks[0].price_scaled) as f64 / 2.0;
        checks += 1;

        match base.direction.as_str() {
            "sweep_low" => {
                // After sweeping low, price should go UP
                if current_mid > hist_mid { reversals += 1; }
            }
            "sweep_high" => {
                // After sweeping high, price should go DOWN
                if current_mid < hist_mid { reversals += 1; }
            }
            _ => {}
        }
    }

    if checks > 0 && reversals * 2 > checks {
        base.reversal_confirmed = true;
        base.post_sweep_direction = match base.direction.as_str() {
            "sweep_low" => "up".into(),
            "sweep_high" => "down".into(),
            _ => "unknown".into(),
        };
        base.confidence = (base.confidence + 0.20).min(1.0);
    } else {
        base.reversal_confirmed = false;
        base.post_sweep_direction = "unconfirmed".into();
    }

    Ok(base)
}

/// Temporal displacement: check if acceleration is sustained
pub fn detect_displacement_temporal(
    current: &crate::models::MarketSnapshot,
    history: &[&crate::models::MarketSnapshot],
) -> Result<DisplacementSignal, EngineError> {
    let mut base = detect_displacement(&current.trades)?;

    if !base.detected || history.is_empty() {
        return Ok(base);
    }

    // Count how many recent snapshots had displacement in same direction
    let mut sustained = 1_usize;
    for snap in history.iter().take(5) {
        if let Ok(h_sig) = detect_displacement(&snap.trades) {
            if h_sig.detected && h_sig.direction == base.direction {
                sustained += 1;
            }
        }
    }

    base.sustained_bars = sustained;
    // Sustained displacement = higher confidence
    let sustain_boost = ((sustained as f64 - 1.0) * 0.05).min(0.25);
    base.confidence = (base.confidence + sustain_boost).min(1.0);

    Ok(base)
}

/// Temporal volume profile: track POC migration over time
pub fn compute_volume_profile_temporal(
    current: &crate::models::MarketSnapshot,
    history: &[&crate::models::MarketSnapshot],
) -> Result<VolumeProfileSignal, EngineError> {
    let current_price = current.trades.last()
        .map(|t| t.price_scaled)
        .ok_or_else(|| EngineError::InvalidData("no trades".into()))?;
    let mut base = compute_volume_profile(&current.trades, current_price)?;

    if history.is_empty() {
        return Ok(base);
    }

    // Track POC price changes across history
    let mut poc_prices = vec![base.poc_price];
    for snap in history.iter().take(10) {
        if let Some(last_t) = snap.trades.last() {
            if let Ok(h_prof) = compute_volume_profile(&snap.trades, last_t.price_scaled) {
                poc_prices.push(h_prof.poc_price);
            }
        }
    }

    // Calculate migration rate: average POC change per snapshot
    if poc_prices.len() >= 2 {
        let total_migration: i64 = poc_prices.windows(2)
            .map(|w| (w[0] - w[1]).abs())
            .sum();
        let steps = (poc_prices.len() - 1) as f64;
        base.poc_migration_rate = total_migration as f64 / steps;
    }

    Ok(base)
}
