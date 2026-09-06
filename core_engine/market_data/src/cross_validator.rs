//! ╔═══════════════════════════════════════════════════════════╗
//! ║ MODULE: atlas-market-data / cross_validator              ║
//! ║ OWNER: core_engine/market_data (Rust)                    ║
//! ║ POLICY: governance/policies/rust-policy.yaml             ║
//! ║ ADR: docs/decisions/006-websocket-ingestion-architecture ║
//! ╠═══════════════════════════════════════════════════════════╣
//! ║ ⛔  NO FLOATS. NO PANIC. NO UNSAFE. NO UNWRAP.           ║
//! ║ Cross-exchange price validation using scaled integers.   ║
//! ╚═══════════════════════════════════════════════════════════╝

use std::collections::VecDeque;
use thiserror::Error;

/// Maximum age of a price sample before it is considered stale.
const MAX_SAMPLE_AGE_NS: u64 = 5_000_000_000; // 5 seconds

/// Maximum number of samples retained per exchange per symbol.
const MAX_SAMPLES_PER_EXCHANGE: usize = 100;

/// Deviation threshold in basis points (1 bps = 0.01%).
/// Prices deviating more than this from median are flagged.
const DEFAULT_DEVIATION_THRESHOLD_BPS: u64 = 50; // 0.5%

/// Minimum number of exchanges required for cross-validation.
const MIN_SOURCES: usize = 2;

/// Errors from cross-validation operations.
#[derive(Debug, Clone, PartialEq, Eq, Error)]
pub enum CrossValidationError {
    #[error("insufficient sources: need at least {min}, got {got}")]
    InsufficientSources { min: usize, got: usize },
    #[error("stale data: all samples older than {max_age_ns}ns")]
    StaleData { max_age_ns: u64 },
    #[error("empty symbol rejected")]
    EmptySymbol,
}

/// A single price observation from one exchange.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PriceSample {
    /// Exchange identifier (e.g., "bybit", "aster")
    pub exchange_id: String,
    /// Price in smallest currency unit (scaled integer)
    pub price_scaled: u64,
    /// Nanoseconds since UNIX epoch
    pub timestamp_ns: u64,
}

/// Result of cross-validation for a single symbol.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ValidationResult {
    /// The trading symbol
    pub symbol: String,
    /// Median price across all valid sources (scaled)
    pub median_price_scaled: u64,
    /// Number of valid sources used
    pub source_count: usize,
    /// Spread between highest and lowest price (scaled)
    pub spread_scaled: u64,
    /// Spread in basis points
    pub spread_bps: u64,
    /// Exchanges that deviated beyond threshold
    pub anomalous_exchanges: Vec<String>,
    /// Whether the result is actionable (enough sources, not stale)
    pub is_valid: bool,
}

/// Signal emitted when an arbitrage opportunity is detected.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SpreadSignal {
    pub symbol: String,
    pub buy_exchange: String,
    pub sell_exchange: String,
    pub buy_price_scaled: u64,
    pub sell_price_scaled: u64,
    pub spread_bps: u64,
    pub timestamp_ns: u64,
}

/// Per-symbol, per-exchange sliding window of price samples.
#[derive(Debug, Clone)]
struct SymbolWindow {
    samples: VecDeque<PriceSample>,
}

impl SymbolWindow {
    fn new() -> Self {
        Self {
            samples: VecDeque::with_capacity(MAX_SAMPLES_PER_EXCHANGE),
        }
    }

    fn insert(&mut self, sample: PriceSample) {
        if self.samples.len() >= MAX_SAMPLES_PER_EXCHANGE {
            self.samples.pop_front();
        }
        self.samples.push_back(sample);
    }

    fn latest_valid(&self, now_ns: u64) -> Option<&PriceSample> {
        self.samples
            .iter()
            .rev()
            .find(|s| now_ns.saturating_sub(s.timestamp_ns) <= MAX_SAMPLE_AGE_NS)
    }
}

