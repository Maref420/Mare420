// MODULE: atlas-memory-store
// GOVERNANCE: Matrix A - Rust Compute Layer
// CONTRACT: Governed memory store per ADR-006 Phase 2.
pub mod node;
pub mod graph;
pub mod persist;

pub use graph::{MemoryGraph, MemoryStats};
pub use node::{MemoryEdge, MemoryError, MemoryNode};
pub use persist::{BackgroundScheduler, PersistConfig};
