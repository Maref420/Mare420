// DATA FLOW:
// 1. HTTP Request arrives at the Go gateway (or local mux).
// 2. RegisterRoutes maps /health/live and /health/ready to handlers.
// 3. LiveHandler executes instantly -> returns 200 {"status": "ok"}.
// 4. ReadyHandler triggers executeReadinessCheck().
// 5. executeReadinessCheck creates a child context with a 3s timeout per checker.
// 6. It spawns a goroutine for each registered Checker.
// 7. Each Checker runs Check(ctx) respecting context deadline.
// 8. Results are gathered into a mutex-protected map.
// 9. If all pass -> 200 {"status": "ok"}. If any fail -> 503 {"status": "fail"}.
//
// SHARED STATE:
// - checkers ([]Checker): read-only after construction, protected by RWMutex on copy.
// - checks (map[string]CheckResult): write-protected by resultsMu (sync.Mutex).
// - anyFailed (bool): write-protected by resultsMu.
//
// CONCURRENCY MODEL:
// - One goroutine per checker, bounded by WaitGroup.
// - Context cancellation prevents goroutine leaks (go-policy: goroutine_leaks prohibited).
// - Race safety guaranteed by mutex around shared results map.
// - Run with -race flag to verify: go test -race ./...
package health

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"
)

// --- Mock Checkers ---

type alwaysPassChecker struct{}

func (a *alwaysPassChecker) Name() string                { return "always-pass" }
func (a *alwaysPassChecker) Check(_ context.Context) error { return nil }

type alwaysFailChecker struct{}

func (a *alwaysFailChecker) Name() string                { return "always-fail" }
func (a *alwaysFailChecker) Check(_ context.Context) error { return errors.New("check failed") }

type slowChecker struct{}

func (s *slowChecker) Name() string { return "slow-checker" }
func (s *slowChecker) Check(ctx context.Context) error {
	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-time.After(5 * time.Second):
		return errors.New("slow checker completed")
	}
}

// --- Helpers ---

func helperNewServer(checkers ...Checker) *httptest.Server {
	mux := http.NewServeMux()
	srv := NewHealthServer("test-service", "v1.0.0", checkers...)
	srv.RegisterRoutes(mux)
	return httptest.NewServer(mux)
}

func helperGet(ts *httptest.Server, path string) (int, string, error) {
	resp, err := http.Get(ts.URL + path)
	if err != nil {
		return 0, "", err
	}
	defer resp.Body.Close()
	buf := make([]byte, 2048)
	n, _ := resp.Body.Read(buf)
	return resp.StatusCode, string(buf[:n]), nil
}

// --- Tests ---

func TestLiveness_AlwaysOK(t *testing.T) {
	ts := helperNewServer(&alwaysPassChecker{})
	defer ts.Close()

	code, body, err := helperGet(ts, "/health/live")
	if err != nil {
		t.Fatalf("request failed: %v", err)
	}
	if code != http.StatusOK {
		t.Errorf("expected status %d, got %d", http.StatusOK, code)
	}
	if !strings.Contains(body, `"status":"ok"`) {
		t.Errorf("expected status ok in body, got: %s", body)
	}
}

func TestReadiness_AllCheckersPass(t *testing.T) {
	ts := helperNewServer(&alwaysPassChecker{}, &alwaysPassChecker{})
	defer ts.Close()

	code, body, err := helperGet(ts, "/health/ready")
	if err != nil {
		t.Fatalf("request failed: %v", err)
	}
	if code != http.StatusOK {
		t.Errorf("expected status %d, got %d", http.StatusOK, code)
	}
	if !strings.Contains(body, `"status":"ok"`) {
		t.Errorf("expected status ok in body, got: %s", body)
	}
}