/// Cross-validator maintains sliding windows of prices per symbol per exchange
/// and computes median-based consensus with deviation detection.
#[derive(Debug, Clone)]
pub struct CrossValidator {
    /// symbol -> (exchange_id -> window)
    windows: std::collections::HashMap<String, std::collections::HashMap<String, SymbolWindow>>,
    /// Deviation threshold in basis points
    deviation_threshold_bps: u64,
}

impl CrossValidator {
    /// Create a new CrossValidator with default thresholds.
    pub fn new() -> Self {
        Self {
            windows: std::collections::HashMap::new(),
            deviation_threshold_bps: DEFAULT_DEVIATION_THRESHOLD_BPS,
        }
    }

    /// Create with custom deviation threshold.
    pub fn with_threshold(deviation_threshold_bps: u64) -> Self {
        Self {
            windows: std::collections::HashMap::new(),
            deviation_threshold_bps,
        }
    }

    /// Insert a price sample from an exchange.
    pub fn insert_sample(&mut self, symbol: &str, sample: PriceSample) {
        let sym_windows = self
            .windows
            .entry(symbol.to_string())
            .or_insert_with(std::collections::HashMap::new);
        let window = sym_windows
            .entry(sample.exchange_id.clone())
            .or_insert_with(SymbolWindow::new);
        window.insert(sample);
    }

    /// Validate prices for a symbol across all known exchanges.
    /// Returns error if insufficient sources or all data is stale.
    pub fn validate(
        &self,
        symbol: &str,
        now_ns: u64,
    ) -> Result<ValidationResult, CrossValidationError> {
        if symbol.is_empty() {
            return Err(CrossValidationError::EmptySymbol);
        }

        let sym_windows = match self.windows.get(symbol) {
            Some(w) => w,
            None => {
                return Err(CrossValidationError::InsufficientSources {
                    min: MIN_SOURCES,
                    got: 0,
                });
            }
        };

        // Collect latest valid price from each exchange
        let mut valid_prices: Vec<(String, u64)> = Vec::new();
        for (exchange_id, window) in sym_windows {
            if let Some(sample) = window.latest_valid(now_ns) {
                valid_prices.push((exchange_id.clone(), sample.price_scaled));
            }
        }

        if valid_prices.len() < MIN_SOURCES {
            return Err(CrossValidationError::InsufficientSources {
                min: MIN_SOURCES,
                got: valid_prices.len(),
            });
        }

        // Sort by price for median calculation
        valid_prices.sort_by_key(|&(_, p)| p);

        let count = valid_prices.len();
        let median_price = if count % 2 == 0 {
            let mid = count / 2;
            // Integer average — no floats
            (valid_prices[mid - 1].1 + valid_prices[mid].1) / 2
        } else {
            valid_prices[count / 2].1
        };

        let min_price = valid_prices[0].1;
        let max_price = valid_prices[count - 1].1;
        let spread_scaled = max_price.saturating_sub(min_price);

        // Calculate spread in basis points using integer arithmetic
        // bps = (spread * 10000) / median
        let spread_bps = if median_price > 0 {
            spread_scaled
                .saturating_mul(10_000)
                .checked_div(median_price)
                .unwrap_or(0)
        } else {
            0
        };

        // Detect anomalous exchanges
        let mut anomalous = Vec::new();
        for (exchange_id, price) in &valid_prices {
            let deviation = if *price > median_price {
                price.saturating_sub(median_price)
            } else {
                median_price.saturating_sub(*price)
            };
            // deviation_bps = (deviation * 10000) / median
            let deviation_bps = if median_price > 0 {
                deviation
                    .saturating_mul(10_000)
                    .checked_div(median_price)
                    .unwrap_or(0)
            } else {
                0
            };
            if deviation_bps > self.deviation_threshold_bps {
                anomalous.push(exchange_id.clone());
            }
        }

        Ok(ValidationResult {
            symbol: symbol.to_string(),
            median_price_scaled: median_price,
            source_count: count,
            spread_scaled,
            spread_bps,
            anomalous_exchanges: anomalous,
            is_valid: true,
        })
    }

