// Minimal envelope validation CLI for cross-language E2E testing.
// Reads JSON from stdin, validates via envelope.Validate(), exits 0 or 1.
package main

import (
	"fmt"
	"io"
	"os"

	"atlas.ai/message-broker/internal/envelope"
)

func main() {
	data, err := io.ReadAll(os.Stdin)
	if err != nil {
		fmt.Fprintf(os.Stderr, "read error: %v\n", err)
		os.Exit(2)
	}
	_, err = envelope.Validate(data)
	if err != nil {
		fmt.Fprintf(os.Stderr, "%v\n", err)
		os.Exit(1)
	}
	os.Exit(0)
}
