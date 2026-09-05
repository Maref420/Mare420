package transport

// Transport abstracts message delivery mechanism.
// Implementations must be safe for concurrent use.
// Swap channel → NATS by adding new implementation, no core changes.
type Transport interface {
	Publish(topic string, data []byte) error
	Subscribe(topic string, handler func([]byte) error) error
	Close() error
}
