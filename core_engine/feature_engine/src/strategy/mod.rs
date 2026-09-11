// MODULE: atlas-feature-engine::strategy
// GOVERNANCE: Matrix A - Rust Compute Layer
// CONTRACT: Config-driven composition engine for strategy signals.
// P21: Multi-Strategy + Primitives + Composer.
// No parallel strategy paths.
// WARNING: No unwrap/expect/panic on request path. All errors via Result.
pub mod primitives;

use std::collections::HashMap;
use crate::models::MarketSnapshot;
use crate::EngineError;

use std::collections::HashMap as StdMap;
use std::sync::{Arc, RwLock};
use primitives::SnapshotRing;

/// Thread-safe per-symbol history for temporal primitives.
#[derive(Clone)]
pub struct SymbolHistory {
    rings: Arc<RwLock<StdMap<String, SnapshotRing>>>,
    default_capacity: usize,
}

impl SymbolHistory {
    pub fn new(default_capacity: usize) -> Self {
        Self {
            rings: Arc::new(RwLock::new(StdMap::new())),
            default_capacity: default_capacity.clamp(1, 10_000),
        }
    }

    /// Push a snapshot for a symbol. Creates ring if first time.
    pub fn push(&self, snap: &MarketSnapshot) {
        let mut map = self.rings.write().unwrap_or_else(|e| e.into_inner());
        let ring = map.entry(snap.symbol.clone())
            .or_insert_with(|| SnapshotRing::new(self.default_capacity));
        ring.push(snap.clone());
    }

    /// Get last N snapshots for a symbol (excluding current).
    pub fn get_history(&self, symbol: &str, n: usize) -> Vec<crate::models::MarketSnapshot> {
        let map = self.rings.read().unwrap_or_else(|e| e.into_inner());
        match map.get(symbol) {
            Some(ring) => ring.last_n(n + 1).into_iter().skip(1).cloned().collect(),
            None => Vec::new(),
        }
    }

    pub fn symbol_count(&self) -> usize {
        let map = self.rings.read().unwrap_or_else(|e| e.into_inner());
        map.len()
    }
}

impl Default for SymbolHistory {
    fn default() -> Self { Self::new(100) }
}

impl std::fmt::Debug for SymbolHistory {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let count = self.symbol_count();
        f.debug_struct("SymbolHistory")
            .field("symbols", &count)
            .field("capacity", &self.default_capacity)
            .finish()
    }
}


#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
pub enum Direction { Buy, Sell, Neutral }

impl Direction {
    pub fn as_str(&self) -> &str {
        match self { Direction::Buy => "BUY", Direction::Sell => "SELL", Direction::Neutral => "NEUTRAL" }
    }
}

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct PrimitiveWeight { pub name: String, pub weight: f64 }
impl PrimitiveWeight {
    pub fn new(name: &str, weight: f64) -> Self { Self { name: name.to_string(), weight } }
}

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct StrategyConfig {
    pub id: String, pub description: String,
    pub primitives: Vec<PrimitiveWeight>,
    pub thresholds: HashMap<String, f64>,
    pub degrade_best_effort: bool,
    pub lookback: usize,
}
impl StrategyConfig {
    pub fn new(id: &str, desc: &str, prims: Vec<PrimitiveWeight>) -> Self {
        let mut t = HashMap::new(); t.insert("min_confidence".into(), 0.20);
        Self { id: id.into(), description: desc.into(), primitives: prims, thresholds: t, degrade_best_effort: true, lookback: 10 }
    }
    pub fn min_confidence(&self) -> f64 { self.thresholds.get("min_confidence").copied().unwrap_or(0.20) }
}

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct PrimitiveResult {
    pub primitive: String, pub direction: Direction,
    pub confidence: f64, pub weight: f64, pub contribution: f64,
    pub attributes: HashMap<String, String>, pub error: Option<String>,
}
impl PrimitiveResult {
    fn ok(n: &str, d: Direction, c: f64, a: HashMap<String, String>) -> Self {
        Self { primitive: n.into(), direction: d, confidence: c.clamp(0.0,1.0), weight: 0.0, contribution: 0.0, attributes: a, error: None }
    }
    fn failed(n: &str, e: &EngineError) -> Self {
        Self { primitive: n.into(), direction: Direction::Neutral, confidence: 0.0, weight: 0.0, contribution: 0.0, attributes: HashMap::new(), error: Some(e.to_string()) }
    }
}

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct StrategySignal {
    pub strategy_id: String, pub symbol: String, pub direction: Direction,
    pub confidence: f64, pub attributes: HashMap<String, String>,
    pub causal_trace: Vec<PrimitiveResult>, pub timestamp_ns: u64,
}

