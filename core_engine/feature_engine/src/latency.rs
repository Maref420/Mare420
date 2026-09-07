// MODULE: atlas-feature-engine
// GOVERNANCE: Matrix A - Rust Compute Layer
use std::collections::VecDeque;

/// Tracks inter-arrival latency and computes variance.
#[derive(Debug, Clone)]
pub struct LatencyTracker {
    timestamps: VecDeque<u64>,
    max_samples: usize,
}

impl LatencyTracker {
    pub fn new(max_samples: usize) -> Self {
        Self {
            timestamps: VecDeque::with_capacity(max_samples),
            max_samples,
        }
    }

    pub fn record(&mut self, timestamp_ns: u64) {
        if self.timestamps.len() >= self.max_samples {
            self.timestamps.pop_front();
        }
        self.timestamps.push_back(timestamp_ns);
    }

    /// Returns variance of inter-arrival times in milliseconds.
    pub fn variance_ms(&self) -> f64 {
        if self.timestamps.len() < 2 {
            return 0.0;
        }
        let intervals: Vec<f64> = self.timestamps
            .iter()
            .zip(self.timestamps.iter().skip(1))
            .map(|(a, b)| (*b as f64 - *a as f64) / 1_000_000.0)
            .collect();

        let n = intervals.len() as f64;
        let mean: f64 = intervals.iter().sum::<f64>() / n;
        let variance: f64 = intervals.iter().map(|x| (x - mean).powi(2)).sum::<f64>() / n;
        variance
    }

    /// Returns mean inter-arrival time in milliseconds.
    pub fn mean_latency_ms(&self) -> f64 {
        if self.timestamps.len() < 2 {
            return 0.0;
        }
        let first = *self.timestamps.front().unwrap_or(&0);
        let last = *self.timestamps.back().unwrap_or(&0);
        let count = (self.timestamps.len() - 1) as f64;
        if count == 0.0 {
            return 0.0;
        }
        (last as f64 - first as f64) / 1_000_000.0 / count
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_constant_interval_zero_variance() {
        let mut tracker = LatencyTracker::new(100);
        for i in 0..10 {
            tracker.record(i * 1_000_000); // 1ms apart
        }
        assert!(tracker.variance_ms() < 1e-9);
    }

    #[test]
    fn test_variable_interval() {
        let mut tracker = LatencyTracker::new(100);
        tracker.record(0);
        tracker.record(1_000_000);  // 1ms
        tracker.record(5_000_000);  // 4ms
        assert!(tracker.variance_ms() > 0.0);
    }

    #[test]
    fn test_single_sample() {
        let mut tracker = LatencyTracker::new(100);
        tracker.record(1000);
        assert_eq!(tracker.variance_ms(), 0.0);
        assert_eq!(tracker.mean_latency_ms(), 0.0);
    }

    #[test]
    fn test_max_samples_eviction() {
        let mut tracker = LatencyTracker::new(5);
        for i in 0..10 {
            tracker.record(i * 1_000_000);
        }
        assert_eq!(tracker.timestamps.len(), 5);
    }
}
