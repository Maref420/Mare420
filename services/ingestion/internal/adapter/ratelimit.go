// MODULE: atlas-ws-ingestion
// GOVERNANCE: Rate limiting per CR-P0-004 v3 Section D1
// DESIGN: Token bucket algorithm, per-adapter, no external dependencies
// WARNING: Rate limits are exchange-specific. Each adapter configures its own.

package adapter

import (
	"context"
	"sync"
	"time"
)

// RateLimiter implements a token bucket rate limiter.
// Thread-safe. Zero-value is NOT usable; use NewRateLimiter.
type RateLimiter struct {
	mu         sync.Mutex
	tokens     float64
	maxTokens  float64
	refillRate float64 // tokens per second
	lastRefill time.Time
}

// NewRateLimiter creates a rate limiter.
// maxTokens: burst capacity
// refillPerSec: sustained rate (tokens/second)
func NewRateLimiter(maxTokens float64, refillPerSec float64) *RateLimiter {
	return &RateLimiter{
		tokens:     maxTokens,
		maxTokens:  maxTokens,
		refillRate: refillPerSec,
		lastRefill: time.Now(),
	}
}

// Allow checks if one token is available. Returns true if allowed.
// Non-blocking: returns immediately.
func (rl *RateLimiter) Allow() bool {
	rl.mu.Lock()
	defer rl.mu.Unlock()

	now := time.Now()
	elapsed := now.Sub(rl.lastRefill).Seconds()
	rl.tokens += elapsed * rl.refillRate
	if rl.tokens > rl.maxTokens {
		rl.tokens = rl.maxTokens
	}
	rl.lastRefill = now

	if rl.tokens >= 1.0 {
		rl.tokens -= 1.0
		return true
	}
	return false
}

// Wait blocks until a token is available or context is cancelled.
func (rl *RateLimiter) Wait(ctx context.Context) error {
	for {
		if rl.Allow() {
			return nil
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(10 * time.Millisecond):
		}
	}
}
