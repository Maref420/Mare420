//! MODULE: atlas-ipc-listener
//! OWNER: core_engine/ipc_listener (Rust)
//! SPEC: contracts/schemas/ipc-binary-v1.spec.yaml v1.1
//! POLICY: governance/policies/rust-policy.yaml
//! STATUS: Production-Grade | Phase 1 Active
//! NO FLOATS. NO PANIC. NO UNSAFE. NO UNWRAP.
//! DATA PATH: Single path continuation — Go Writer -> UDS -> This Listener -> parse_frame()

use atlas_market_data::{parse_frame, ParsedFrame};
use std::path::Path;
use tokio::io::{AsyncReadExt, BufReader};
use tokio::net::UnixListener;
use tokio::signal;
use tracing::{error, info, warn};

const MAX_FRAME_SIZE: usize = 16_777_216 + 4;
const READ_TIMEOUT_SECS: u64 = 60;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new("info")),
        )
        .json()
        .init();

    let socket_path = std::env::var("WS_IPC_SOCKET_PATH")
        .map_err(|_| "WS_IPC_SOCKET_PATH environment variable is required but not set")?;

    info!(socket_path = %socket_path, max_frame_size = MAX_FRAME_SIZE, "atlas-ipc-listener starting");

    if Path::new(&socket_path).exists() {
        std::fs::remove_file(&socket_path)
            .map_err(|e| format!("failed to remove stale socket {}: {}", socket_path, e))?;
    }

    let listener = UnixListener::bind(&socket_path)
        .map_err(|e| format!("failed to bind Unix socket at {}: {}", socket_path, e))?;

    info!(socket_path = %socket_path, "listening for IPC connections");

    let shutdown = async {
        signal::ctrl_c().await.ok();
        info!("shutdown signal received");
    };

    let mut stats = ListenerStats::default();

    tokio::select! {
        _ = shutdown => {
            info!(total_frames = stats.frames, total_connections = stats.connections, parse_errors = stats.errors, "graceful shutdown complete");
        }
        result = accept_loop(&listener, &mut stats) => {
            if let Err(e) = result { error!(error = %e, "accept loop failed"); }
        }
    }

    let _ = std::fs::remove_file(&socket_path);
    Ok(())
}

#[derive(Default)]
struct ListenerStats {
    frames: u64,
    connections: u64,
    errors: u64,
}

async fn accept_loop(listener: &UnixListener, stats: &mut ListenerStats) -> Result<(), Box<dyn std::error::Error>> {
    loop {
        let (stream, _) = listener.accept().await.map_err(|e| format!("accept failed: {}", e))?;
        stats.connections += 1;
        let conn_id = stats.connections;
        info!(connection_id = conn_id, "new IPC connection accepted");

        match handle_connection(stream, conn_id, stats).await {
            Ok(n) => info!(connection_id = conn_id, frames_received = n, "connection closed normally"),
            Err(e) => warn!(connection_id = conn_id, error = %e, "connection ended with error"),
        }
    }
}

async fn handle_connection(
    stream: tokio::net::UnixStream,
    conn_id: u64,
    stats: &mut ListenerStats,
) -> Result<u64, Box<dyn std::error::Error>> {
    let mut reader = BufReader::new(stream);
    let mut frames_in_conn: u64 = 0;
    let mut header_buf = [0u8; 4];

    loop {
        let read_result = tokio::time::timeout(
            std::time::Duration::from_secs(READ_TIMEOUT_SECS),
            reader.read_exact(&mut header_buf),
        ).await;

        match read_result {
            Ok(Ok(_n)) => {}
            Ok(Err(e)) if e.kind() == std::io::ErrorKind::UnexpectedEof => return Ok(frames_in_conn),
            Ok(Err(e)) => return Err(format!("read error conn {}: {}", conn_id, e).into()),
            Err(_) => return Err(format!("read timeout conn {} after {}s", conn_id, READ_TIMEOUT_SECS).into()),
        }

        let payload_length = u32::from_be_bytes(header_buf) as usize;

        if payload_length == 0 {
            stats.errors += 1;
            warn!(connection_id = conn_id, "zero-length frame rejected per spec");
            continue;
        }

        if payload_length > MAX_FRAME_SIZE - 4 {
            stats.errors += 1;
            warn!(connection_id = conn_id, payload_length = payload_length, "oversized frame rejected per spec");
            let skip_len = payload_length.min(65536);
            let mut skip_buf = vec![0u8; skip_len];
            let _ = reader.read_exact(&mut skip_buf).await;
            continue;
        }

        let mut payload_buf = vec![0u8; payload_length];
        if let Err(e) = reader.read_exact(&mut payload_buf).await {
            return Err(format!("payload read error conn {}: {}", conn_id, e).into());
        }

        let mut full_frame = Vec::with_capacity(4 + payload_length);
        full_frame.extend_from_slice(&header_buf);
        full_frame.extend_from_slice(&payload_buf);

        match parse_frame(&full_frame) {
            Ok(parsed) => {
                stats.frames += 1;
                frames_in_conn += 1;
                log_parsed_frame(conn_id, stats.frames, &parsed);
            }
            Err(e) => {
                stats.errors += 1;
                warn!(connection_id = conn_id, error = %e, "frame parse failed — logged and skipped");
            }
        }
    }
}

fn log_parsed_frame(conn_id: u64, frame_num: u64, parsed: &ParsedFrame) {
    let preview = payload_preview(&parsed.payload);
    match &parsed.trace {
        Some(trace) => info!(
            connection_id = conn_id, frame_number = frame_num,
            exchange_tag = %trace.exchange_tag, timestamp_ms = trace.timestamp_ms,
            payload_size = parsed.payload.len(), payload_preview = %preview,
            stage = "IPC_RECEIVE", trace_status = "traced",
            data_path = "Go Adapter -> SerializeFrameTraced -> UDS -> Rust parse_frame -> TraceInfo extracted",
            "FRAME RECEIVED WITH TRACE"
        ),
        None => info!(
            connection_id = conn_id, frame_number = frame_num,
            payload_size = parsed.payload.len(), payload_preview = %preview,
            stage = "IPC_RECEIVE", trace_status = "legacy",
            "FRAME RECEIVED (LEGACY)"
        ),
    }
}

fn payload_preview(payload: &[u8]) -> String {
    let s = String::from_utf8_lossy(payload);
    if s.len() > 120 { format!("{}...[truncated]", &s[..120]) } else { s.into_owned() }
}
