package envelope

import (
	"encoding/json"
	"testing"
)

func makeValidMemoryEnvelope(payload interface{}) ([]byte, error) {
	p, err := json.Marshal(payload)
	if err != nil {
		return nil, err
	}
	msg := map[string]interface{}{
		"contract_version": "1.0",
		"message_type":     "memory.experience.v1",
		"source_engine":    "rust_engine",
		"timestamp":        "2026-08-30T12:00:00Z",
		"payload":          json.RawMessage(p),
		"metadata": map[string]string{
			"specification_id":  "memory-experience-event-v1",
			"policy_version":    "1.0",
			"owner":             "Contract Layer",
			"validation_status": "validated",
		},
	}
	return json.Marshal(msg)
}

func TestValidExecutionOutcomeAccepted(t *testing.T) {
	// Scaled integers per ADR-2026-08-30-004. quantity=1.5 BTC → 150000000 satoshis
	payload := map[string]interface{}{
		"order_id": "ord-001",
		"symbol":   "BTCUSDT",
		"side":     "buy",
		"quantity": int64(150000000),
		"pnl":      int64(-15000),
		"status":   "filled",
	}
	data, err := makeValidMemoryEnvelope(payload)
	if err != nil {
		t.Fatalf("failed to create envelope: %v", err)
	}
	msg, err := Validate(data)
	if err != nil {
		t.Fatalf("valid execution_outcome rejected: %v", err)
	}
	if msg.MessageType != "memory.experience.v1" {
		t.Errorf("unexpected message_type: %s", msg.MessageType)
	}
}

func TestValidRiskAssessmentAccepted(t *testing.T) {
	payload := map[string]interface{}{
		"assessment_type":       "position_limit",
		"result":                "pass",
		"circuit_breaker_state": "normal",
		"risk_score":            int64(4200), // basis points: 4200 = 42.00%
	}
	data, err := makeValidMemoryEnvelope(payload)
	if err != nil {
		t.Fatalf("failed to create envelope: %v", err)
	}
	_, err = Validate(data)
	if err != nil {
		t.Fatalf("valid risk_assessment rejected: %v", err)
	}
}

func TestValidAgentDecisionAccepted(t *testing.T) {
	payload := map[string]interface{}{
		"decision_type":  "entry_signal",
		"input_summary":  "RSI oversold",
		"output_action":  "buy_limit",
		"confidence":     0.82,
	}
	data, err := makeValidMemoryEnvelope(payload)
	if err != nil {
		t.Fatalf("failed to create envelope: %v", err)
	}
	_, err = Validate(data)
	if err != nil {
		t.Fatalf("valid agent_decision rejected: %v", err)
	}
}

func TestInvalidExecutionOutcomeSideRejected(t *testing.T) {
	payload := map[string]interface{}{
		"order_id": "ord-002",
		"symbol":   "ETHUSDT",
		"side":     "invalid_side",
		"quantity": 1.0,
		"pnl":      0.0,
		"status":   "filled",
	}
	data, err := makeValidMemoryEnvelope(payload)
	if err != nil {
		t.Fatalf("failed to create envelope: %v", err)
	}
	_, err = Validate(data)
	if err == nil {
		t.Fatal("invalid side should be rejected")
	}
}

func TestUnknownMemoryEventTypeRejected(t *testing.T) {
	payload := map[string]interface{}{
		"unknown_field": "value",
	}
	data, err := makeValidMemoryEnvelope(payload)
	if err != nil {
		t.Fatalf("failed to create envelope: %v", err)
	}
	_, err = Validate(data)
	if err == nil {
		t.Fatal("unknown memory event type should be rejected")
	}
}

func TestNonMemoryMessageNotAffected(t *testing.T) {
	msg := map[string]interface{}{
		"contract_version": "1.0",
		"message_type":     "exec.order.v1",
		"source_engine":    "rust_engine",
		"timestamp":        "2026-08-30T12:00:00Z",
		"payload":          map[string]string{"order_id": "test"},
		"metadata": map[string]string{
			"specification_id":  "order-v1",
			"policy_version":    "1.0",
			"owner":             "Execution Engine",
			"validation_status": "validated",
		},
	}
	data, err := json.Marshal(msg)
	if err != nil {
		t.Fatalf("marshal failed: %v", err)
	}
	_, err = Validate(data)
	if err != nil {
		t.Fatalf("non-memory message should not be affected: %v", err)
	}
}

// === Strategy Signal Payload Validation Tests ===

func TestValidateStrategySignalValid(t *testing.T) {
	env := "{" +
		`"contract_version":"1.0",` +
		`"message_type":"strategy.signal.v1",` +
		`"source_engine":"python_engine",` +
		`"timestamp":"2026-08-31T10:00:00Z",` +
		`"payload":{` +
		`"version":"1.0.0",` +
		`"event_id":"550e8400-e29b-41d4-a716-446655440000",` +
		`"timestamp_utc":"2026-08-31T10:00:00Z",` +
		`"source_agent":"test_agent",` +
		`"signal":{` +
		`"symbol":"BTCUSDT",` +
		`"direction":"LONG",` +
		`"confidence":0.87,` +
		`"regime":"TRENDING"` +
		`}` +
		`},` +
		`"metadata":{` +
		`"specification_id":"strategy-signal-event-v1",` +
		`"policy_version":"1.0",` +
		`"owner":"core_engine_team",` +
		`"validation_status":"validated"` +
		`}` +
		"}"
	msg, err := Validate([]byte(env))
	if err != nil {
		t.Fatalf("expected valid strategy signal, got error: %v", err)
	}
	if msg.MessageType != "strategy.signal.v1" {
		t.Errorf("expected message_type strategy.signal.v1, got %s", msg.MessageType)
	}
}