    /// Detect arbitrage opportunities for a symbol.
    /// Returns signals where spread exceeds threshold.
    pub fn detect_arbitrage(
        &self,
        symbol: &str,
        now_ns: u64,
    ) -> Result<Vec<SpreadSignal>, CrossValidationError> {
        let result = self.validate(symbol, now_ns)?;
        let mut signals = Vec::new();

        if result.spread_bps <= self.deviation_threshold_bps {
            return Ok(signals);
        }

        let sym_windows = match self.windows.get(symbol) {
            Some(w) => w,
            None => return Ok(signals),
        };

        // Find min and max price exchanges
        let mut min_exchange = String::new();
        let mut min_price = u64::MAX;
        let mut max_exchange = String::new();
        let mut max_price = u64::MIN;

        for (exchange_id, window) in sym_windows {
            if let Some(sample) = window.latest_valid(now_ns) {
                if sample.price_scaled < min_price {
                    min_price = sample.price_scaled;
                    min_exchange = exchange_id.clone();
                }
                if sample.price_scaled > max_price {
                    max_price = sample.price_scaled;
                    max_exchange = exchange_id.clone();
                }
            }
        }

        if min_exchange != max_exchange && min_price < max_price {
            signals.push(SpreadSignal {
                symbol: symbol.to_string(),
                buy_exchange: min_exchange,
                sell_exchange: max_exchange,
                buy_price_scaled: min_price,
                sell_price_scaled: max_price,
                spread_bps: result.spread_bps,
                timestamp_ns: now_ns,
            });
        }

        Ok(signals)
    }
}

impl Default for CrossValidator {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
#[cfg_attr(test, allow(clippy::panic))]
mod tests {
    use super::*;

    fn make_sample(exchange: &str, price: u64, ts_ns: u64) -> PriceSample {
        PriceSample {
            exchange_id: exchange.to_string(),
            price_scaled: price,
            timestamp_ns: ts_ns,
        }
    }

    #[test]
    fn test_insufficient_sources_rejected() {
        let mut cv = CrossValidator::new();
        let now = 1_000_000_000_000;
        cv.insert_sample("BTCUSDT", make_sample("bybit", 65_000_000_000, now));
        let err = cv.validate("BTCUSDT", now).unwrap_err();
        assert!(matches!(
            err,
            CrossValidationError::InsufficientSources { min: 2, got: 1 }
        ));
    }

    #[test]
    fn test_two_sources_valid_median() {
        let mut cv = CrossValidator::new();
        let now = 1_000_000_000_000;
        cv.insert_sample("BTCUSDT", make_sample("bybit", 65_000_000_000, now));
        cv.insert_sample("BTCUSDT", make_sample("okx", 65_010_000_000, now));
        let result = cv.validate("BTCUSDT", now).expect("should validate");
        assert_eq!(result.source_count, 2);
        // Median of [65_000_000_000, 65_010_000_000] = 65_005_000_000
        assert_eq!(result.median_price_scaled, 65_005_000_000);
        assert_eq!(result.spread_scaled, 10_000_000);
        assert!(result.is_valid);
    }

    #[test]
    fn test_four_sources_median_calculation() {
        let mut cv = CrossValidator::new();
        let now = 1_000_000_000_000;
        cv.insert_sample("BTCUSDT", make_sample("bybit", 65_000_000_000, now));
        cv.insert_sample("BTCUSDT", make_sample("okx", 65_010_000_000, now));
        cv.insert_sample("BTCUSDT", make_sample("aster", 65_005_000_000, now));
        cv.insert_sample("BTCUSDT", make_sample("hyperliquid", 65_008_000_000, now));
        let result = cv.validate("BTCUSDT", now).expect("should validate");
        assert_eq!(result.source_count, 4);
        // Sorted: [65_000, 65_005, 65_008, 65_010] → median = (65_005 + 65_008) / 2 = 65_006_500_000
        assert_eq!(result.median_price_scaled, 65_006_500_000);
    }

