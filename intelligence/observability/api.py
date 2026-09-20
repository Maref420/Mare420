"""
Atlas AI Observability API Server.
Provides REST endpoints for the commercial dashboard.
Governed by: C-G3-4 (Zero Dependencies Core - Lazy Import).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Lazy imports per C-G3-4: Never crash trading pipeline if FastAPI missing
try:
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import FileResponse, JSONResponse
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    FastAPI = Any  # type: ignore[assignment,misc]

from intelligence.observability.adapter import ReadOnlyAdapter

TEMPLATE_DIR = Path(__file__).parent / "templates"


def create_app() -> Any:
    """Factory function to create FastAPI application."""
    if not FASTAPI_AVAILABLE:
        raise RuntimeError(
            "FastAPI not installed. Run: pip install fastapi uvicorn"
        )

    app = FastAPI(
        title="Atlas AI Observability API",
        version="1.0.0",
        description="Read-only commercial dashboard API for Atlas AI Trading Intelligence Fabric.",
    )

    @app.get("/", include_in_schema=False)
    async def serve_dashboard() -> Any:
        """Serve the single-file SPA dashboard."""
        index_path = TEMPLATE_DIR / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path))
        return JSONResponse({"message": "Atlas AI Observability API Running"})

    @app.get("/api/v1/pipeline/health")
    async def pipeline_health() -> Any:
        """System health status for SLA proof."""
        return ReadOnlyAdapter.get_pipeline_health().model_dump(mode="json")

    @app.get("/api/v1/memory/stats")
    async def memory_stats() -> Any:
        """Memory tier statistics demonstrating learning capacity."""
        return ReadOnlyAdapter.get_memory_stats().model_dump(mode="json")

    @app.get("/api/v1/audit/recent")
    async def recent_audit(limit: int = 50) -> Any:
        """Recent audit events for compliance demonstration."""
        if limit < 1 or limit > 500:
            raise HTTPException(status_code=400, detail="limit must be 1-500")
        events = ReadOnlyAdapter.get_recent_audit_events(limit=limit)
        return [e.model_dump(mode="json") for e in events]

    @app.get("/api/v1/signals/cancelled")
    async def cancelled_signals(limit: int = 50) -> Any:
        """Cancelled signals proving filter rate effectiveness."""
        if limit < 1 or limit > 500:
            raise HTTPException(status_code=400, detail="limit must be 1-500")
        signals = ReadOnlyAdapter.get_cancelled_signals(limit=limit)
        return [s.model_dump(mode="json") for s in signals]

    return app


def start_server(host: str = "0.0.0.0", port: int = 8787) -> None:
    """Start observability server in a background thread."""
    try:
        import uvicorn
        app = create_app()
        logger.info(f"OBSERVABILITY_API_STARTING on {host}:{port}")
        uvicorn.run(app, host=host, port=port, log_level="warning")
    except ImportError:
        logger.warning("OBSERVABILITY_API_SKIPPED: uvicorn not installed")
    except Exception as e:
        logger.error(f"OBSERVABILITY_API_FAILED: {e}")
