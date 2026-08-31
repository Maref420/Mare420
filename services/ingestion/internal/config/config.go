// MODULE: atlas-ws-ingestion
// GOVERNANCE: Matrix B - Go Network/Transfer Layer
// ADR: docs/decisions/006-websocket-ingestion-architecture.md
// SPEC: contracts/schemas/ipc-binary-v1.spec.yaml
// WARNING: All env vars MUST be validated at startup. Missing vars = explicit failure.

package config

import (
	"fmt"
	"os"
	"strconv"
	"time"
)

type Config struct {
	WSURI                string
	WSAuthToken          string
	ReconnectMaxRetries  int
	ReconnectBaseDelayMs int
	HeartbeatIntervalMs  int
	IPCSocketPath        string
}

func Load() (*Config, error) {
	wsURI := os.Getenv("WS_URI")
	if wsURI == "" {
		return nil, fmt.Errorf("WS_URI environment variable is required but not set")
	}

	ipcPath := os.Getenv("WS_IPC_SOCKET_PATH")
	if ipcPath == "" {
		return nil, fmt.Errorf("WS_IPC_SOCKET_PATH environment variable is required but not set")
	}

	authToken := os.Getenv("WS_AUTH_TOKEN")
	if authToken == "" {
		return nil, fmt.Errorf("WS_AUTH_TOKEN environment variable is required but not set")
	}

	maxRetries, err := getEnvInt("WS_RECONNECT_MAX_RETRIES", 10)
	if err != nil {
		return nil, fmt.Errorf("WS_RECONNECT_MAX_RETRIES: %w", err)
	}

	baseDelay, err := getEnvInt("WS_RECONNECT_BASE_DELAY_MS", 1000)
	if err != nil {
		return nil, fmt.Errorf("WS_RECONNECT_BASE_DELAY_MS: %w", err)
	}

	heartbeat, err := getEnvInt("WS_HEARTBEAT_INTERVAL_MS", 30000)
	if err != nil {
		return nil, fmt.Errorf("WS_HEARTBEAT_INTERVAL_MS: %w", err)
	}

	return &Config{
		WSURI:                wsURI,
		WSAuthToken:          authToken,
		ReconnectMaxRetries:  maxRetries,
		ReconnectBaseDelayMs: baseDelay,
		HeartbeatIntervalMs:  heartbeat,
		IPCSocketPath:        ipcPath,
	}, nil
}

func (c *Config) HeartbeatInterval() time.Duration {
	return time.Duration(c.HeartbeatIntervalMs) * time.Millisecond
}

func (c *Config) ReconnectBaseDelay() time.Duration {
	return time.Duration(c.ReconnectBaseDelayMs) * time.Millisecond
}

func getEnvInt(key string, defaultVal int) (int, error) {
	val := os.Getenv(key)
	if val == "" {
		return defaultVal, nil
	}
	n, err := strconv.Atoi(val)
	if err != nil {
		return 0, fmt.Errorf("invalid integer value %q for %s: %w", val, key, err)
	}
	if n < 0 {
		return 0, fmt.Errorf("%s must be non-negative, got %d", key, n)
	}
	return n, nil
}
