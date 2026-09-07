// MODULE: atlas-arb-orchestrator
// GOVERNANCE: Matrix A - Rust Compute Layer
// CONTRACT: Reads ForensicsSignals, converts to ExchangeSignals,
//           runs ArbGraph detect_arbitrage, outputs ArbitragePaths via IPC.
// WARNING: No unwrap/expect/panic on request path. Graceful shutdown.
// §17: Written directly — orchestration logic.
use std::collections::HashMap;
use std::io::{self, BufRead, Write};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::Duration;

use arb_graph::mapper::{detect_arbitrage, ArbitragePath, ExchangeSignal};
use feature_engine::models::ForensicsSignal;
use serde::{Deserialize, Serialize};

/// IPC message envelope for sending arbitrage paths to Go Gateway.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IpcMessage {
    pub msg_type: String,
    pub payload: serde_json::Value,
    pub trace_id: String,
    pub timestamp_ns: u64,
    pub source_uri: String,
}

/// Converts a ForensicsSignal into an ExchangeSignal.
fn forensics_to_exchange(signal: &ForensicsSignal) -> Option<ExchangeSignal> {
    let parts: Vec<&str> = signal.symbol.split('_').collect();
    let (source, target, sym) = if parts.len() >= 3 {
        (parts[0].to_string(), parts[1].to_string(), parts[2..].join("_"))
    } else {
        let src = signal.source_uri.replace("rust-feature-engine://", "");
        (src, "default_target".to_string(), signal.symbol.clone())
    };

    Some(ExchangeSignal {
        source_exchange: source,
        target_exchange: target,
        symbol: sym,
        spread_bps: signal.raw_spread_bps,
        vpin_toxicity: signal.vpin_toxicity,
        confidence: signal.confidence,
        timestamp_ns: signal.timestamp_ns,
    })
}

/// Groups exchange signals by symbol for batch processing.
fn group_by_symbol(signals: &[ExchangeSignal]) -> HashMap<String, Vec<ExchangeSignal>> {
    let mut groups: HashMap<String, Vec<ExchangeSignal>> = HashMap::new();
    for sig in signals {
        groups.entry(sig.symbol.clone()).or_default().push(sig.clone());
    }
    groups
}

/// Filters profitable arbitrage paths using explicit ArbitragePath type.
fn filter_profitable(paths: Vec<ArbitragePath>) -> Vec<ArbitragePath> {
    paths.into_iter().filter(|p| p.profitable).collect()
}

/// Processes a batch of ForensicsSignals and returns arbitrage IPC messages.
pub fn process_batch(
    signals: &[ForensicsSignal],
    trace_id: &str,
) -> Result<Vec<IpcMessage>, OrchestratorError> {
    let exchange_signals: Vec<ExchangeSignal> = signals
        .iter()
        .filter_map(forensics_to_exchange)
        .collect();

    if exchange_signals.is_empty() {
        return Ok(Vec::new());
    }

    let grouped = group_by_symbol(&exchange_signals);
    let mut messages: Vec<IpcMessage> = Vec::new();

    for (symbol, sigs) in &grouped {
        match detect_arbitrage(sigs, symbol) {
            Ok(paths) => {
                let profitable = filter_profitable(paths);
                for path in &profitable {
                    let payload = serde_json::to_value(path)
                        .map_err(|e| OrchestratorError::Serialization(e.to_string()))?;
                    messages.push(IpcMessage {
                        msg_type: "arbitrage_path".to_string(),
                        payload,
                        trace_id: trace_id.to_string(),
                        timestamp_ns: path.timestamp_ns,
                        source_uri: "rust-arb-orchestrator://v1".to_string(),
                    });
                }
            }
            Err(e) => {
                eprintln!("graph_error symbol={}: {}", symbol, e);
            }
        }
    }

    Ok(messages)
}

