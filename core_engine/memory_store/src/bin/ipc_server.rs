use std::io::{self, BufRead, Write};
use memory_store::{BackgroundScheduler, MemoryGraph, MemoryNode, PersistConfig};
use serde::{Deserialize, Serialize};

#[derive(Debug, Deserialize)]
struct IpcRequest {
    cmd: String,
    #[serde(default)]
    payload: serde_json::Value,
}

#[derive(Debug, Serialize)]
struct IpcResponse {
    ok: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    data: Option<serde_json::Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    error: Option<IpcError>,
}

#[derive(Debug, Serialize)]
struct IpcError {
    code: String,
    message: String,
    retryable: bool,
}

impl IpcResponse {
    fn success(data: serde_json::Value) -> Self {
        Self { ok: true, data: Some(data), error: None }
    }
    fn empty_success() -> Self {
        Self { ok: true, data: None, error: None }
    }
    fn fail(code: &str, message: &str, retryable: bool) -> Self {
        Self {
            ok: false,
            data: None,
            error: Some(IpcError {
                code: code.into(),
                message: message.into(),
                retryable,
            }),
        }
    }
}

fn map_error(e: &(impl std::error::Error + ?Sized)) -> IpcResponse {
    let msg = e.to_string();
    let retryable = msg.starts_with("DEP_") || msg.starts_with("RES_");
    IpcResponse::fail(&msg, &msg, retryable)
}

fn now_ns() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_nanos() as u64)
        .unwrap_or(0)
}

fn handle_write(graph: &MemoryGraph, payload: &serde_json::Value) -> IpcResponse {
    let node: MemoryNode = match serde_json::from_value(payload.clone()) {
        Ok(n) => n,
        Err(e) => return IpcResponse::fail("VAL_INVALID_INPUT", &e.to_string(), false),
    };
    match graph.write_node(node) {
        Ok(()) => IpcResponse::empty_success(),
        Err(e) => map_error(&e),
    }
}

fn handle_read(graph: &MemoryGraph, payload: &serde_json::Value) -> IpcResponse {
    let node_id = match payload.get("node_id").and_then(|v| v.as_str()) {
        Some(id) => id,
        None => return IpcResponse::fail("VAL_INVALID_INPUT", "missing node_id", false),
    };
    match graph.read_node(node_id, now_ns()) {
        Ok(Some(node)) => match serde_json::to_value(&node) {
            Ok(v) => IpcResponse::success(v),
            Err(e) => IpcResponse::fail("INT_INVARIANT_BROKEN", &e.to_string(), false),
        },
        Ok(None) => IpcResponse::success(serde_json::Value::Null),
        Err(e) => map_error(&e),
    }
}

fn handle_search(graph: &MemoryGraph, payload: &serde_json::Value) -> IpcResponse {
    let keyword = match payload.get("keyword").and_then(|v| v.as_str()) {
        Some(k) => k,
        None => return IpcResponse::fail("VAL_INVALID_INPUT", "missing keyword", false),
    };
    match graph.search(keyword, now_ns()) {
        Ok(nodes) => match serde_json::to_value(&nodes) {
            Ok(v) => IpcResponse::success(v),
            Err(e) => IpcResponse::fail("INT_INVARIANT_BROKEN", &e.to_string(), false),
        },
        Err(e) => map_error(&e),
    }
}

fn handle_evict(graph: &MemoryGraph) -> IpcResponse {
    match graph.evict_expired(now_ns()) {
        Ok(count) => IpcResponse::success(serde_json::json!({"evicted": count})),
        Err(e) => map_error(&e),
    }
}

fn handle_stats(graph: &MemoryGraph) -> IpcResponse {
    match graph.stats(now_ns()) {
        Ok(stats) => match serde_json::to_value(&stats) {
            Ok(v) => IpcResponse::success(v),
            Err(e) => IpcResponse::fail("INT_INVARIANT_BROKEN", &e.to_string(), false),
        },
        Err(e) => map_error(&e),
    }
}

fn handle_export(graph: &MemoryGraph) -> IpcResponse {
    match graph.export_state() {
        Ok(data) => match String::from_utf8(data) {
            Ok(s) => IpcResponse::success(serde_json::Value::String(s)),
            Err(e) => IpcResponse::fail("INT_INVARIANT_BROKEN", &e.to_string(), false),
        },
        Err(e) => map_error(&e),
    }
}

fn handle_import(graph: &MemoryGraph, payload: &serde_json::Value) -> IpcResponse {
    let data_str = match payload.get("data").and_then(|v| v.as_str()) {
        Some(s) => s,
        None => return IpcResponse::fail("VAL_INVALID_INPUT", "missing data field", false),
    };
    match graph.import_state(data_str.as_bytes()) {
        Ok(()) => IpcResponse::empty_success(),
        Err(e) => map_error(&e),
    }
}

fn main() {
    let graph = std::sync::Arc::new(MemoryGraph::new());
    let config = PersistConfig::default();
    let mut _scheduler: Option<BackgroundScheduler> = None;

    if let Ok(true) = memory_store::persist::load_state(&graph, &config) {
        eprintln!("ipc_server: loaded state from {}", config.full_path().display());
    }

    match BackgroundScheduler::start(graph.clone(), config.clone()) {
        Ok(s) => _scheduler = Some(s),
        Err(e) => eprintln!("ipc_server: scheduler start failed: {}", e),
    }

    let stdin = io::stdin();
    let stdout = io::stdout();
    let mut out = stdout.lock();

    for line in stdin.lock().lines() {
        let line = match line {
            Ok(l) => l,
            Err(_) => break,
        };
        let trimmed = line.trim();
        if trimmed.is_empty() { continue; }

        let req: IpcRequest = match serde_json::from_str(trimmed) {
            Ok(r) => r,
            Err(e) => {
                let resp = IpcResponse::fail("VAL_INVALID_INPUT", &e.to_string(), false);
                let json = serde_json::to_string(&resp).unwrap_or_else(|_| {
                    r#"{"ok":false,"error":{"code":"INT_INVARIANT_BROKEN","message":"serialization failed","retryable":false}}"#.into()
                });
                if writeln!(out, "{}", json).is_err() { break; }
                if out.flush().is_err() { break; }
                continue;
            }
        };

        let resp = match req.cmd.as_str() {
            "write" => handle_write(&graph, &req.payload),
            "read" => handle_read(&graph, &req.payload),
            "search" => handle_search(&graph, &req.payload),
            "evict" => handle_evict(&graph),
            "stats" => handle_stats(&graph),
            "export" => handle_export(&graph),
            "import" => handle_import(&graph, &req.payload),
            _ => IpcResponse::fail("VAL_INVALID_INPUT", &format!("unknown cmd: {}", req.cmd), false),
        };

        let json = serde_json::to_string(&resp).unwrap_or_else(|_| {
            r#"{"ok":false,"error":{"code":"INT_INVARIANT_BROKEN","message":"serialization failed","retryable":false}}"#.into()
        });
        if writeln!(out, "{}", json).is_err() { break; }
        if out.flush().is_err() { break; }
    }

    if let Err(e) = memory_store::persist::save_state(&graph, &config) {
        eprintln!("ipc_server: shutdown save error: {}", e);
    }
}
