//! ╔═══════════════════════════════════════════════════════════╗
//! ║ MODULE: atlas-market-data / ipc_parser                   ║
//! ║ OWNER: core_engine/market_data (Rust)                    ║
//! ║ SPEC: contracts/schemas/ipc-binary-v1.spec.yaml v1.1     ║
//! ║ POLICY: governance/policies/rust-policy.yaml             ║
//!  STATUS: Production-Grade | Phase 1 Active                ║
//! ╠═══════════════════════════════════════════════════════════╣
//! ║ ⛔  NO FLOATS. NO PANIC. NO UNSAFE. NO UNWRAP.           ║
//! ║ ⛔  Backward-compatible: handles both legacy (flags=0x00) ║
//! ║    and traced (flags=0x01) frames per spec v1.1          ║
//! ╚═══════════════════════════════════════════════════════════╝

/// Parsed result from an IPC frame.
/// Contains the raw payload and optional trace metadata.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ParsedFrame {
    /// Raw payload bytes (WebSocket frame content, unchanged from source)
    pub payload: Vec<u8>,
    /// Trace metadata if flags bit 0 = 1, None for legacy frames
    pub trace: Option<TraceInfo>,
}

/// Trace metadata extracted from IPC frame header.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TraceInfo {
    /// Timestamp in milliseconds since UNIX epoch (from trace header)
    pub timestamp_ms: u64,
    /// Exchange identifier tag (e.g., "bybit", "okx"), max 32 bytes
    pub exchange_tag: String,
}

/// Explicit error types for IPC frame parsing.
/// No panics, no unwrap — per rust-policy.yaml.
#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub enum IpcParseError {
    #[error("truncated header: got {got} bytes, need minimum 4")]
    TruncatedHeader { got: usize },

    #[error("zero_length_payload: REJECTED per spec")]
    ZeroLengthPayload,

    #[error("oversized_payload: {size} bytes exceeds max 16777216")]
    OversizedPayload { size: u32 },

    #[error("truncated_payload: header says {expected} bytes but only {available} available after header")]
    TruncatedPayload { expected: u32, available: usize },

    #[error("truncated_trace_flags: payload too short for flags byte")]
    TruncatedTraceFlags,

    #[error("truncated_trace_timestamp: payload too short for 8-byte timestamp after flags")]
    TruncatedTraceTimestamp,

    #[error("truncated_trace_tag_length: payload too short for tag length byte")]
    TruncatedTraceTagLength,

    #[error("truncated_trace_tag: tag_length says {expected} bytes but only {available} available")]
    TruncatedTraceTag { expected: usize, available: usize },

    #[error("trace_tag_too_long: {length} bytes exceeds max 32")]
    TraceTagTooLong { length: usize },

    #[error("invalid_utf8_in_exchange_tag")]
    InvalidUtf8InExchangeTag,
}

const FLAG_TRACE_PRESENT: u8 = 0x01;
const MAX_FRAME_SIZE: u32 = 16_777_216; // 16 MB
const MAX_EXCHANGE_TAG: usize = 32;