pub trait Strategy: Send + Sync {
    fn id(&self) -> &str;
    fn description(&self) -> &str;
    fn compute(&self, snap: &MarketSnapshot) -> Result<StrategySignal, EngineError>;
}

#[derive(Debug, Clone)]
pub struct CompositionStrategy { config: StrategyConfig, history: SymbolHistory }
impl CompositionStrategy {
    pub fn new(c: StrategyConfig) -> Self { Self { config: c, history: SymbolHistory::default() } }
    pub fn with_history(c: StrategyConfig, h: SymbolHistory) -> Self { Self { config: c, history: h } }
}

impl Strategy for CompositionStrategy {
    fn id(&self) -> &str { &self.config.id }
    fn description(&self) -> &str { &self.config.description }
    fn compute(&self, snap: &MarketSnapshot) -> Result<StrategySignal, EngineError> {
        // Push current snapshot to temporal memory BEFORE evaluation
        self.history.push(snap);
        let lookback = self.config.lookback;
        let hist_owned = self.history.get_history(&snap.symbol, lookback);
        let hist_refs: Vec<&crate::models::MarketSnapshot> = hist_owned.iter().collect();
        let mut trace = Vec::with_capacity(self.config.primitives.len());
        let (mut bs, mut ss, mut aw, mut fc) = (0.0_f64, 0.0_f64, 0.0_f64, 0_usize);
        for pw in &self.config.primitives {
            let w = pw.weight.max(0.0);
            match eval_primitive(&pw.name, snap, &hist_refs) {
                Ok(mut r) => { r.weight = w; r.contribution = r.confidence * w;
                    match r.direction { Direction::Buy => bs += r.contribution, Direction::Sell => ss += r.contribution, Direction::Neutral => {} }
                    aw += w; trace.push(r);
                }
                Err(e) => { fc += 1; if !self.config.degrade_best_effort { return Err(e); }
                    let mut f = PrimitiveResult::failed(&pw.name, &e); f.weight = w; trace.push(f);
                }
            }
        }
        let (mut dir, mut conf) = if aw <= 0.0 { (Direction::Neutral, 0.0) } else {
            let b = bs/aw; let s = ss/aw;
            if b > s { (Direction::Buy, b.clamp(0.0,1.0)) } else if s > b { (Direction::Sell, s.clamp(0.0,1.0)) } else { (Direction::Neutral, 0.0) }
        };
        if conf < self.config.min_confidence() { dir = Direction::Neutral; conf = 0.0; }
        let mut attrs = HashMap::new();
        attrs.insert("fusion".into(), "weighted_average".into());
        attrs.insert("primitive_count".into(), self.config.primitives.len().to_string());
        attrs.insert("failed_count".into(), fc.to_string());
        attrs.insert("active_weight".into(), format!("{:.4}", aw));
        Ok(StrategySignal { strategy_id: self.config.id.clone(), symbol: snap.symbol.clone(), direction: dir, confidence: conf, attributes: attrs, causal_trace: trace, timestamp_ns: snap.timestamp_ns })
    }
}

