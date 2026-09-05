//! Atlas IPC Server — Generic UDS transport for agent ↔ engine communication.
//!
//! GOVERNANCE: Matrix A - Rust Compute Layer
//! CONTRACT: ipc-binary-v1.spec.yaml (length-prefixed frames)
//! SAFETY: No unsafe code, no panics on request path.
//! NOTE: This is TRANSPORT ONLY. Business logic wiring is manual.

#![forbid(unsafe_code)]
#![deny(clippy::unwrap_used)]
#![deny(clippy::expect_used)]
#![deny(clippy::panic)]

use log::{error, info, warn};
use serde_json::Value;
use std::env;
use std::io::{self, Read, Write};
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::Path;

/// Read exactly `buf.len()` bytes from the reader.
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

/// Read a single length-prefixed frame: [4-byte BE uint32][payload].
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

/// Write a length-prefixed frame.
fn write_frame(stream: &mut impl Write, payload: &[u8]) -> io::Result<()> {
    let length = payload.len() as u32;
    stream.write_all(&length.to_be_bytes())?;
    stream.write_all(payload)?;
    stream.flush()?;
    Ok(())
}

/// Process a generic request — placeholder for business logic wiring.
/// Real integration will call assess_order() etc. here.
fn process_request(input: Value) -> Value {
    serde_json::json!({
        "status": "ok",
        "received": input
    })
}

/// Handle a single client connection (multiple requests per connection).
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
                serde_json::json!({"status": "error", "message": format!("invalid JSON: {e}")})
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
        .unwrap_or_else(|_| "/tmp/atlas-ipc.sock".to_string());

    // Clean up stale socket
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

    loop {
        match listener.accept() {
            Ok((stream, _addr)) => {
                info!("client connected");
                handle_client(stream);
            }
            Err(e) => {
                error!("accept error: {e}");
            }
        }
    }
}
