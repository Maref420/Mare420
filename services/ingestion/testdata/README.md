# Golden Datasets for WebSocket Ingestion

## Purpose
Recorded raw WebSocket frames from production-like sources for replay testing.

## Rules
- Files MUST contain raw frames exactly as received (no modification)
- Each file named: {exchange}_{symbol}_{date}.raw
- Accompanying metadata: {exchange}_{symbol}_{date}.meta.json
- NEVER commit credentials or auth tokens in golden datasets
- Add new datasets via ADR amendment

## Current Datasets
(none yet - add after first successful integration test)