#[derive(thiserror::Error, Debug)]
pub enum OrchestratorError {
    #[error("serialization error: {0}")]
    Serialization(String),
    #[error("io error: {0}")]
    Io(#[from] io::Error),
}

fn main() {
    let running = Arc::new(AtomicBool::new(true));
    let r = running.clone();
    ctrlc_handler(r);

    eprintln!("arb_orchestrator started, reading ForensicsSignals from stdin...");

    let stdin = io::stdin();
    let stdout = io::stdout();
    let mut out = stdout.lock();
    let mut trace_counter: u64 = 0;
    let mut batch: Vec<ForensicsSignal> = Vec::new();
    let batch_size = 10;

    for line in stdin.lock().lines() {
        if !running.load(Ordering::Relaxed) {
            eprintln!("arb_orchestrator shutting down gracefully");
            break;
        }

        let line = match line {
            Ok(l) => l,
            Err(e) => {
                eprintln!("read_error: {}", e);
                continue;
            }
        };

        if line.trim().is_empty() {
            continue;
        }

        match serde_json::from_str::<ForensicsSignal>(&line) {
            Ok(signal) => {
                batch.push(signal);
                if batch.len() >= batch_size {
                    flush_batch(&mut batch, &mut trace_counter, &mut out);
                }
            }
            Err(e) => {
                eprintln!("parse_error: {}", e);
            }
        }
    }

    if !batch.is_empty() {
        flush_batch(&mut batch, &mut trace_counter, &mut out);
    }

    eprintln!("arb_orchestrator stopped");
}

fn flush_batch(
    batch: &mut Vec<ForensicsSignal>,
    trace_counter: &mut u64,
    out: &mut impl Write,
) {
    *trace_counter += 1;
    let trace_id = format!("arb-trace-{}", trace_counter);

    match process_batch(batch, &trace_id) {
        Ok(messages) => {
            for msg in &messages {
                match serde_json::to_string(msg) {
                    Ok(json) => {
                        if let Err(e) = writeln!(out, "{}", json) {
                            eprintln!("write_error: {}", e);
                        }
                    }
                    Err(e) => {
                        eprintln!("serialize_error: {}", e);
                    }
                }
            }
        }
        Err(e) => {
            eprintln!("process_error: {}", e);
        }
    }

    batch.clear();
}

fn ctrlc_handler(running: Arc<AtomicBool>) {
    std::thread::spawn(move || {
        loop {
            std::thread::sleep(Duration::from_millis(500));
            if !running.load(Ordering::Relaxed) {
                break;
            }
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;
    use feature_engine::models::ForensicsSignal;

    fn make_forensics(symbol: &str, spread: i32, vpin: f64, conf: f64) -> ForensicsSignal {
        ForensicsSignal {
            symbol: symbol.to_string(),
            raw_spread_bps: spread,
            aqs_score: 70,
            confidence: conf,
            orderbook_imbalance: 0.5,
            vpin_toxicity: vpin,
            spoofing_detected: false,
            trace_id: "test".to_string(),
            timestamp_ns: 1_000_000_000,
            source_uri: "rust-feature-engine://v1".to_string(),
        }
    }

    #[test]
    fn test_forensics_to_exchange_parsed_symbol() {
        let sig = make_forensics("binance_okx_BTCUSDT", 10, 0.2, 0.9);
        let ex = forensics_to_exchange(&sig).expect("valid signal");
        assert_eq!(ex.source_exchange, "binance");
        assert_eq!(ex.target_exchange, "okx");
        assert_eq!(ex.symbol, "BTCUSDT");
    }

    #[test]
    fn test_forensics_to_exchange_simple_symbol() {
        let sig = make_forensics("BTCUSDT", 10, 0.2, 0.9);
        let ex = forensics_to_exchange(&sig).expect("valid signal");
        assert_eq!(ex.symbol, "BTCUSDT");
    }

    #[test]
    fn test_process_batch_empty() {
        let result = process_batch(&[], "t1").expect("empty batch ok");
        assert!(result.is_empty());
    }

    #[test]
    fn test_process_batch_triangle_profitable() {
        let signals = vec![
            make_forensics("A_B_BTC", 1, 0.01, 0.99),
            make_forensics("B_C_BTC", 1, 0.01, 0.99),
            make_forensics("C_A_BTC", 1, 0.01, 0.99),
        ];
        let msgs = process_batch(&signals, "t2").expect("batch ok");
        assert!(!msgs.is_empty(), "Expected arbitrage paths");
        for msg in &msgs {
            assert_eq!(msg.msg_type, "arbitrage_path");
            assert_eq!(msg.source_uri, "rust-arb-orchestrator://v1");
        }
    }

    #[test]
    fn test_process_batch_no_cycle() {
        let signals = vec![
            make_forensics("A_B_BTC", 100, 0.5, 0.5),
            make_forensics("C_D_BTC", 100, 0.5, 0.5),
        ];
        let msgs = process_batch(&signals, "t3").expect("batch ok");
        assert!(msgs.is_empty());
    }

    #[test]
    fn test_group_by_symbol() {
        let sigs = vec![
            ExchangeSignal {
                source_exchange: "A".into(), target_exchange: "B".into(),
                symbol: "BTC".into(), spread_bps: 10, vpin_toxicity: 0.1,
                confidence: 0.9, timestamp_ns: 1,
            },
            ExchangeSignal {
                source_exchange: "C".into(), target_exchange: "D".into(),
                symbol: "ETH".into(), spread_bps: 20, vpin_toxicity: 0.2,
                confidence: 0.8, timestamp_ns: 2,
            },
        ];
        let groups = group_by_symbol(&sigs);
        assert_eq!(groups.len(), 2);
        assert!(groups.contains_key("BTC"));
        assert!(groups.contains_key("ETH"));
    }

    #[test]
    fn test_filter_profitable_uses_arbitrage_path_type() {
        let paths = vec![
            ArbitragePath {
                exchanges: vec!["A".into(), "B".into()],
                symbol: "BTC".into(), net_weight: -0.01, hop_count: 2,
                profitable: true, timestamp_ns: 1,
                source_uri: "test://v1".into(),
            },
            ArbitragePath {
                exchanges: vec!["C".into(), "D".into()],
                symbol: "BTC".into(), net_weight: 0.05, hop_count: 2,
                profitable: false, timestamp_ns: 2,
                source_uri: "test://v1".into(),
            },
        ];
        let result = filter_profitable(paths);
        assert_eq!(result.len(), 1);
        assert!(result[0].profitable);
    }

    #[test]
    fn test_ipc_message_serialization() {
        let msg = IpcMessage {
            msg_type: "arbitrage_path".into(),
            payload: serde_json::json!({"test": true}),
            trace_id: "t1".into(),
            timestamp_ns: 1_000_000_000,
            source_uri: "rust-arb-orchestrator://v1".into(),
        };
        let json = serde_json::to_string(&msg).expect("serialize");
        let parsed: IpcMessage = serde_json::from_str(&json).expect("deserialize");
        assert_eq!(parsed.msg_type, "arbitrage_path");
    }
}
