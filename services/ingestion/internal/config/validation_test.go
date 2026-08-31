// MODULE: atlas-ws-ingestion
// GOVERNANCE: Config validation - missing env vars must cause explicit startup failure

package config

import (
	"os"
	"testing"
)

func TestMissingWSURI_FailsExplicitly(t *testing.T) {
	os.Unsetenv("WS_URI")
	_, err := Load()
	if err == nil {
		t.Fatal("expected explicit error when WS_URI is missing, got nil")
	}
}

func TestMissingIPCPath_FailsExplicitly(t *testing.T) {
	os.Setenv("WS_URI", "wss://example.com/ws")
	os.Unsetenv("WS_IPC_SOCKET_PATH")
	_, err := Load()
	if err == nil {
		t.Fatal("expected explicit error when WS_IPC_SOCKET_PATH is missing, got nil")
	}
}