    #[test]
    fn test_stale_data_rejected() {
        let mut cv = CrossValidator::new();
        let old_ts = 1_000_000_000_000;
        let now = old_ts + MAX_SAMPLE_AGE_NS + 1; // just past stale threshold
        cv.insert_sample("BTCUSDT", make_sample("bybit", 65_000_000_000, old_ts));
        cv.insert_sample("BTCUSDT", make_sample("okx", 65_010_000_000, old_ts));
        let err = cv.validate("BTCUSDT", now).unwrap_err();
        assert!(matches!(err, CrossValidationError::InsufficientSources { .. }));
    }

    #[test]
    fn test_anomalous_exchange_detected() {
        let mut cv = CrossValidator::new();
        let now = 1_000_000_000_000;
        // 3 exchanges close together
        cv.insert_sample("BTCUSDT", make_sample("bybit", 65_000_000_000, now));
        cv.insert_sample("BTCUSDT", make_sample("okx", 65_001_000_000, now));
        cv.insert_sample("BTCUSDT", make_sample("aster", 65_002_000_000, now));
        // 1 exchange way off (>0.5% deviation)
        cv.insert_sample(
            "BTCUSDT",
            make_sample("hyperliquid", 65_500_000_000, now),
        );
        let result = cv.validate("BTCUSDT", now).expect("should validate");
        assert!(result.anomalous_exchanges.contains(&"hyperliquid".to_string()));
    }

    #[test]
    fn test_arbitrage_signal_generated() {
        let mut cv = CrossValidator::new();
        let now = 1_000_000_000_000;
        // Large spread: ~1.5%
        cv.insert_sample("ETHUSDT", make_sample("aster", 3_000_000_000, now));
        cv.insert_sample("ETHUSDT", make_sample("hyperliquid", 3_045_000_000, now));
        let signals = cv.detect_arbitrage("ETHUSDT", now).expect("should detect");
        assert_eq!(signals.len(), 1);
        assert_eq!(signals[0].buy_exchange, "aster");
        assert_eq!(signals[0].sell_exchange, "hyperliquid");
        assert!(signals[0].spread_bps > 50); // > 0.5%
    }

    #[test]
    fn test_no_signal_when_spread_within_threshold() {
        let mut cv = CrossValidator::new();
        let now = 1_000_000_000_000;
        // Small spread: ~0.015%
        cv.insert_sample("BTCUSDT", make_sample("bybit", 65_000_000_000, now));
        cv.insert_sample("BTCUSDT", make_sample("okx", 65_010_000_000, now));
        let signals = cv.detect_arbitrage("BTCUSDT", now).expect("should detect");
        assert!(signals.is_empty());
    }

    #[test]
    fn test_empty_symbol_rejected() {
        let cv = CrossValidator::new();
        let err = cv.validate("", 1_000_000_000_000).unwrap_err();
        assert!(matches!(err, CrossValidationError::EmptySymbol));
    }

    #[test]
    fn test_window_eviction_at_capacity() {
        let mut cv = CrossValidator::new();
        let base_ts = 1_000_000_000_000;
        // Insert more than MAX_SAMPLES_PER_EXCHANGE
        for i in 0..MAX_SAMPLES_PER_EXCHANGE + 10 {
            cv.insert_sample(
                "BTCUSDT",
                make_sample("bybit", 65_000_000_000 + i as u64, base_ts + i as u64),
            );
        }
        // Should still work — oldest evicted
        cv.insert_sample("BTCUSDT", make_sample("okx", 65_000_000_000, base_ts + 200));
        let result = cv.validate("BTCUSDT", base_ts + 200);
        assert!(result.is_ok());
    }

    #[test]
    fn test_spread_bps_integer_arithmetic() {
        let mut cv = CrossValidator::new();
        let now = 1_000_000_000_000;
        // Exact 1% spread: 100 bps
        cv.insert_sample("BTCUSDT", make_sample("bybit", 100_000_000_000, now));
        cv.insert_sample("BTCUSDT", make_sample("okx", 101_000_000_000, now));
        let result = cv.validate("BTCUSDT", now).expect("should validate");
        // spread = 1_000_000_000, median = 100_500_000_000
        // bps = 1_000_000_000 * 10000 / 100_500_000_000 ≈ 99
        assert!(result.spread_bps >= 99 && result.spread_bps <= 100);
    }
}
