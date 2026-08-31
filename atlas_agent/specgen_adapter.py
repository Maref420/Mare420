"""Adapter between Atlas AI Orchestrator and Rust SpecGen binary.

Governed by: governance/policies/global-policy.yaml
Role: Deterministic project scaffold generation BEFORE LLM logic filling.

This adapter:
  1. Converts Requirement → SpecGen TOML metadata
  2. Invokes specgen binary as subprocess
  3. Parses output and returns GenerationResult
  4. Provides graceful degradation if specgen is unavailable
"""
import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Governed: specgen binary location relative to project root.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SPECGEN_BINARY = _PROJECT_ROOT / "tools" / "specgen" / "target" / "debug" / "specgen"
_TEMPLATES_DIR = _PROJECT_ROOT / "tools" / "specgen" / "templates"


@dataclass
class SpecGenMetadata:
    """Metadata document for specgen invocation.

    Fields map 1:1 to specgen's ModuleMetadata struct.
    Governed by: tools/specgen/src/metadata.rs
    """
    name: str
    artifact: str
    language: str
    profile: str
    owner: str
    purpose: str
    specification_id: str
    responsibilities: list[str] = field(default_factory=list)
    forbidden: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)

    def to_toml(self) -> str:
        """Serialize to TOML format expected by specgen."""
        lines = ["[module]"]
        lines.append(f'name = "{self.name}"')
        lines.append(f'artifact = "{self.artifact}"')
        lines.append(f'language = "{self.language}"')
        lines.append(f'profile = "{self.profile}"')
        lines.append(f'owner = "{self.owner}"')
        lines.append(f'purpose = "{self.purpose}"')
        lines.append(f'specification_id = "{self.specification_id}"')

        if self.responsibilities:
            items = ", ".join(f'"{r}"' for r in self.responsibilities)
            lines.append(f"responsibilities = [{items}]")

        if self.forbidden:
            items = ", ".join(f'"{f}"' for f in self.forbidden)
            lines.append(f"forbidden = [{items}]")

        if self.dependencies:
            items = ", ".join(f'"{d}"' for d in self.dependencies)
            lines.append(f"dependencies = [{items}]")

        return "\n".join(lines) + "\n"


@dataclass
class GenerationResult:
    """Result of a specgen invocation."""
    success: bool
    files_written: list[str] = field(default_factory=list)
    output_dir: str = ""
    error_message: str = ""


def is_available() -> bool:
    """Check if specgen binary exists and is executable."""
    return _SPECGEN_BINARY.exists() and os.access(_SPECGEN_BINARY, os.X_OK)


def generate_scaffold(
    metadata: SpecGenMetadata,
    output_dir: Path,
    timeout_seconds: int = 30,
) -> GenerationResult:
    """Invoke specgen to generate a deterministic project scaffold.

    Args:
        metadata: Module specification for generation.
        output_dir: Target directory for generated files.
        timeout_seconds: Maximum execution time.

    Returns:
        GenerationResult with success status and file list.
    """
    if not is_available():
        logger.warning(
            "specgen binary not found at %s; skipping scaffold generation",
            _SPECGEN_BINARY,
        )
        return GenerationResult(
            success=False,
            error_message="specgen binary not available",
        )

    # Write metadata TOML to temp file
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".toml", delete=False, prefix="specgen_meta_"
        ) as tmp:
            tmp.write(metadata.to_toml())
            metadata_path = tmp.name
    except OSError as exc:
        logger.error("Failed to write specgen metadata: %s", exc)
        return GenerationResult(success=False, error_message=str(exc))

    try:
        # Ensure output directory exists
        output_dir.mkdir(parents=True, exist_ok=True)

        # Invoke specgen
        cmd = [
            str(_SPECGEN_BINARY),
            "--metadata", metadata_path,
            "--output", str(output_dir),
            "--templates", str(_TEMPLATES_DIR),
        ]

        logger.info("Invoking specgen: %s", " ".join(cmd))
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )

        if result.returncode != 0:
            logger.error(
                "specgen failed (exit %d): %s",
                result.returncode,
                result.stderr.strip(),
            )
            return GenerationResult(
                success=False,
                error_message=result.stderr.strip() or "specgen exited with error",
            )

        # Parse generated files from stdout
        files_written = []
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if stripped.startswith("→"):
                files_written.append(stripped.lstrip("→ ").strip())

        logger.info(
            "specgen generated %d files in %s",
            len(files_written),
            output_dir,
        )

        return GenerationResult(
            success=True,
            files_written=files_written,
            output_dir=str(output_dir),
        )

    except subprocess.TimeoutExpired:
        logger.error("specgen timed out after %ds", timeout_seconds)
        return GenerationResult(
            success=False,
            error_message=f"specgen timed out after {timeout_seconds}s",
        )
    except OSError as exc:
        logger.error("Failed to execute specgen: %s", exc)
        return GenerationResult(success=False, error_message=str(exc))
    finally:
        # Clean up temp metadata file
        try:
            os.unlink(metadata_path)
        except OSError:  # acceptable: temp file may already be removed
            pass


def build_metadata_from_requirement(
    name: str,
    language: str,
    purpose: str,
    specification_id: str = "SPEC-AUTO",
    artifact: str = "module",
    profile: str = "production",
    owner: str = "Atlas AI",
    responsibilities: Optional[list[str]] = None,
    forbidden: Optional[list[str]] = None,
    dependencies: Optional[list[str]] = None,
) -> SpecGenMetadata:
    """Build SpecGenMetadata from high-level requirement parameters.

    Convenience function for orchestrator integration.
    """
    return SpecGenMetadata(
        name=name,
        artifact=artifact,
        language=language,
        profile=profile,
        owner=owner,
        purpose=purpose,
        specification_id=specification_id,
        responsibilities=responsibilities or [],
        forbidden=forbidden or [],
        dependencies=dependencies or [],
    )
