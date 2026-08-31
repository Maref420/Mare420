// MODULE: atlas-market-data
// GOVERNANCE: Contract test for IPC binary format v1
// ADR: docs/decisions/006-websocket-ingestion-architecture.md
// SPEC: contracts/schemas/ipc-binary-v1.spec.yaml
// WARNING: This test validates deserialization ONLY. No business logic permitted.

#[cfg(test)]
mod ipc_contract_tests {
    use std::fs;
    use std::path::Path;

    const SPEC_PATH: &str = "../../contracts/schemas/ipc-binary-v1.spec.yaml";
    const GOLDEN_DIR: &str = "../../services/ingestion/testdata/ipc_frames";

    /// Validates that the spec file exists and is readable.
    /// If this fails, all other tests are meaningless.
    #[test]
    fn spec_file_exists_and_readable() {
        let path = Path::new(SPEC_PATH);
        assert!(path.exists(), "IPC spec file not found at {}", SPEC_PATH);
        let content = fs::read_to_string(path)
            .expect("Failed to read IPC spec file");
        assert!(content.contains("version: \"1\""), "Spec must declare version 1");
        assert!(content.contains("big_endian"), "Spec must declare big_endian");
        assert!(content.contains("max: 16777216"), "Spec must declare max frame size 16MB");
    }

    /// Deserializes a length-prefixed binary frame per ipc-binary-v1 spec.
    /// Returns (payload_length, payload_bytes) or Err with explicit reason.
    /// NEVER silently returns default values on malformed input.
    fn deserialize_frame(raw: &[u8]) -> Result<(u32, Vec<u8>), String> {
        if raw.len() < 4 {
            return Err(format!(
                "truncated header: got {} bytes, need minimum 4",
                raw.len()
            ));
        }

        let length = u32::from_be_bytes([raw[0], raw[1], raw[2], raw[3]]);

        if length == 0 {
            return Err("zero_length_payload: REJECTED per spec".to_string());
        }

        if length > 16_777_216 {
            return Err(format!(
                "oversized_payload: {} bytes exceeds max 16777216",
                length
            ));
        }

        let expected_total = 4 + length as usize;
        if raw.len() < expected_total {
            return Err(format!(
                "truncated_payload: header says {} bytes but only {} available after header",
                length,
                raw.len() - 4
            ));
        }

        let payload = raw[4..4 + length as usize].to_vec();
        Ok((length, payload))
    }

    #[test]
    fn valid_single_frame_deserializes_correctly() {
        // Frame: [0x00, 0x00, 0x00, 0x05] + b"hello"
        let frame: Vec<u8> = vec![0x00, 0x00, 0x00, 0x05, b'h', b'e', b'l', b'l', b'o'];
        let (length, payload) = deserialize_frame(&frame).expect("valid frame must deserialize");
        assert_eq!(length, 5);
        assert_eq!(payload, b"hello");
    }

    #[test]
    fn minimum_valid_frame_one_byte_payload() {
        // Frame: [0x00, 0x00, 0x00, 0x01] + b"x"
        let frame: Vec<u8> = vec![0x00, 0x00, 0x00, 0x01, b'x'];
        let (length, payload) = deserialize_frame(&frame).expect("1-byte payload must be valid");
        assert_eq!(length, 1);
        assert_eq!(payload, b"x");
    }

    #[test]
    fn zero_length_payload_rejected() {
        let frame: Vec<u8> = vec![0x00, 0x00, 0x00, 0x00];
        let err = deserialize_frame(&frame).unwrap_err();
        assert!(err.contains("zero_length_payload"), "must explicitly reject zero-length: got '{}'", err);
    }

    #[test]
    fn oversized_payload_rejected() {
        // Length = 16777217 (one byte over max)
        let mut frame: Vec<u8> = vec![0x01, 0x00, 0x00, 0x01]; // 16777217 in BE
        frame.extend(vec![0u8; 100]); // dummy payload (won't be read)
        let err = deserialize_frame(&frame).unwrap_err();
        assert!(err.contains("oversized_payload"), "must explicitly reject oversized: got '{}'", err);
    }

    #[test]
    fn truncated_header_rejected() {
        let frame: Vec<u8> = vec![0x00, 0x00]; // only 2 bytes
        let err = deserialize_frame(&frame).unwrap_err();
        assert!(err.contains("truncated header"), "must explicitly reject truncated header: got '{}'", err);
    }

    #[test]
    fn truncated_payload_rejected() {
        // Header says 10 bytes but only 3 available
        let frame: Vec<u8> = vec![0x00, 0x00, 0x00, 0x0A, b'a', b'b', b'c'];
        let err = deserialize_frame(&frame).unwrap_err();
        assert!(err.contains("truncated_payload"), "must explicitly reject truncated payload: got '{}'", err);
    }

    #[test]
    fn golden_fixture_files_exist() {
        let dir = Path::new(GOLDEN_DIR);
        assert!(dir.exists(), "Golden fixture directory must exist at {}", GOLDEN_DIR);
        let entries: Vec<_> = fs::read_dir(dir)
            .expect("Failed to read golden fixture directory")
            .filter_map(|e| e.ok())
            .collect();
        assert!(
            !entries.is_empty(),
            "Golden fixture directory must contain at least one .bin file. \
             Run Go cross-validation generator first."
        );
    }

    #[test]
    fn all_golden_fixtures_deserialize_successfully() {
        let dir = Path::new(GOLDEN_DIR);
        if !dir.exists() {
            return; // golden_fixture_files_exist test will catch this
        }
        for entry in fs::read_dir(dir).expect("Failed to read golden dir") {
            let entry = entry.expect("Failed to read dir entry");
            let path = entry.path();
            if path.extension().map_or(false, |ext| ext == "bin") {
                let raw = fs::read(&path)
                    .unwrap_or_else(|e| panic!("Failed to read golden fixture {:?}: {}", path, e));
                let result = deserialize_frame(&raw);
                assert!(
                    result.is_ok(),
                    "Golden fixture {:?} must deserialize successfully per spec, got error: {:?}",
                    path.file_name().unwrap(),
                    result.err()
                );
            }
        }
    }
}