func TestValidateStrategySignalInvalidSymbol(t *testing.T) {
	env := "{" +
		`"contract_version":"1.0",` +
		`"message_type":"strategy.signal.v1",` +
		`"source_engine":"python_engine",` +
		`"timestamp":"2026-08-31T10:00:00Z",` +
		`"payload":{` +
		`"version":"1.0.0",` +
		`"event_id":"550e8400-e29b-41d4-a716-446655440000",` +
		`"timestamp_utc":"2026-08-31T10:00:00Z",` +
		`"source_agent":"test_agent",` +
		`"signal":{` +
		`"symbol":"x",` +
		`"direction":"LONG",` +
		`"confidence":0.5,` +
		`"regime":"TRENDING"` +
		`}` +
		`},` +
		`"metadata":{` +
		`"specification_id":"strategy-signal-event-v1",` +
		`"policy_version":"1.0",` +
		`"owner":"core_engine_team",` +
		`"validation_status":"validated"` +
		`}` +
		"}"
	_, err := Validate([]byte(env))
	if err == nil {
		t.Fatal("expected error for invalid symbol, got nil")
	}
}

func TestValidateStrategySignalInvalidDirection(t *testing.T) {
	env := "{" +
		`"contract_version":"1.0",` +
		`"message_type":"strategy.signal.v1",` +
		`"source_engine":"python_engine",` +
		`"timestamp":"2026-08-31T10:00:00Z",` +
		`"payload":{` +
		`"version":"1.0.0",` +
		`"event_id":"550e8400-e29b-41d4-a716-446655440000",` +
		`"timestamp_utc":"2026-08-31T10:00:00Z",` +
		`"source_agent":"test_agent",` +
		`"signal":{` +
		`"symbol":"BTCUSDT",` +
		`"direction":"INVALID",` +
		`"confidence":0.5,` +
		`"regime":"TRENDING"` +
		`}` +
		`},` +
		`"metadata":{` +
		`"specification_id":"strategy-signal-event-v1",` +
		`"policy_version":"1.0",` +
		`"owner":"core_engine_team",` +
		`"validation_status":"validated"` +
		`}` +
		"}"
	_, err := Validate([]byte(env))
	if err == nil {
		t.Fatal("expected error for invalid direction, got nil")
	}
}

func TestValidateStrategySignalConfidenceOutOfRange(t *testing.T) {
	env := "{" +
		`"contract_version":"1.0",` +
		`"message_type":"strategy.signal.v1",` +
		`"source_engine":"python_engine",` +
		`"timestamp":"2026-08-31T10:00:00Z",` +
		`"payload":{` +
		`"version":"1.0.0",` +
		`"event_id":"550e8400-e29b-41d4-a716-446655440000",` +
		`"timestamp_utc":"2026-08-31T10:00:00Z",` +
		`"source_agent":"test_agent",` +
		`"signal":{` +
		`"symbol":"BTCUSDT",` +
		`"direction":"LONG",` +
		`"confidence":1.5,` +
		`"regime":"TRENDING"` +
		`}` +
		`},` +
		`"metadata":{` +
		`"specification_id":"strategy-signal-event-v1",` +
		`"policy_version":"1.0",` +
		`"owner":"core_engine_team",` +
		`"validation_status":"validated"` +
		`}` +
		"}"
	_, err := Validate([]byte(env))
	if err == nil {
		t.Fatal("expected error for confidence out of range, got nil")
	}
}

func TestValidateStrategySignalUnknownField(t *testing.T) {
	env := "{" +
		`"contract_version":"1.0",` +
		`"message_type":"strategy.signal.v1",` +
		`"source_engine":"python_engine",` +
		`"timestamp":"2026-08-31T10:00:00Z",` +
		`"payload":{` +
		`"version":"1.0.0",` +
		`"event_id":"550e8400-e29b-41d4-a716-446655440000",` +
		`"timestamp_utc":"2026-08-31T10:00:00Z",` +
		`"source_agent":"test_agent",` +
		`"signal":{` +
		`"symbol":"BTCUSDT",` +
		`"direction":"LONG",` +
		`"confidence":0.5,` +
		`"regime":"TRENDING"` +
		`},` +
		`"unexpected_field":true` +
		`},` +
		`"metadata":{` +
		`"specification_id":"strategy-signal-event-v1",` +
		`"policy_version":"1.0",` +
		`"owner":"core_engine_team",` +
		`"validation_status":"validated"` +
		`}` +
		"}"
	_, err := Validate([]byte(env))
	if err == nil {
		t.Fatal("expected error for unknown field, got nil")
	}
}
