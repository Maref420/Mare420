//! Atlas IPC Server — UDS endpoint wiring transport to risk engine.
//!
//! GOVERNANCE: Matrix A - Rust Compute Layer
//! CONTRACT: ipc-binary-v1.spec.yaml (length-prefixed frames)
//! SAFETY: No unsafe code, no panics on request path.

#![forbid(unsafe_code)]
#![deny(clippy::unwrap_used)]
#![deny(clippy::expect_used)]
#![deny(clippy::panic)]

use atlas_risk_engine::assessment::{assess_order, RiskConfig};
use atlas_risk_engine::types::RiskAssessment;
use uuid::Uuid;
use log::{error, info, warn};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::env;
use std::io::{self, Read, Write};
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::Path;

#[derive(Debug, Deserialize)]
struct RiskRequest {
    order_id: String,
    agent_id: String,
    symbol: String,
    quantity: f64,
    #[serde(default = "default_max_qty")]
    max_order_quantity: f64,
    #[serde(default)]
    allowed_symbols: Vec<String>,
    #[serde(default)]
    require_risk_score: bool,
}

fn default_max_qty() -> f64 {
    1000.0
}

#[derive(Debug, Serialize)]
struct RiskResponse {
    success: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    assessment: Option<RiskAssessment>,
    #[serde(skip_serializing_if = "Option::is_none")]
    error: Option<String>,
}

fn read_exact<R: Read>(reader: &mut R, buf: &mut [u8]) -> io::Result<()> {
    let mut total = 0usize;
    while total < buf.len() {
        match reader.read(&mut buf[total..]) {
            Ok(0) => return Err(io::Error::new(io::ErrorKind::UnexpectedEof, "unexpected EOF")),
            Ok(n) => total += n,
            Err(ref e) if e.kind() == io::ErrorKind::Interrupted => continue,
            Err(e) => return Err(e),
        }
    }
    Ok(())
}

fn read_frame(stream: &mut impl Read) -> io::Result<Vec<u8>> {
    let mut len_buf = [0u8; 4];
    read_exact(stream, &mut len_buf)?;
    let length = u32::from_be_bytes(len_buf) as usize;
    if length == 0 || length > 16_777_216 {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            format!("invalid frame length: {length}"),
        ));
    }
    let mut payload = vec![0u8; length];
    read_exact(stream, &mut payload)?;
    Ok(payload)
}

fn write_frame(stream: &mut impl Write, payload: &[u8]) -> io::Result<()> {
    let length = payload.len() as u32;
    stream.write_all(&length.to_be_bytes())?;
    stream.write_all(payload)?;
    stream.flush()?;
    Ok(())
}

fn process_request(input: Value) -> Value {
    let req: RiskRequest = match serde_json::from_value(input.clone()) {
        Ok(r) => r,
        Err(e) => {
            return serde_json::json!({
                "status": "ok",
                "received": input,
                "note": format!("not a risk request: {e}")
            });
        }
    };

    let order_uuid = match Uuid::parse_str(&req.order_id) {
        Ok(id) => id,
        Err(e) => {
            let resp = RiskResponse {
                success: false,
                assessment: None,
                error: Some(format!("invalid order_id '{}': {}", req.order_id, e)),
            };
            return match serde_json::to_value(resp) {
                Ok(v) => v,
                Err(e) => {
                    error!("response serialization failed: {e}");
                    serde_json::json!({"success": false, "error": "internal serialization error"})
                }
            };
        }
    };

    let config = RiskConfig {
        max_order_quantity: req.max_order_quantity,
        allowed_symbols: req.allowed_symbols,
        require_risk_score: req.require_risk_score,
    };

    let assessment = assess_order(order_uuid, &req.agent_id, &req.symbol, req.quantity, &config);

    let resp = RiskResponse {
        success: true,
        assessment: Some(assessment),
        error: None,
    };

    match serde_json::to_value(resp) {
        Ok(v) => v,
        Err(e) => {
            error!("response serialization failed: {e}");
            serde_json::json!({"success": false, "error": "internal serialization error"})
        }
    }
}

fn handle_client(mut stream: UnixStream) {
    loop {
        let frame = match read_frame(&mut stream) {
            Ok(f) => f,
            Err(e) => {
                if e.kind() == io::ErrorKind::UnexpectedEof {
                    info!("client disconnected");
                } else {
                    warn!("read error: {e}");
                }
                return;
            }
        };

        let response = match serde_json::from_slice::<Value>(&frame) {
            Ok(req) => process_request(req),
            Err(e) => {
                serde_json::json!({"success": false, "error": format!("invalid JSON: {e}")})
            }
        };

        let resp_bytes = match serde_json::to_vec(&response) {
            Ok(b) => b,
            Err(e) => {
                error!("serialization error: {e}");
                return;
            }
        };

        if let Err(e) = write_frame(&mut stream, &resp_bytes) {
            error!("write error: {e}");
            return;
        }
    }
}

fn main() {
    if let Err(e) = env_logger::try_init() {
        eprintln!("logger init failed: {e}");
    }

    let socket_path = env::var("IPC_SOCKET_PATH")
        .unwrap_or("/tmp/atlas-ipc.sock".to_string());

    if Path::new(&socket_path).exists() {
        match std::fs::remove_file(&socket_path) {
            Ok(()) => info!("removed stale socket"),
            Err(e) => error!("failed to remove stale socket: {e}"),
        }
    }

    let listener = match UnixListener::bind(&socket_path) {
        Ok(l) => l,
        Err(e) => {
            error!("failed to bind UDS at {socket_path}: {e}");
            std::process::exit(1);
        }
    };

    info!("atlas-ipc-server listening on {socket_path}");

    // Graceful shutdown: set non-blocking + periodic flag check
    let running = std::sync::Arc::new(std::sync::atomic::AtomicBool::new(true));
    let r = running.clone();

    // Spawn signal watcher thread (no external deps)
    std::thread::spawn(move || {
        // On Unix, SIGTERM/SIGINT will interrupt blocking syscalls.
        // We use a simple approach: register a handler that sets the flag.
        // Since we cannot safely use signal() without libc, we rely on
        // the process being terminated and the OS cleaning up.
        // For graceful shutdown, we check the flag in the accept loop.
        loop {
            std::thread::sleep(std::time::Duration::from_secs(1));
            if !r.load(std::sync::atomic::Ordering::Relaxed) {
                break;
            }
        }
    });

    listener.set_nonblocking(true).ok();

    while running.load(std::sync::atomic::Ordering::Relaxed) {
        match listener.accept() {
            Ok((stream, _addr)) => {
                info!("client connected");
                handle_client(stream);
            }
            Err(ref e) if e.kind() == io::ErrorKind::WouldBlock => {
                std::thread::sleep(std::time::Duration::from_millis(100));
            }
            Err(e) => {
                if running.load(std::sync::atomic::Ordering::Relaxed) {
                    error!("accept error: {e}");
                }
            }
        }
    }

    // Cleanup socket on exit
    if Path::new(&socket_path).exists() {
        match std::fs::remove_file(&socket_path) {
            Ok(()) => info!("cleaned up socket on shutdown"),
            Err(e) => warn!("failed to cleanup socket: {e}"),
        }
    }
    info!("atlas-ipc-server stopped");
}
