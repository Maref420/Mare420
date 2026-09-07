// MODULE: atlas-memory-store
// GOVERNANCE: Matrix A - Rust Compute Layer
// CONTRACT: File-based JSON persistence for MemoryGraph state.
// WARNING: No unwrap/expect/panic on production path. All I/O via Result.
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::{Arc, RwLock};
use std::thread;
use std::time::Duration;

use crate::graph::MemoryGraph;
use crate::node::MemoryError;

#[derive(Debug, Clone)]
pub struct PersistConfig {
    pub data_dir: PathBuf,
    pub filename: String,
    pub auto_save_interval_secs: u64,
}

impl Default for PersistConfig {
    fn default() -> Self {
        Self {
            data_dir: PathBuf::from("data"),
            filename: "memory_store.json".into(),
            auto_save_interval_secs: 60,
        }
    }
}

impl PersistConfig {
    pub fn full_path(&self) -> PathBuf {
        self.data_dir.join(&self.filename)
    }
}

pub fn save_state(graph: &MemoryGraph, config: &PersistConfig) -> Result<(), MemoryError> {
    let data = graph.export_state()?;
    let path = config.full_path();

    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|e| {
            MemoryError::StoreUnavailable(format!("create dir {}: {}", parent.display(), e))
        })?;
    }

    let tmp_path = path.with_extension("json.tmp");
    fs::write(&tmp_path, &data).map_err(|e| {
        MemoryError::StoreUnavailable(format!("write temp {}: {}", tmp_path.display(), e))
    })?;

    fs::rename(&tmp_path, &path).map_err(|e| {
        MemoryError::StoreUnavailable(format!("rename {}: {}", path.display(), e))
    })?;

    Ok(())
}

pub fn load_state(graph: &MemoryGraph, config: &PersistConfig) -> Result<bool, MemoryError> {
    let path = config.full_path();

    if !Path::new(&path).exists() {
        return Ok(false);
    }

    let data = fs::read(&path).map_err(|e| {
        MemoryError::StoreUnavailable(format!("read {}: {}", path.display(), e))
    })?;

    if data.is_empty() {
        return Ok(false);
    }

    graph.import_state(&data)?;
    Ok(true)
}

pub struct BackgroundScheduler {
    stop_flag: Arc<RwLock<bool>>,
    handle: Option<thread::JoinHandle<()>>,
}

impl BackgroundScheduler {
    pub fn start(
        graph: Arc<MemoryGraph>,
        config: PersistConfig,
    ) -> Result<Self, MemoryError> {
        let stop_flag = Arc::new(RwLock::new(false));
        let flag_clone = stop_flag.clone();

        let handle = thread::Builder::new()
            .name("memory-scheduler".into())
            .spawn(move || {
                let interval = Duration::from_secs(config.auto_save_interval_secs);
                loop {
                    {
                        let stopped = flag_clone.read()
                            .map(|f| *f)
                            .unwrap_or(true);
                        if stopped {
                            break;
                        }
                    }

                    thread::sleep(interval);

                    {
                        let stopped = flag_clone.read()
                            .map(|f| *f)
                            .unwrap_or(true);
                        if stopped {
                            break;
                        }
                    }

                    let now_ns = std::time::SystemTime::now()
                        .duration_since(std::time::UNIX_EPOCH)
                        .map(|d| d.as_nanos() as u64)
                        .unwrap_or(0);

                    match graph.evict_expired(now_ns) {
                        Ok(evicted) => {
                            if evicted > 0 {
                                eprintln!("memory_scheduler: evicted {} stale nodes", evicted);
                            }
                        }
                        Err(e) => {
                            eprintln!("memory_scheduler: eviction error: {}", e);
                        }
                    }

                    match save_state(&graph, &config) {
                        Ok(()) => {}
                        Err(e) => {
                            eprintln!("memory_scheduler: save error: {}", e);
                        }
                    }
                }
            })
            .map_err(|e| MemoryError::InternalError(format!("spawn scheduler: {}", e)))?;

        Ok(Self {
            stop_flag,
            handle: Some(handle),
        })
    }

    pub fn stop(&mut self) {
        if let Ok(mut flag) = self.stop_flag.write() {
            *flag = true;
        }
        if let Some(handle) = self.handle.take() {
            let _ = handle.join();
        }
    }
}

impl Drop for BackgroundScheduler {
    fn drop(&mut self) {
        self.stop();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::node::MemoryNode;
    use std::collections::HashMap;
    use std::env;

    fn test_config() -> PersistConfig {
        let dir = env::temp_dir().join("atlas_mem_test");
        PersistConfig {
            data_dir: dir,
            filename: "test_memory.json".into(),
            auto_save_interval_secs: 1,
        }
    }

    fn cleanup(config: &PersistConfig) {
        let path = config.full_path();
        let _ = fs::remove_file(&path);
        let tmp = path.with_extension("json.tmp");
        let _ = fs::remove_file(tmp);
        let _ = fs::remove_dir(&config.data_dir);
    }

    #[test]
    fn test_save_and_load() {
        let config = test_config();
        let graph = MemoryGraph::new();
        let node = MemoryNode {
            node_id: "n1".into(), entity_type: "test".into(),
            attributes: HashMap::new(), source_uri: "t://v1".into(),
            agent_id: "a1".into(), ttl_ns: 0,
            created_at_ns: 1, updated_at_ns: 1,
        };
        graph.write_node(node).unwrap();
        save_state(&graph, &config).unwrap();
        let graph2 = MemoryGraph::new();
        let loaded = load_state(&graph2, &config).unwrap();
        assert!(loaded);
        assert_eq!(graph2.node_count().unwrap(), 1);
        cleanup(&config);
    }

    #[test]
    fn test_load_nonexistent_returns_false() {
        let config = test_config();
        let graph = MemoryGraph::new();
        let loaded = load_state(&graph, &config).unwrap();
        assert!(!loaded);
    }

    #[test]
    fn test_background_scheduler_starts_and_stops() {
        let config = test_config();
        let graph = Arc::new(MemoryGraph::new());
        let mut scheduler = BackgroundScheduler::start(graph, config.clone()).unwrap();
        thread::sleep(Duration::from_millis(100));
        scheduler.stop();
        cleanup(&config);
    }

    #[test]
    fn test_atomic_write_creates_dir() {
        let config = PersistConfig {
            data_dir: env::temp_dir().join("atlas_mem_nested/deep/dir"),
            filename: "test.json".into(),
            auto_save_interval_secs: 60,
        };
        let graph = MemoryGraph::new();
        save_state(&graph, &config).unwrap();
        assert!(config.full_path().exists());
        let _ = fs::remove_file(config.full_path());
        let _ = fs::remove_dir_all(env::temp_dir().join("atlas_mem_nested"));
    }
}
