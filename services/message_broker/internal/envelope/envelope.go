package envelope

import (
	"bytes"
	"encoding/json"
	"fmt"
)

// EngineMessage mirrors governance/schemas/engine-contract-v1.json.
type EngineMessage struct {
	ContractVersion string          `json:"contract_version"`
	MessageType     string          `json:"message_type"`
	SourceEngine    string          `json:"source_engine"`
	Timestamp       string          `json:"timestamp"`
	Payload         json.RawMessage `json:"payload"`
	Metadata        MessageMetadata `json:"metadata"`
}

type MessageMetadata struct {
	SpecificationID  string `json:"specification_id"`
	PolicyVersion    string `json:"policy_version"`
	Owner            string `json:"owner"`
	ValidationStatus string `json:"validation_status"`
}

var validEngines = map[string]bool{
	"rust_engine": true, "python_engine": true, "go_engine": true,
}

func Validate(data []byte) (*EngineMessage, error) {
	dec := json.NewDecoder(bytes.NewReader(data))
	dec.DisallowUnknownFields()
	var msg EngineMessage
	if err := dec.Decode(&msg); err != nil {
		return nil, fmt.Errorf("envelope decode: %w", err)
	}
	if msg.ContractVersion != "1.0" {
		return nil, fmt.Errorf("invalid contract_version: %s", msg.ContractVersion)
	}
	if !validEngines[msg.SourceEngine] {
		return nil, fmt.Errorf("invalid source_engine: %s", msg.SourceEngine)
	}
	if msg.MessageType == "" || msg.Timestamp == "" {
		return nil, fmt.Errorf("missing required fields")
	}
	if msg.Metadata.SpecificationID == "" || msg.Metadata.Owner == "" {
		return nil, fmt.Errorf("missing required metadata fields")
	}
	return &msg, nil
}
