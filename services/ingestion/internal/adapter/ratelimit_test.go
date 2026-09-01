// MODULE: atlas-ws-ingestion
// GOVERNANCE: Rate limiter tests per CR-P0-004 v3 Section D1

package adapter

import (
	"context"
	"testing"
	"time"
)

func TestRateLimiter_Allow_BurstCapacity(t *testing.T) {
	rl := NewRateLimiter(5, 10)
	allowed := 0
	for i := 0; i < 10; i++ {
		if rl.Allow() {
			allowed++
		}
	}
	if allowed != 5 {
		t.Fatalf("expected 5 allowed (burst), got %d", allowed)
	}
}

func TestRateLimiter_Allow_Refill(t *testing.T) {
	rl := NewRateLimiter(2, 100) // 100/sec = 1 per 10ms
	// Drain burst
	rl.Allow()
	rl.Allow()
	// Should be denied
	if rl.Allow() {
		t.Fatal("expected denial after burst drained")
	}
	// Wait for refill
	time.Sleep(25 * time.Millisecond)
	if !rl.Allow() {
		t.Fatal("expected allow after refill period")
	}
}

func TestRateLimiter_Wait_ContextCancel(t *testing.T) {
	rl := NewRateLimiter(1, 0.1) // Very slow refill
	rl.Allow()                     // Drain

	ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
	defer cancel()

	err := rl.Wait(ctx)
	if err == nil {
		t.Fatal("expected context timeout error")
	}
}

func TestRateLimiter_Wait_Success(t *testing.T) {
	rl := NewRateLimiter(1, 100) // Fast refill
	rl.Allow()                     // Drain

	ctx, cancel := context.WithTimeout(context.Background(), 1*time.Second)
	defer cancel()

	err := rl.Wait(ctx)
	if err != nil {
		t.Fatalf("expected success, got: %v", err)
	}
}