#[derive(Clone)]
pub struct StrategyRegistry { strategies: Vec<CompositionStrategy> }
impl Default for StrategyRegistry { fn default() -> Self { Self::new() } }
impl StrategyRegistry {
    pub fn new() -> Self { Self { strategies: default_configs().into_iter().map(CompositionStrategy::new).collect() } }
    pub fn from_configs(c: Vec<StrategyConfig>) -> Self { Self { strategies: c.into_iter().map(CompositionStrategy::new).collect() } }
    pub fn register_config(&mut self, c: StrategyConfig) { self.strategies.push(CompositionStrategy::new(c)); }
    pub fn compute_all(&self, s: &MarketSnapshot) -> Vec<StrategySignal> { self.strategies.iter().filter_map(|st| st.compute(s).ok()).collect() }
    pub fn compute_by_id(&self, id: &str, s: &MarketSnapshot) -> Result<StrategySignal, EngineError> {
        self.strategies.iter().find(|st| st.id() == id).ok_or_else(|| EngineError::InvalidData(format!("unknown strategy: {}", id)))?.compute(s)
    }
    pub fn compute_selected(&self, ids: &[&str], s: &MarketSnapshot) -> Vec<StrategySignal> {
        self.strategies.iter().filter(|st| ids.contains(&st.id())).filter_map(|st| st.compute(s).ok()).collect()
    }
    pub fn list_ids(&self) -> Vec<String> { self.strategies.iter().map(|s| s.id().to_string()).collect() }
    pub fn len(&self) -> usize { self.strategies.len() }
    pub fn is_empty(&self) -> bool { self.strategies.is_empty() }
}

pub fn default_configs() -> Vec<StrategyConfig> {
    vec![
        StrategyConfig::new("vwap","VWAP baseline",vec![PrimitiveWeight::new("vwap",1.0)]),
        StrategyConfig::new("mean_reversion","Z-score reversion",vec![PrimitiveWeight::new("mean_reversion",1.0)]),
        StrategyConfig::new("momentum","ROC momentum",vec![PrimitiveWeight::new("momentum",1.0)]),
        StrategyConfig::new("smart_money","OBI+Sweep+Iceberg",vec![PrimitiveWeight::new("obi",0.35),PrimitiveWeight::new("liquidity_sweep",0.35),PrimitiveWeight::new("iceberg",0.30)]),
        StrategyConfig::new("ict","FVG+Displacement+Sweep",vec![PrimitiveWeight::new("fvg",0.40),PrimitiveWeight::new("displacement",0.30),PrimitiveWeight::new("liquidity_sweep",0.30)]),
        StrategyConfig::new("iceberg_hunter","Pure iceberg",vec![PrimitiveWeight::new("iceberg",1.0)]),
        StrategyConfig::new("volume_trading","VWAP+VolumeProfile",vec![PrimitiveWeight::new("vwap",0.50),PrimitiveWeight::new("volume_profile",0.50)]),
        StrategyConfig::new("slippage_aware","VWAP gated by slippage",vec![PrimitiveWeight::new("vwap",0.70),PrimitiveWeight::new("slippage",0.30)]),
    ]
}

fn latest_price(s: &MarketSnapshot) -> Result<i64, EngineError> { s.trades.last().map(|t| t.price_scaled).ok_or_else(|| EngineError::InvalidData("no trades".into())) }
fn dir_up(v: &str) -> Direction { match v { "BUY" => Direction::Buy, "SELL" => Direction::Sell, _ => Direction::Neutral } }

