package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"sync"
	"time"
)

var ErrInvalidEnvelope = errors.New("invalid envelope structure")
var ErrInvalidPayload = errors.New("invalid payload schema")
var ErrTimeout = errors.New("operation timed out")
var ErrBufferFull = errors.New("buffer full, message dropped")
var ErrNATSDisconnected = errors.New("nats connection lost")

type ValidatedMessage struct {
	Envelope         []byte
	Payload          []byte
	ReceiveTimestamp time.Time
	RoutingPath      string
}

type Validator struct {
	maxTimeout int64
}

func NewValidator(maxTimeoutMs int64) *Validator {
	if maxTimeoutMs <= 0 {
		maxTimeoutMs = 5000
	}
	return &Validator{maxTimeout: maxTimeoutMs}
}

func (v *Validator) Validate(ctx context.Context, envelope []byte) (*ValidatedMessage, error) {
	if ctx == nil {
		ctx = context.Background()
	}
	deadline, ok := ctx.Deadline()
	if ok {
		remaining := time.Until(deadline)
		if remaining <= 0 {
			return nil, ErrTimeout
		}
	}
	if v.maxTimeout > 0 {
		timeoutCtx, cancel := context.WithTimeout(ctx, time.Duration(v.maxTimeout)*time.Millisecond)
		defer cancel()
		ctx = timeoutCtx
	}
	var env struct {
		Version string `json:"version"`
		Payload []byte `json:"payload"`
	}
	if err := json.Unmarshal(envelope, &env); err != nil {
		return nil, fmt.Errorf("%w: %v", ErrInvalidEnvelope, err)
	}
	if env.Version != "engine-contract-v1" {
		return nil, fmt.Errorf("%w: unsupported version %s", ErrInvalidEnvelope, env.Version)
	}
	if len(env.Payload) == 0 {
		return nil, fmt.Errorf("%w: empty payload", ErrInvalidPayload)
	}
	var payload struct {
		Type string `json:"type"`
	}
	if err := json.Unmarshal(env.Payload, &payload); err != nil {
		return nil, fmt.Errorf("%w: %v", ErrInvalidPayload, err)
	}

	var routingPath string
	switch payload.Type {
	case "strategy-signal-event-v1":
		routingPath = "atlas.strategy.signal.v1"
	case "decision-proposal-v1":
		routingPath = "atlas.control.decision.v1"
	default:
		return nil, fmt.Errorf("%w: unsupported payload type %s", ErrInvalidPayload, payload.Type)
	}

	select {
	case <-ctx.Done():
		return nil, ErrTimeout
	default:
	}
	return &ValidatedMessage{
		Envelope:         envelope,
		Payload:          env.Payload,
		ReceiveTimestamp: time.Now(),
		RoutingPath:      routingPath,
	}, nil
}

type Buffer struct {
	mu       sync.Mutex
	messages []*ValidatedMessage
	maxSize  int
}

func NewBuffer(maxSize int) *Buffer {
	if maxSize <= 0 {
		maxSize = 1000
	}
	return &Buffer{
		messages: make([]*ValidatedMessage, 0, maxSize),
		maxSize:  maxSize,
	}
}

func (b *Buffer) Add(msg *ValidatedMessage) error {
	if msg == nil {
		return errors.New("nil message")
	}
	b.mu.Lock()
	defer b.mu.Unlock()
	if len(b.messages) >= b.maxSize {
		b.messages = b.messages[1:]
	}
	b.messages = append(b.messages, msg)
	return nil
}

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

func (b *Buffer) Len() int {
	b.mu.Lock()
	defer b.mu.Unlock()
	return len(b.messages)
}

type Router struct {
	mu          sync.Mutex
	buffer      *Buffer
	natsPublish func(ctx context.Context, topic string, data []byte) error
}

func NewRouter(natsPublish func(ctx context.Context, topic string, data []byte) error) *Router {
	return &Router{
		buffer:      NewBuffer(1000),
		natsPublish: natsPublish,
	}
}

func (r *Router) Route(ctx context.Context, msg *ValidatedMessage) error {
	if ctx == nil {
		ctx = context.Background()
	}
	if msg == nil {
		return errors.New("nil message")
	}
	r.mu.Lock()
	defer r.mu.Unlock()
	if r.natsPublish != nil {
		err := r.natsPublish(ctx, msg.RoutingPath, msg.Envelope)
		if err == nil {
			return nil
		}
		if errors.Is(err, context.DeadlineExceeded) || errors.Is(err, context.Canceled) {
			return ErrTimeout
		}
		if bufErr := r.buffer.Add(msg); bufErr != nil {
			return bufErr
		}
		return nil
	}
	if bufErr := r.buffer.Add(msg); bufErr != nil {
		return bufErr
	}
	return nil
}

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
			_ = r.buffer.Add(msg)
			continue
		}
		err := r.natsPublish(ctx, msg.RoutingPath, msg.Envelope)
		if err != nil {
			lastErr = err
			_ = r.buffer.Add(msg)
		}
	}
	return lastErr
}