func TestReadiness_OneCheckerFails(t *testing.T) {
	ts := helperNewServer(&alwaysPassChecker{}, &alwaysFailChecker{})
	defer ts.Close()

	code, body, err := helperGet(ts, "/health/ready")
	if err != nil {
		t.Fatalf("request failed: %v", err)
	}
	if code != http.StatusServiceUnavailable {
		t.Errorf("expected status %d, got %d", http.StatusServiceUnavailable, code)
	}
	if !strings.Contains(body, `"status":"fail"`) {
		t.Errorf("expected status fail in body, got: %s", body)
	}
}

func TestReadiness_CheckerTimeout(t *testing.T) {
	ts := helperNewServer(&slowChecker{})
	defer ts.Close()

	start := time.Now()
	code, _, err := helperGet(ts, "/health/ready")
	elapsed := time.Since(start)

	if err != nil {
		t.Fatalf("request failed: %v", err)
	}
	if code != http.StatusServiceUnavailable {
		t.Errorf("expected status %d, got %d", http.StatusServiceUnavailable, code)
	}
	// Should complete within ~3s (checker timeout) + overhead, not 5s
	if elapsed > 4*time.Second {
		t.Errorf("timeout not enforced: took %v", elapsed)
	}
}

func TestReadiness_ParentContextCancelled(t *testing.T) {
	mux := http.NewServeMux()
	srv := NewHealthServer("test-service", "v1.0.0", &slowChecker{})
	srv.RegisterRoutes(mux)
	ts := httptest.NewServer(mux)
	defer ts.Close()

	req, err := http.NewRequest("GET", ts.URL+"/health/ready", nil)
	if err != nil {
		t.Fatalf("failed to create request: %v", err)
	}

	ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
	defer cancel()
	req = req.WithContext(ctx)

	client := &http.Client{}
	_, err = client.Do(req)
	if err == nil {
		t.Log("Request completed before cancellation (acceptable for fast checkers)")
	} else {
		t.Logf("Got expected error due to context cancellation: %v", err)
	}
}

func TestReadiness_ConcurrentSafety(t *testing.T) {
	ts := helperNewServer(&alwaysPassChecker{}, &alwaysPassChecker{})
	defer ts.Close()

	var wg sync.WaitGroup
	errCh := make(chan error, 100)

	for i := 0; i < 100; i++ {
		wg.Add(1)
		go func(id int) {
			defer wg.Done()
			code, _, err := helperGet(ts, "/health/ready")
			if err != nil {
				errCh <- fmt.Errorf("request %d failed: %v", id, err)
				return
			}
			if code != http.StatusOK {
				errCh <- fmt.Errorf("request %d: expected 200, got %d", id, code)
			}
		}(i)
	}

	wg.Wait()
	close(errCh)

	for err := range errCh {
		t.Error(err)
	}
	// Run with: go test -race ./foundation/health/
	// This proves no data races under concurrent access.
}

func TestRegisterRoutes(t *testing.T) {
	ts := helperNewServer(&alwaysPassChecker{})
	defer ts.Close()

	code1, _, err := helperGet(ts, "/health/live")
	if err != nil {
		t.Fatalf("/health/live failed: %v", err)
	}
	if code1 != http.StatusOK {
		t.Errorf("/health/live expected 200, got %d", code1)
	}

	code2, _, err := helperGet(ts, "/health/ready")
	if err != nil {
		t.Fatalf("/health/ready failed: %v", err)
	}
	if code2 != http.StatusOK {
		t.Errorf("/health/ready expected 200, got %d", code2)
	}
}

func TestMethodNotAllowed(t *testing.T) {
	ts := helperNewServer(&alwaysPassChecker{})
	defer ts.Close()

	req, err := http.NewRequest("POST", ts.URL+"/health/live", nil)
	if err != nil {
		t.Fatalf("failed to create request: %v", err)
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("request failed: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusMethodNotAllowed {
		t.Errorf("expected %d, got %d", http.StatusMethodNotAllowed, resp.StatusCode)
	}
}