fn eval_primitive(name: &str, snap: &MarketSnapshot, history: &[&crate::models::MarketSnapshot]) -> Result<PrimitiveResult, EngineError> {
    match name {
        "obi" => { let v = crate::obi::compute_obi(&snap.bids,&snap.asks,5); let d = if v>0.1{Direction::Buy}else if v < -0.1{Direction::Sell}else{Direction::Neutral}; let mut a=HashMap::new(); a.insert("obi".into(),format!("{:.6}",v)); Ok(PrimitiveResult::ok("obi",d,v.abs().min(1.0),a)) }
        "vwap" => { let p=latest_price(snap)?; let s=crate::vwap::generate_vwap_signal(&snap.symbol,&snap.trades,p,snap.timestamp_ns)?; let mut a=HashMap::new(); a.insert("dev_bps".into(),s.deviation_bps.to_string()); a.insert("obv".into(),format!("{:.6}",s.obv)); Ok(PrimitiveResult::ok("vwap",dir_up(&s.direction),s.confidence,a)) }
        "mean_reversion" => { if snap.trades.len()<3{return Err(EngineError::InvalidData("need>=3".into()))} let ps:Vec<f64>=snap.trades.iter().map(|t|t.price_scaled as f64).collect(); let n=ps.len()as f64; let m: f64=ps.iter().sum::<f64>()/n; let var: f64=ps.iter().map(|p|(p-m).powi(2)).sum::<f64>()/n; let sd=var.sqrt(); if sd<=0.0{return Err(EngineError::InvalidData("zero var".into()))} let c=ps.last().copied().ok_or(EngineError::InvalidData("empty ps".into()))?; let z=(c-m)/sd; let d=if z < -1.5{Direction::Buy}else if z>1.5{Direction::Sell}else{Direction::Neutral}; let mut a=HashMap::new(); a.insert("z".into(),format!("{:.6}",z)); Ok(PrimitiveResult::ok("mean_reversion",d,(z.abs()/3.0).min(1.0),a)) }
        "momentum" => { if snap.trades.len()<2{return Err(EngineError::InvalidData("need>=2".into()))} let f=snap.trades.first().ok_or(EngineError::InvalidData("no first".into()))?.price_scaled as f64; let l=snap.trades.last().ok_or(EngineError::InvalidData("no last".into()))?.price_scaled as f64; if f<=0.0{return Err(EngineError::InvalidData("f<=0".into()))} let roc=((l-f)/f)*100.0; let d=if roc>0.3{Direction::Buy}else if roc < -0.3{Direction::Sell}else{Direction::Neutral}; let bv:f64=snap.trades.iter().filter(|t|t.side.to_lowercase()=="buy").map(|t|t.quantity).sum(); let sv:f64=snap.trades.iter().filter(|t|t.side.to_lowercase()=="sell").map(|t|t.quantity).sum(); let tv=bv+sv; let vr=if tv>0.0{(bv-sv)/tv}else{0.0}; let vc=(roc>0.0&&vr>0.0)||(roc<0.0&&vr<0.0); let conf=if vc{((roc.abs()/2.0).min(1.0)+0.15).min(1.0)}else{(roc.abs()/2.0).min(1.0)}; let mut a=HashMap::new(); a.insert("roc".into(),format!("{:.6}",roc)); Ok(PrimitiveResult::ok("momentum",d,conf,a)) }
        "iceberg" => { let s = if history.is_empty() { let mut lv=Vec::new(); lv.extend(snap.bids.iter().cloned()); lv.extend(snap.asks.iter().cloned()); primitives::detect_iceberg(&snap.trades,&lv)? } else { primitives::detect_iceberg_temporal(snap,history)? }; let d=if s.detected{match s.side.to_lowercase().as_str(){"buy"=>Direction::Buy,"sell"=>Direction::Sell,_=>Direction::Neutral}}else{Direction::Neutral}; let mut a=HashMap::new(); a.insert("detected".into(),s.detected.to_string()); a.insert("hr".into(),format!("{:.6}",s.hidden_ratio)); a.insert("duration".into(),s.duration_snapshots.to_string()); a.insert("trend".into(),s.trend.clone()); Ok(PrimitiveResult::ok("iceberg",d,s.confidence,a)) }
        "fvg" => { let s=primitives::detect_fvg(&snap.bids,&snap.asks)?; let d=match s.gap_type.as_str(){"bullish"=>Direction::Buy,"bearish"=>Direction::Sell,_=>Direction::Neutral}; let mut a=HashMap::new(); a.insert("gt".into(),s.gap_type.clone()); a.insert("bps".into(),s.gap_bps.to_string()); Ok(PrimitiveResult::ok("fvg",d,s.confidence,a)) }
        "liquidity_sweep" => { let s = if history.is_empty() { primitives::detect_liquidity_sweep(&snap.trades)? } else { primitives::detect_sweep_temporal(snap,history)? }; let d=match s.direction.as_str(){"sweep_low"=>Direction::Buy,"sweep_high"=>Direction::Sell,_=>Direction::Neutral}; let mut a=HashMap::new(); a.insert("dir".into(),s.direction.clone()); a.insert("spike".into(),format!("{:.6}",s.volume_spike_ratio)); a.insert("reversal".into(),s.reversal_confirmed.to_string()); a.insert("post_dir".into(),s.post_sweep_direction.clone()); Ok(PrimitiveResult::ok("liquidity_sweep",d,s.confidence,a)) }
        "displacement" => { let s = if history.is_empty() { primitives::detect_displacement(&snap.trades)? } else { primitives::detect_displacement_temporal(snap,history)? }; let d=match s.direction.as_str(){"up"=>Direction::Buy,"down"=>Direction::Sell,_=>Direction::Neutral}; let mut a=HashMap::new(); a.insert("acc".into(),format!("{:.6}",s.acceleration)); a.insert("sustained".into(),s.sustained_bars.to_string()); Ok(PrimitiveResult::ok("displacement",d,s.confidence,a)) }
        "volume_profile" => { let s = if history.is_empty() { let p=latest_price(snap)?; primitives::compute_volume_profile(&snap.trades,p)? } else { primitives::compute_volume_profile_temporal(snap,history)? }; let d=match s.current_vs_poc.as_str(){"below"=>Direction::Buy,"above"=>Direction::Sell,_=>Direction::Neutral}; let mut a=HashMap::new(); a.insert("poc".into(),s.poc_price.to_string()); a.insert("vs".into(),s.current_vs_poc.clone()); a.insert("migration_rate".into(),format!("{:.2}",s.poc_migration_rate)); Ok(PrimitiveResult::ok("volume_profile",d,s.confidence,a)) }
        "slippage" => { let s=primitives::estimate_slippage(&snap.bids,&snap.asks,1.0)?; let d=if s.estimated_slippage_bps<=10{Direction::Buy}else if s.estimated_slippage_bps>=30{Direction::Sell}else{Direction::Neutral}; let c=if s.estimated_slippage_bps<=10{s.confidence}else if s.estimated_slippage_bps>=30{(s.estimated_slippage_bps as f64/100.0).min(1.0)}else{0.0}; let mut a=HashMap::new(); a.insert("bps".into(),s.estimated_slippage_bps.to_string()); Ok(PrimitiveResult::ok("slippage",d,c,a)) }
        o => Err(EngineError::InvalidData(format!("unknown primitive: {}",o))),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::models::{MarketSnapshot, OrderbookLevel, TradeRecord};
    fn snap() -> MarketSnapshot {
        MarketSnapshot { symbol:"BTCUSDT".into(), exchange:"binance".into(),
            bids:vec![OrderbookLevel{price_scaled:99_900,quantity:1.0},OrderbookLevel{price_scaled:99_800,quantity:2.0},OrderbookLevel{price_scaled:99_700,quantity:3.0}],
            asks:vec![OrderbookLevel{price_scaled:100_100,quantity:1.0},OrderbookLevel{price_scaled:100_200,quantity:2.0},OrderbookLevel{price_scaled:100_300,quantity:3.0}],
            trades:vec![TradeRecord{price_scaled:99_800,quantity:3.0,side:"sell".into()},TradeRecord{price_scaled:99_900,quantity:1.0,side:"buy".into()},TradeRecord{price_scaled:100_000,quantity:1.0,side:"buy".into()},TradeRecord{price_scaled:100_100,quantity:0.8,side:"buy".into()},TradeRecord{price_scaled:100_200,quantity:0.7,side:"sell".into()},TradeRecord{price_scaled:100_300,quantity:2.5,side:"buy".into()}],
            timestamp_ns:1_000_000_000, source_uri:"test://p21".into() }
    }
    #[test] fn t_8_strats() { assert_eq!(StrategyRegistry::new().len(), 8); }
    #[test] fn t_compute_all() { let s=StrategyRegistry::new().compute_all(&snap()); assert_eq!(s.len(),8); for x in &s { assert!(!x.causal_trace.is_empty()); } }
    #[test] fn t_selected() { assert_eq!(StrategyRegistry::new().compute_selected(&["smart_money","ict"],&snap()).len(), 2); }
    #[test] fn t_unknown_err() { assert!(StrategyRegistry::new().compute_by_id("nope",&snap()).is_err()); }
    #[test] fn t_custom_cfg() { let mut c={ let mut c = StrategyConfig::new("cust","test",vec![PrimitiveWeight::new("obi",0.6),PrimitiveWeight::new("vwap",0.4)]); c.lookback = 5; c }; c.thresholds.insert("min_confidence".into(),0.05); let s=StrategyRegistry::from_configs(vec![c]).compute_by_id("cust",&snap()).unwrap(); assert_eq!(s.causal_trace.len(),2); }
    #[test] fn t_degrade() { let c={ let mut c = StrategyConfig::new("d","deg",vec![PrimitiveWeight::new("obi",0.5),PrimitiveWeight::new("bad",0.5)]); c.lookback = 3; c }; let s=CompositionStrategy::new(c).compute(&snap()).unwrap(); assert_eq!(s.causal_trace.iter().filter(|r|r.error.is_some()).count(),1); }

    #[test] fn t_ring_buffer_overflow() {
        let mut ring = primitives::SnapshotRing::new(3);
        for i in 0..5 {
            ring.push(MarketSnapshot { symbol:"T".into(), exchange:"X".into(), bids:vec![], asks:vec![], trades:vec![], timestamp_ns:i, source_uri:"t".into() });
        }
        assert_eq!(ring.len(), 3);
        let h = ring.last_n(2);
        assert_eq!(h.len(), 2);
        assert_eq!(h[0].timestamp_ns, 4); // newest first
        assert_eq!(h[1].timestamp_ns, 3);
    }
    #[test] fn t_symbol_history() {
        let sh = super::SymbolHistory::new(5);
        let s = snap();
        for _ in 0..3 { sh.push(&s); }
        let h = sh.get_history("BTCUSDT", 10);
        assert_eq!(h.len(), 2); // 3 pushed, skip 1 (current) = 2
    }
    #[test] fn t_temporal_primitives_with_history() {
        let sh = super::SymbolHistory::new(10);
        let s = snap();
        for _ in 0..5 { sh.push(&s); }
        let mut cfg = StrategyConfig::new("tpm_test","temporal",vec![PrimitiveWeight::new("iceberg",0.5),PrimitiveWeight::new("liquidity_sweep",0.5)]);
        cfg.lookback = 3;
        let st = CompositionStrategy::with_history(cfg, sh);
        let sig = st.compute(&s).unwrap();
        assert_eq!(sig.causal_trace.len(), 2);
        // Check that temporal attributes are present
        for r in &sig.causal_trace {
            if r.primitive == "iceberg" { assert!(r.attributes.contains_key("duration")); }
            if r.primitive == "liquidity_sweep" { assert!(r.attributes.contains_key("reversal")); }
        }
    }
}