/// Parse a raw IPC frame per ipc-binary-v1 spec v1.1.
///
/// Frame format: [4-byte BE total_length][payload_after_header]
///
/// When flags bit 0 = 0 (legacy):
///   payload_after_header = [raw WebSocket frame bytes]
///
/// When flags bit 0 = 1 (traced):
///   payload_after_header = [1-byte flags][8-byte BE timestamp_ms][1-byte tag_len][tag_bytes][raw payload]
///
/// Returns ParsedFrame with payload and optional TraceInfo.
/// NEVER panics. NEVER unwraps. All errors are explicit IpcParseError variants.
pub fn parse_frame(raw: &[u8]) -> Result<ParsedFrame, IpcParseError> {
    // Step 1: Validate minimum header size
    if raw.len() < 4 {
        return Err(IpcParseError::TruncatedHeader { got: raw.len() });
    }

    // Step 2: Read length prefix (big-endian u32)
    let total_length = u32::from_be_bytes([raw[0], raw[1], raw[2], raw[3]]);

    // Step 3: Validate length constraints
    if total_length == 0 {
        return Err(IpcParseError::ZeroLengthPayload);
    }
    if total_length > MAX_FRAME_SIZE {
        return Err(IpcParseError::OversizedPayload { size: total_length });
    }

    // Step 4: Validate we have enough bytes for the full frame
    let expected_total = 4usize + total_length as usize;
    if raw.len() < expected_total {
        return Err(IpcParseError::TruncatedPayload {
            expected: total_length,
            available: raw.len().saturating_sub(4),
        });
    }

    // Step 5: Extract the payload-after-header region
    let after_header = &raw[4..expected_total];

    // Step 6: Check flags byte (first byte of after_header)
    if after_header.is_empty() {
        return Err(IpcParseError::TruncatedTraceFlags);
    }

    let flags = after_header[0];

    if flags & FLAG_TRACE_PRESENT == 0 {
        // Legacy format: flags=0x00, rest is raw payload
        let payload = after_header[1..].to_vec();
        return Ok(ParsedFrame {
            payload,
            trace: None,
        });
    }

    // Traced format: flags=0x01
    // Layout after flags: [8-byte timestamp_ms][1-byte tag_len][tag_bytes][payload]

    // Step 7: Validate timestamp (8 bytes after flags)
    if after_header.len() < 1 + 8 {
        return Err(IpcParseError::TruncatedTraceTimestamp);
    }

    let timestamp_ms = u64::from_be_bytes([
        after_header[1],
        after_header[2],
        after_header[3],
        after_header[4],
        after_header[5],
        after_header[6],
        after_header[7],
        after_header[8],
    ]);

    // Step 8: Validate tag length byte
    if after_header.len() < 1 + 8 + 1 {
        return Err(IpcParseError::TruncatedTraceTagLength);
    }

    let tag_len = after_header[9] as usize;

    if tag_len > MAX_EXCHANGE_TAG {
        return Err(IpcParseError::TraceTagTooLong { length: tag_len });
    }

    // Step 9: Validate tag bytes available
    if after_header.len() < 1 + 8 + 1 + tag_len {
        return Err(IpcParseError::TruncatedTraceTag {
            expected: tag_len,
            available: after_header.len().saturating_sub(1 + 8 + 1),
        });
    }

    // Step 10: Extract exchange tag (validate UTF-8)
    let tag_bytes = &after_header[10..10 + tag_len];
    let exchange_tag = match std::str::from_utf8(tag_bytes) {
        Ok(s) => s.to_string(),
        Err(_) => return Err(IpcParseError::InvalidUtf8InExchangeTag),
    };

    // Step 11: Extract raw payload (everything after trace fields)
    let payload_start = 1 + 8 + 1 + tag_len;
    let payload = after_header[payload_start..].to_vec();

    Ok(ParsedFrame {
        payload,
        trace: Some(TraceInfo {
            timestamp_ms,
            exchange_tag,
        }),
    })
}

#[cfg(test)]
#[cfg_attr(test, allow(clippy::panic))]
mod tests {
    use super::*;

    #[test]
    fn test_parse_legacy_frame_no_trace() {
        // Build a legacy frame: [4-byte len][flags=0x00][payload]
        let payload = b"hello world";
        let total_len = (1 + payload.len()) as u32;
        let mut frame = Vec::new();
        frame.extend_from_slice(&total_len.to_be_bytes());
        frame.push(0x00); // flags: no trace
        frame.extend_from_slice(payload);

        let parsed = parse_frame(&frame).expect("legacy frame must parse");
        assert_eq!(parsed.payload, payload);
        assert!(parsed.trace.is_none());
    }

    #[test]
    fn test_parse_traced_frame_bybit() {
        // Build a traced frame matching Go SerializeFrameTraced output
        let payload = br#"{"topic":"tickers.BTCUSDT","lastPrice":"74734"}"#;
        let exchange_tag = b"bybit";
        let timestamp_ms: u64 = 1788293930811;

        let total_len = (1 + 8 + 1 + exchange_tag.len() + payload.len()) as u32;
        let mut frame = Vec::new();
        frame.extend_from_slice(&total_len.to_be_bytes());
        frame.push(0x01); // flags: trace present
        frame.extend_from_slice(&timestamp_ms.to_be_bytes());
        frame.push(exchange_tag.len() as u8);
        frame.extend_from_slice(exchange_tag);
        frame.extend_from_slice(payload);

        let parsed = parse_frame(&frame).expect("traced frame must parse");
        assert_eq!(parsed.payload, payload);

        let trace = parsed.trace.expect("trace must be present");
        assert_eq!(trace.timestamp_ms, 1788293930811);
        assert_eq!(trace.exchange_tag, "bybit");
    }

