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

// MessageMetadata mirrors engine-contract-v1.json metadata requirements.
type MessageMetadata struct {
	SpecificationID  string `json:"specification_id"`
	PolicyVersion    string `json:"policy_version"`
	Owner            string `json:"owner"`
	ValidationStatus string `json:"validation_status"`
}

var validEngines = map[string]bool{
	"rust_engine": true, "python_engine": true, "go_engine": true,
}

// memoryEventTypes defines allowed event types for memory.experience.v1.
var memoryEventTypes = map[string]bool{
	"execution_outcome": true,
	"risk_assessment":   true,
	"agent_decision":    true,
}

// executionOutcomePayload mirrors memory-experience-event-v1.json execution_outcome fields.
type executionOutcomePayload struct {
	OrderID  string  `json:"order_id"`
	Symbol   string  `json:"symbol"`
	Side     string  `json:"side"`
	Quantity float64 `json:"quantity"`
	PnL      float64 `json:"pnl"`
	Status   string  `json:"status"`
}

// riskAssessmentPayload mirrors memory-experience-event-v1.json risk_assessment fields.
type riskAssessmentPayload struct {
	AssessmentType      string  `json:"assessment_type"`
	Result              string  `json:"result"`
	CircuitBreakerState string  `json:"circuit_breaker_state"`
	RiskScore           float64 `json:"risk_score"`
}

// agentDecisionPayload mirrors memory-experience-event-v1.json agent_decision fields.
type agentDecisionPayload struct {
	DecisionType  string  `json:"decision_type"`
	InputSummary  string  `json:"input_summary"`
	OutputAction  string  `json:"output_action"`
	Confidence    float64 `json:"confidence"`
}

// Validate validates an EngineMessage envelope per engine-contract-v1.json.
// For memory.experience.v1 messages, also validates payload per
// memory-experience-event-v1.json.
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
	// Payload-specific validation for memory experience events.
	if msg.MessageType == "memory.experience.v1" {
		if err := validateMemoryPayload(msg.Payload); err != nil {
			return nil, fmt.Errorf("memory payload validation: %w", err)
		}
	}
	return &msg, nil
}

// validateMemoryPayload validates the payload of a memory.experience.v1 message
// per contracts/schemas/memory/memory-experience-event-v1.json.
func validateMemoryPayload(raw json.RawMessage) error {
	// First determine event type by checking which payload structure matches.
	// We try each known type; the payload must match exactly one.
	var probe map[string]json.RawMessage
	if err := json.Unmarshal(raw, &probe); err != nil {
		return fmt.Errorf("payload is not a JSON object: %w", err)
	}

	// Detect event type by presence of unique required fields.
	if _, ok := probe["order_id"]; ok {
		return validateExecutionOutcome(raw)
	}
	if _, ok := probe["assessment_type"]; ok {
		return validateRiskAssessment(raw)
	}
	if _, ok := probe["decision_type"]; ok {
		return validateAgentDecision(raw)
	}

	return fmt.Errorf("unknown memory event type: cannot identify from payload fields")
}

func validateExecutionOutcome(raw json.RawMessage) error {
	dec := json.NewDecoder(bytes.NewReader(raw))
	dec.DisallowUnknownFields()
	var p executionOutcomePayload
	if err := dec.Decode(&p); err != nil {
		return fmt.Errorf("execution_outcome decode: %w", err)
	}
	if p.OrderID == "" {
		return fmt.Errorf("execution_outcome: order_id is required")
	}
	if p.Symbol == "" {
		return fmt.Errorf("execution_outcome: symbol is required")
	}
	if p.Side != "buy" && p.Side != "sell" {
		return fmt.Errorf("execution_outcome: side must be buy or sell, got %q", p.Side)
	}
	if p.Status != "filled" && p.Status != "rejected" && p.Status != "cancelled" && p.Status != "halted_by_circuit_breaker" {
		return fmt.Errorf("execution_outcome: invalid status %q", p.Status)
	}
	return nil
}

func validateRiskAssessment(raw json.RawMessage) error {
	dec := json.NewDecoder(bytes.NewReader(raw))
	dec.DisallowUnknownFields()
	var p riskAssessmentPayload
	if err := dec.Decode(&p); err != nil {
		return fmt.Errorf("risk_assessment decode: %w", err)
	}
	if p.AssessmentType == "" {
		return fmt.Errorf("risk_assessment: assessment_type is required")
	}
	if p.Result != "pass" && p.Result != "warn" && p.Result != "block" {
		return fmt.Errorf("risk_assessment: result must be pass/warn/block, got %q", p.Result)
	}
	if p.CircuitBreakerState != "normal" && p.CircuitBreakerState != "tripped" && p.CircuitBreakerState != "cooldown" {
		return fmt.Errorf("risk_assessment: invalid circuit_breaker_state %q", p.CircuitBreakerState)
	}
	if p.RiskScore < 0 || p.RiskScore > 100 {
		return fmt.Errorf("risk_assessment: risk_score must be 0-100, got %f", p.RiskScore)
	}
	return nil
}

func validateAgentDecision(raw json.RawMessage) error {
	dec := json.NewDecoder(bytes.NewReader(raw))
	dec.DisallowUnknownFields()
	var p agentDecisionPayload
	if err := dec.Decode(&p); err != nil {
		return fmt.Errorf("agent_decision decode: %w", err)
	}
	if p.DecisionType == "" {
		return fmt.Errorf("agent_decision: decision_type is required")
	}
	if p.InputSummary == "" {
		return fmt.Errorf("agent_decision: input_summary is required")
	}
	if p.OutputAction == "" {
		return fmt.Errorf("agent_decision: output_action is required")
	}
	if p.Confidence < 0 || p.Confidence > 1 {
		return fmt.Errorf("agent_decision: confidence must be 0-1, got %f", p.Confidence)
	}
	return nil
}
