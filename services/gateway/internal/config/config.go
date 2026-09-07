// MODULE: atlas-gateway
// GOVERNANCE: Matrix B - Go Network/Transfer Layer
// CONTRACT: Typed config from env only. No secrets in source.
package config

import (
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"
)

type CustomerConfig struct {
	Name           string `json:"name"`
	APIKey         string `json:"api_key"`
	MaxFPS         int    `json:"max_fps"`
	MaxConnections int    `json:"max_connections"`
}

type Config struct {
	Port            int
	MetricsPort     int
	APIKeys         map[string]CustomerConfig
	ShutdownTimeout time.Duration
}

func Load() (*Config, error) {
	port := 8443
	if s := os.Getenv("ATLAS_GATEWAY_PORT"); s != "" {
		p, err := strconv.Atoi(s)
		if err != nil {
			return nil, fmt.Errorf("invalid ATLAS_GATEWAY_PORT: %w", err)
		}
		port = p
	}

	metricsPort := 9091
	if s := os.Getenv("ATLAS_GATEWAY_METRICS_PORT"); s != "" {
		mp, err := strconv.Atoi(s)
		if err != nil {
			return nil, fmt.Errorf("invalid ATLAS_GATEWAY_METRICS_PORT: %w", err)
		}
		metricsPort = mp
	}

	apiKeys := make(map[string]CustomerConfig)
	if env := os.Getenv("ATLAS_GATEWAY_API_KEYS"); env != "" {
		for _, entry := range strings.Split(env, ",") {
			parts := strings.SplitN(entry, ":", 3)
			if len(parts) != 3 {
				return nil, fmt.Errorf("invalid api key format: %q (expected name:key:max_fps)", entry)
			}
			fps, err := strconv.Atoi(parts[2])
			if err != nil {
				return nil, fmt.Errorf("invalid max_fps in %q: %w", entry, err)
			}
			cfg := CustomerConfig{
				Name:           parts[0],
				APIKey:         parts[1],
				MaxFPS:         fps,
				MaxConnections: 50,
			}
			apiKeys[cfg.APIKey] = cfg
		}
	}

	return &Config{
		Port:            port,
		MetricsPort:     metricsPort,
		APIKeys:         apiKeys,
		ShutdownTimeout: 10 * time.Second,
	}, nil
}