    #[test]
    fn test_parse_traced_frame_okx() {
        let payload = br#"{"instId":"BTC-USDT","last":"65432.1"}"#;
        let exchange_tag = b"okx";
        let timestamp_ms: u64 = 1788293930811;

        let total_len = (1 + 8 + 1 + exchange_tag.len() + payload.len()) as u32;
        let mut frame = Vec::new();
        frame.extend_from_slice(&total_len.to_be_bytes());
        frame.push(0x01);
        frame.extend_from_slice(&timestamp_ms.to_be_bytes());
        frame.push(exchange_tag.len() as u8);
        frame.extend_from_slice(exchange_tag);
        frame.extend_from_slice(payload);

        let parsed = parse_frame(&frame).expect("traced frame must parse");
        assert_eq!(parsed.payload, payload);

        let trace = parsed.trace.expect("trace must be present");
        assert_eq!(trace.exchange_tag, "okx");
    }

    #[test]
    fn test_truncated_header_rejected() {
        let frame = vec![0x00, 0x00]; // only 2 bytes
        let err = parse_frame(&frame).unwrap_err();
        assert!(matches!(err, IpcParseError::TruncatedHeader { got: 2 }));
    }

    #[test]
    fn test_zero_length_rejected() {
        let frame = vec![0x00, 0x00, 0x00, 0x00];
        let err = parse_frame(&frame).unwrap_err();
        assert!(matches!(err, IpcParseError::ZeroLengthPayload));
    }

    #[test]
    fn test_oversized_payload_rejected() {
        let mut frame = vec![0x01, 0x00, 0x00, 0x01]; // 16777217
        frame.extend(vec![0u8; 10]);
        let err = parse_frame(&frame).unwrap_err();
        assert!(matches!(err, IpcParseError::OversizedPayload { .. }));
    }

    #[test]
    fn test_truncated_payload_rejected() {
        // Header says 10 bytes but only 3 available after header
        let frame = vec![0x00, 0x00, 0x00, 0x0A, 0x00, b'a', b'b'];
        let err = parse_frame(&frame).unwrap_err();
        assert!(matches!(err, IpcParseError::TruncatedPayload { .. }));
    }

    #[test]
    fn test_truncated_trace_timestamp_rejected() {
        // flags=0x01 but only 2 bytes after flags (need 8 for timestamp)
        let total_len: u32 = 3; // flags(1) + 2 bytes
        let mut frame = Vec::new();
        frame.extend_from_slice(&total_len.to_be_bytes());
        frame.push(0x01); // flags: trace present
        frame.push(0x00);
        frame.push(0x00);
        let err = parse_frame(&frame).unwrap_err();
        assert!(matches!(err, IpcParseError::TruncatedTraceTimestamp));
    }

    #[test]
    fn test_trace_tag_too_long_rejected() {
        // tag_len = 33 (exceeds max 32)
        let total_len: u32 = 1 + 8 + 1 + 33;
        let mut frame = Vec::new();
        frame.extend_from_slice(&total_len.to_be_bytes());
        frame.push(0x01);
        frame.extend_from_slice(&0u64.to_be_bytes()); // timestamp
        frame.push(33); // tag_len > 32
        frame.extend(vec![b'x'; 33]);
        let err = parse_frame(&frame).unwrap_err();
        assert!(matches!(err, IpcParseError::TraceTagTooLong { length: 33 }));
    }

    #[test]
    fn test_invalid_utf8_tag_rejected() {
        let total_len: u32 = 1 + 8 + 1 + 2;
        let mut frame = Vec::new();
        frame.extend_from_slice(&total_len.to_be_bytes());
        frame.push(0x01);
        frame.extend_from_slice(&0u64.to_be_bytes());
        frame.push(2);
        frame.push(0xFF);
        frame.push(0xFE); // invalid UTF-8
        let err = parse_frame(&frame).unwrap_err();
        assert!(matches!(err, IpcParseError::InvalidUtf8InExchangeTag));
    }

    #[test]
    fn test_empty_payload_after_trace_fields() {
        // Valid traced frame with empty payload (just trace fields)
        let exchange_tag = b"bybit";
        let timestamp_ms: u64 = 1788293930811;
        let total_len = (1 + 8 + 1 + exchange_tag.len()) as u32; // no payload bytes
        let mut frame = Vec::new();
        frame.extend_from_slice(&total_len.to_be_bytes());
        frame.push(0x01);
        frame.extend_from_slice(&timestamp_ms.to_be_bytes());
        frame.push(exchange_tag.len() as u8);
        frame.extend_from_slice(exchange_tag);

        let parsed = parse_frame(&frame).expect("empty payload after trace must parse");
        assert!(parsed.payload.is_empty());
        let trace = parsed.trace.expect("trace must be present");
        assert_eq!(trace.exchange_tag, "bybit");
    }
}
