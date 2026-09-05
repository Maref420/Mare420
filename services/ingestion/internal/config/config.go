// MODULE: atlas-ws-ingestion
// GOVERNANCE: Matrix B - Go Network/Transfer Layer
// ADR: docs/decisions/006-websocket-ingestion-architecture.md
// SPEC: contracts/schemas/ipc-binary-v1.spec.yaml v1.1
// WARNING: All env vars MUST be validated at startup. Missing required vars = explicit failure.
// TRACE: Per CR-P0-004 Section H, trace propagation is mandatory for all frames.

package config

import (
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"
)

// ExchangeConfig holds per-exchange WebSocket configuration.
type ExchangeConfig struct {
	Name      string   // "bybit", "okx", etc.
	WSURI     string   // WebSocket endpoint URL
	Symbols   []string // e.g., ["BTCUSDT", "ETHUSDT"]
	Testnet   bool     // true for testnet endpoints
	APIKey    string   // optional: only needed for private streams
	APISecret string   // optional: only needed for private streams
}

// Config holds all runtime configuration for ws-ingestion service.
type Config struct {
	Exchanges            []ExchangeConfig
	IPCSocketPath        string
	ReconnectMaxRetries  int
	ReconnectBaseDelayMs int
	HeartbeatIntervalMs  int
	MetricsPort          string
	LogLevel             string
}

// Load reads and validates all configuration from environment variables.
// Required vars cause explicit startup failure if missing.
// Optional vars have sensible defaults.
func Load() (*Config, error) {
	ipcPath := os.Getenv("WS_IPC_SOCKET_PATH")
	if ipcPath == "" {
		return nil, fmt.Errorf("WS_IPC_SOCKET_PATH environment variable is required but not set")
	}

	exchanges, err := loadExchanges()
	if err != nil {
		return nil, fmt.Errorf("exchange configuration: %w", err)
	}

	if len(exchanges) == 0 {
		return nil, fmt.Errorf("at least one exchange must be configured via WS_EXCHANGES env var")
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

	metricsPort := os.Getenv("METRICS_PORT")
	if metricsPort == "" {
		metricsPort = "9090"
	}

	logLevel := os.Getenv("LOG_LEVEL")
	if logLevel == "" {
		logLevel = "info"
	}

	return &Config{
		Exchanges:            exchanges,
		IPCSocketPath:        ipcPath,
		ReconnectMaxRetries:  maxRetries,
		ReconnectBaseDelayMs: baseDelay,
		HeartbeatIntervalMs:  heartbeat,
		MetricsPort:          metricsPort,
		LogLevel:             logLevel,
	}, nil
}

// loadExchanges parses WS_EXCHANGES env var.
// Format: "bybit:wss://stream-testnet.bybit.com/v5/public/spot:BTCUSDT,ETHUSDT:testnet;okx:wss://ws.okx.com:8443/ws/v5/public:BTC-USDT:mainnet"
// Each exchange separated by semicolon.
// Fields per exchange: name:uri:symbols:mode (mode = "testnet" or "mainnet")
// API key/secret loaded from BYBIT_API_KEY/BYBIT_API_SECRET or OKX_API_KEY/OKX_API_SECRET per exchange.
func loadExchanges() ([]ExchangeConfig, error) {
	raw := os.Getenv("WS_EXCHANGES")
	if raw == "" {
		return nil, fmt.Errorf("WS_EXCHANGES environment variable is required but not set")
	}

	var exchanges []ExchangeConfig

	for _, entry := range strings.Split(raw, ";") {
		entry = strings.TrimSpace(entry)
		if entry == "" {
			continue
		}

		parts := strings.SplitN(entry, ":", 4)
		if len(parts) < 3 {
			return nil, fmt.Errorf("invalid exchange entry %q: expected format name:uri:symbols[:mode]", entry)
		}

		name := strings.TrimSpace(parts[0])
		uri := strings.TrimSpace(parts[1])
		symbolsRaw := strings.TrimSpace(parts[2])
		mode := "mainnet"
		if len(parts) >= 4 {
			mode = strings.TrimSpace(parts[3])
		}

		if name == "" || uri == "" || symbolsRaw == "" {
			return nil, fmt.Errorf("exchange entry %q has empty required fields", entry)
		}

		var symbols []string
		for _, s := range strings.Split(symbolsRaw, ",") {
			s = strings.TrimSpace(s)
			if s != "" {
				symbols = append(symbols, s)
			}
		}

		if len(symbols) == 0 {
			return nil, fmt.Errorf("exchange %q has no symbols configured", name)
		}

		testnet := strings.EqualFold(mode, "testnet")

		// Load per-exchange credentials (optional for public streams)
		apiKey := os.Getenv(strings.ToUpper(name) + "_API_KEY")
		apiSecret := os.Getenv(strings.ToUpper(name) + "_API_SECRET")

		exchanges = append(exchanges, ExchangeConfig{
			Name:      name,
			WSURI:     uri,
			Symbols:   symbols,
			Testnet:   testnet,
			APIKey:    apiKey,
			APISecret: apiSecret,
		})
	}

	return exchanges, nil
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
