package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"sync"
	"time"
)

// ErrInvalidEnvelope indicates the envelope structure does not match engine-contract-v1.
var ErrInvalidEnvelope = errors.New("invalid envelope structure")

// ErrInvalidPayload indicates the payload does not match strategy-signal-event-v1.
var ErrInvalidPayload = errors.New("invalid payload schema")

// ErrTimeout indicates the operation exceeded the allowed time limit.
var ErrTimeout = errors.New("operation timed out")

// ErrBufferFull indicates the buffer is full and the message was dropped.
var ErrBufferFull = errors.New("buffer full, message dropped")

// ErrNATSDisconnected indicates the NATS connection is lost.
var ErrNATSDisconnected = errors.New("nats connection lost")

// ValidatedMessage represents a successfully validated message ready for routing.
type ValidatedMessage struct {
	// Envelope is the original envelope bytes, preserved byte-for-byte.
	Envelope []byte
	// Payload is the original payload bytes, preserved byte-for-byte.
	Payload []byte
	// ReceiveTimestamp is the time the message was received by the broker.
	ReceiveTimestamp time.Time
	// RoutingPath is the target NATS topic.
	RoutingPath string
}

// Validator validates message envelopes and payloads.
type Validator struct {
	// maxTimeout is the maximum allowed processing time in milliseconds.
	maxTimeout int64
}

// NewValidator creates a new Validator with the specified timeout in milliseconds.
func NewValidator(maxTimeoutMs int64) *Validator {
	if maxTimeoutMs <= 0 {
		maxTimeoutMs = 5000
	}
	return &Validator{
		maxTimeout: maxTimeoutMs,
	}
}

// Validate validates an incoming message envelope and payload.
// It returns a ValidatedMessage if successful, or an error if validation fails.
func (v *Validator) Validate(ctx context.Context, envelope []byte) (*ValidatedMessage, error) {
	if ctx == nil {
		ctx = context.Background()
	}

	// Check context deadline
	deadline, ok := ctx.Deadline()
	if ok {
		remaining := time.Until(deadline)
		if remaining <= 0 {
			return nil, ErrTimeout
		}
	}

	// Enforce max timeout
	if v.maxTimeout > 0 {
		timeoutCtx, cancel := context.WithTimeout(ctx, time.Duration(v.maxTimeout)*time.Millisecond)
		defer cancel()
		ctx = timeoutCtx
	}

	// Parse envelope
	var env struct {
		Version string `json:"version"`
		Payload []byte `json:"payload"`
	}

	if err := json.Unmarshal(envelope, &env); err != nil {
		return nil, fmt.Errorf("%w: %v", ErrInvalidEnvelope, err)
	}

	// Validate version
	if env.Version != "engine-contract-v1" {
		return nil, fmt.Errorf("%w: unsupported version %s", ErrInvalidEnvelope, env.Version)
	}

	// Validate payload presence
	if len(env.Payload) == 0 {
		return nil, fmt.Errorf("%w: empty payload", ErrInvalidPayload)
	}

	// Validate payload schema
	var payload struct {
		Type string `json:"type"`
	}
	if err := json.Unmarshal(env.Payload, &payload); err != nil {
		return nil, fmt.Errorf("%w: %v", ErrInvalidPayload, err)
	}

	if payload.Type != "strategy-signal-event-v1" {
		return nil, fmt.Errorf("%w: unsupported payload type %s", ErrInvalidPayload, payload.Type)
	}

	// Check if context was cancelled or timed out during validation
	select {
	case <-ctx.Done():
		return nil, ErrTimeout
	default:
	}

	return &ValidatedMessage{
		Envelope:         envelope,
		Payload:          env.Payload,
		ReceiveTimestamp: time.Now(),
		RoutingPath:      "atlas.strategy.signal.v1",
	}, nil
}

// Buffer stores messages when NATS is disconnected.
type Buffer struct {
	mu       sync.Mutex
	messages []*ValidatedMessage
	maxSize  int
}

// NewBuffer creates a new message buffer with the specified maximum size.
func NewBuffer(maxSize int) *Buffer {
	if maxSize <= 0 {
		maxSize = 1000
	}
	return &Buffer{
		messages: make([]*ValidatedMessage, 0, maxSize),
		maxSize:  maxSize,
	}
}

// Add adds a message to the buffer. If the buffer is full, the oldest message is dropped.
func (b *Buffer) Add(msg *ValidatedMessage) error {
	if msg == nil {
		return errors.New("nil message")
	}

	b.mu.Lock()
	defer b.mu.Unlock()

	if len(b.messages) >= b.maxSize {
		// Drop oldest message
		b.messages = b.messages[1:]
	}

	b.messages = append(b.messages, msg)
	return nil
}

// Drain removes and returns all messages from the buffer.
func (b *Buffer) Drain() []*ValidatedMessage {
	b.mu.Lock()
	defer b.mu.Unlock()

	if len(b.messages) == 0 {
		return nil
	}

	msgs := b.messages
	b.messages = make([]*ValidatedMessage, 0, b.maxSize)
	return msgs
}

// Len returns the current number of messages in the buffer.
func (b *Buffer) Len() int {
	b.mu.Lock()
	defer b.mu.Unlock()
	return len(b.messages)
}

// Router routes validated messages to NATS.
type Router struct {
	mu          sync.Mutex
	buffer      *Buffer
	natsPublish func(ctx context.Context, topic string, data []byte) error
}

// NewRouter creates a new Router with the specified NATS publish function.
func NewRouter(natsPublish func(ctx context.Context, topic string, data []byte) error) *Router {
	return &Router{
		buffer:      NewBuffer(1000),
		natsPublish: natsPublish,
	}
}

// Route routes a validated message to the NATS topic.
// If NATS is disconnected, the message is buffered.
func (r *Router) Route(ctx context.Context, msg *ValidatedMessage) error {
	if ctx == nil {
		ctx = context.Background()
	}

	if msg == nil {
		return errors.New("nil message")
	}

	r.mu.Lock()
	defer r.mu.Unlock()

	// Try to publish to NATS
	if r.natsPublish != nil {
		err := r.natsPublish(ctx, msg.RoutingPath, msg.Envelope)
		if err == nil {
			return nil
		}

		// If NATS publish fails, buffer the message
		if errors.Is(err, context.DeadlineExceeded) || errors.Is(err, context.Canceled) {
			return ErrTimeout
		}

		// Buffer the message
		if bufErr := r.buffer.Add(msg); bufErr != nil {
			return bufErr
		}
		return nil
	}

	// No NATS publisher configured, buffer the message
	if bufErr := r.buffer.Add(msg); bufErr != nil {
		return bufErr
	}
	return nil
}

// Flush drains the buffer and attempts to publish all buffered messages.
func (r *Router) Flush(ctx context.Context) error {
	if ctx == nil {
		ctx = context.Background()
	}

	r.mu.Lock()
	defer r.mu.Unlock()

	msgs := r.buffer.Drain()
	if len(msgs) == 0 {
		return nil
	}

	var lastErr error
	for _, msg := range msgs {
		if r.natsPublish == nil {
			// Re-buffer if no publisher
			_ = r.buffer.Add(msg)
			continue
		}

		err := r.natsPublish(ctx, msg.RoutingPath, msg.Envelope)
		if err != nil {
			lastErr = err
			// Re-buffer failed messages
			_ = r.buffer.Add(msg)
		}
	}

	return lastErr
}