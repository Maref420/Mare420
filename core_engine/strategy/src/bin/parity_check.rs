//! Parity Check Binary
//!
//! Reads a canonical JSON fixture, deserializes via contract_types,
//! re-serializes with serde_json (sorted keys), and prints to stdout.
//! Used by Python cross-language parity tests.
//!
//! Usage: parity_check <path-to-fixture.json>

use std::env;
use std::fs;
use std::process;

use atlas_strategy_engine::contract_types::StrategySignalEventV1;

fn main() {
    let args: Vec<String> = env::args().collect();
    if args.len() != 2 {
        eprintln!("Usage: {} <fixture.json>", args[0]);
        process::exit(1);
    }

    let fixture_path = &args[1];
    let raw = match fs::read_to_string(fixture_path) {
        Ok(content) => content,
        Err(e) => {
            eprintln!("Failed to read fixture: {e}");
            process::exit(1);
        }
    };

    let event: StrategySignalEventV1 = match serde_json::from_str(&raw) {
        Ok(event) => event,
        Err(e) => {
            eprintln!("Failed to deserialize fixture: {e}");
            process::exit(1);
        }
    };

    if let Err(e) = event.validate_contract() {
        eprintln!("Fixture failed contract validation: {e}");
        process::exit(1);
    }

    // Convert to serde_json::Value to enable sorted keys
    let value = match serde_json::to_value(&event) {
        Ok(v) => v,
        Err(e) => {
            eprintln!("Failed to convert to Value: {e}");
            process::exit(1);
        }
    };

    // Serialize with sorted keys for canonical form

    // Use BTreeMap-based sorting via Value
    let sorted = sort_json_value(value);
    match serde_json::to_string(&sorted) {
        Ok(json) => print!("{json}"),
        Err(e) => {
            eprintln!("Failed to serialize: {e}");
            process::exit(1);
        }
    }
}

/// Recursively sort JSON object keys for deterministic output.
fn sort_json_value(value: serde_json::Value) -> serde_json::Value {
    match value {
        serde_json::Value::Object(map) => {
            let mut sorted: serde_json::Map<String, serde_json::Value> =
                serde_json::Map::new();
            let mut keys: Vec<String> = map.keys().cloned().collect();
            keys.sort();
            for key in keys {
                if let Some(v) = map.get(&key) {
                    sorted.insert(key, sort_json_value(v.clone()));
                }
            }
            serde_json::Value::Object(sorted)
        }
        serde_json::Value::Array(arr) => {
            serde_json::Value::Array(arr.into_iter().map(sort_json_value).collect())
        }
        other => other,
    }
}
