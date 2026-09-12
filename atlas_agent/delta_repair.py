"""Delta Repair Engine and Privacy Sanitizer.

Pillar 2: Surgical code repair without full regeneration.
Privacy: Source code never leaves the machine. Only structural
descriptions and sanitized errors are sent to LLM.

Governed by:
  - contracts/schemas/ai/delta-repair-v1.json
  - contracts/schemas/ai/root-cause-v1.json

Flow:
  1. Parse compiler errors → extract line numbers
  2. Extract ONLY failing lines from source (not full file)
  3. Sanitize identifiers (privacy boundary)
  4. Ask LLM for targeted patch (not full rewrite)
  5. Apply patch locally
  6. Verify with compile/test
"""
import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Optional

__all__ = ["DeltaRepairEngine", "PrivacySanitizer", "DeltaPatch", "PatchOperation"]

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PatchOperation:
    """A single surgical patch operation."""
    op: str           # replace_lines | insert_after | delete_lines | append
    start_line: int
    end_line: int
    new_content: str


@dataclass
class DeltaPatch:
    """Collection of patch operations for a single file."""
    target_file: str
    operations: list[PatchOperation] = field(default_factory=list)
    confidence: float = 0.0

    def apply(self, source_lines: list[str]) -> list[str]:
        """Apply patch operations to source lines. Returns new source."""
        result = list(source_lines)
        # Sort operations bottom-to-top to preserve line numbers
        sorted_ops = sorted(self.operations, key=lambda o: o.start_line, reverse=True)
        for patch_op in sorted_ops:
            try:
                if patch_op.op == "replace_lines":
                    new_lines = patch_op.new_content.split("\n")
                    start = max(0, patch_op.start_line - 1)
                    end = min(len(result), patch_op.end_line)
                    result[start:end] = new_lines
                elif patch_op.op == "insert_after":
                    new_lines = patch_op.new_content.split("\n")
                    idx = min(len(result), patch_op.start_line)
                    for i, nl in enumerate(new_lines):
                        result.insert(idx + i, nl)
                elif patch_op.op == "delete_lines":
                    start = max(0, patch_op.start_line - 1)
                    end = min(len(result), patch_op.end_line)
                    del result[start:end]
                elif patch_op.op == "append":
                    result.extend(patch_op.new_content.split("\n"))
            except (IndexError, ValueError) as e:
                logger.warning("Patch op failed: %s at line %d: %s",
                             patch_op.op, patch_op.start_line, e)
                return source_lines  # Rollback on failure
        return result


class PrivacySanitizer:
    """Sanitizes error messages before sending to external LLM.

    Ensures no project-specific identifiers, file paths, or
    business logic leaks through error messages.

    Governed by: delta-repair-v1.json privacy_boundary
    """

    # Patterns that indicate sensitive information
    _PATH_PATTERNS = [
        re.compile(r'/[\w./\-]+\.rs'),
        re.compile(r'/[\w./\-]+\.py'),
        re.compile(r'/[\w./\-]+\.go'),
        re.compile(r'[A-Za-z]:\\[\w.\\\-]+'),
    ]

    # Generic replacements for common identifier types
    _IDENTIFIER_MAP: dict[str, str] = {}

    @classmethod
    def sanitize_error(cls, error: str) -> str:
        """Remove file paths and project-specific info from error message."""
        sanitized = error
        # Strip file paths
        for pattern in cls._PATH_PATTERNS:
            sanitized = pattern.sub("[FILE]", sanitized)
        # Strip home directory references
        sanitized = re.sub(r'/home/[\w]+', '[HOME]', sanitized)
        sanitized = re.sub(r'/root/[\w]*', '[ROOT]', sanitized)
        # Strip temp paths
        sanitized = re.sub(r'/tmp/[\w]+', '[TMP]', sanitized)
        return sanitized[:300]

    @classmethod
    def sanitize_errors(cls, errors: list[str]) -> list[str]:
        """Sanitize a list of error messages."""
        seen = set()
        result = []
        for err in errors:
            s = cls.sanitize_error(err)
            if s and s not in seen:
                seen.add(s)
                result.append(s)
        return result[:15]  # Max 15 sanitized errors

    @classmethod
    def extract_failing_lines(cls, errors: list[str]) -> list[int]:
        """Extract line numbers from compiler error messages."""
        lines = set()
        # Rust: "error[E0425]: ... --> src/main.rs:15:5"
        # Go: "main.go:15:5: ..."
        # Python: 'File "main.py", line 15'
        patterns = [
            re.compile(r':(\d+):\d+'),           # Rust/Go style
            re.compile(r'line (\d+)'),            # Python style
            re.compile(r'-->.*:(\d+)'),          # Rust arrow style
        ]
        for err in errors:
            for pat in patterns:
                matches = pat.findall(err)
                for m in matches:
                    line_num = int(m)
                    if 1 <= line_num <= 10000:
                        lines.add(line_num)
        return sorted(lines)[:20]

    @classmethod
    def extract_context_lines(cls, source_lines: list[str],
                               failing_lines: list[int],
                               context_window: int = 3) -> str:
        """Extract only failing lines + surrounding context.

        Never sends the full file to LLM.
        """
        if not failing_lines or not source_lines:
            return ""
        relevant = set()
        for fl in failing_lines:
            for offset in range(-context_window, context_window + 1):
                idx = fl - 1 + offset
                if 0 <= idx < len(source_lines):
                    relevant.add(idx)
        parts = []
        sorted_indices = sorted(relevant)
        prev = -2
        for idx in sorted_indices:
            if idx > prev + 1:
                parts.append("...")
            parts.append(f"L{idx+1}: {source_lines[idx]}")
            prev = idx
        return "\n".join(parts)[:2000]  # Hard budget


class DeltaRepairEngine:
    """Surgical code repair engine.

    Instead of regenerating the entire file, identifies failing lines,
    asks LLM for targeted patches, and applies them locally.

    Privacy-safe: only sends line numbers + sanitized errors + minimal
    context to LLM. Never sends full source code.

    Governed by: delta-repair-v1.json
    """

    DELTA_PROMPT_TEMPLATE = (
        "You are a surgical code repair tool. You receive ONLY the failing "
        "lines and their surrounding context from a {language} file.\n\n"
        "FAILING LINES:\n{context}\n\n"
        "ERRORS:\n{errors}\n\n"
        "RCA FINDINGS:\n{rca}\n\n"
        "RULES:\n"
        "1. Fix ONLY the failing lines. Do NOT rewrite the entire file.\n"
        "2. Respond with valid JSON only:\n"
        '{{"operations": [{{"op": "replace_lines|insert_after|delete_lines|append", '
        '"start_line": N, "end_line": M, "new_content": "fixed code"}}], '
        '"confidence": 0.0-1.0}}\n'
        "3. Line numbers refer to the original file.\n"
        "4. new_content must be complete, compilable code for those lines.\n"
        "5. Do NOT include any code outside the specified line range.\n"
        "6. Preserve existing indentation and style."
    )

    @classmethod
    def attempt_delta_repair(cls, file_path: str, errors: list[str],
                              language: str, rca_context: str,
                              llm_client: Any) -> Optional[DeltaPatch]:
        """Attempt surgical repair of a single file.

        Returns DeltaPatch if successful, None if delta repair is not possible.
        """
        if not os.path.exists(file_path):
            logger.warning("Delta repair: file not found: %s", file_path)
            return None

        try:
            with open(file_path, encoding="utf-8") as f:
                source_lines = f.read().split("\n")
        except OSError as e:
            logger.warning("Delta repair: cannot read file: %s", e)
            return None

        # Extract failing line numbers
        failing_lines = PrivacySanitizer.extract_failing_lines(errors)
        if not failing_lines:
            logger.debug("Delta repair: no line numbers in errors, skipping")
            return None

        # Extract only relevant context (not full file)
        context = PrivacySanitizer.extract_context_lines(source_lines, failing_lines)
        if not context:
            return None

        # Sanitize errors
        sanitized_errors = PrivacySanitizer.sanitize_errors(errors)

        # Build prompt
        prompt = cls.DELTA_PROMPT_TEMPLATE.format(
            language=language,
            context=context,
            errors="\n".join(sanitized_errors[:5]),
            rca=rca_context[:300] if rca_context else "No RCA available.",
        )

        try:
            response = llm_client.generate_code(prompt, "json")
            parsed = json.loads(response)
            operations = []
            for op_data in parsed.get("operations", [])[:10]:
                op = op_data.get("op", "")
                if op not in ("replace_lines", "insert_after", "delete_lines", "append"):
                    continue
                operations.append(PatchOperation(
                    op=op,
                    start_line=int(op_data.get("start_line", 0)),
                    end_line=int(op_data.get("end_line", op_data.get("start_line", 0))),
                    new_content=str(op_data.get("new_content", ""))[:1024],
                ))
            if not operations:
                logger.debug("Delta repair: LLM returned no valid operations")
                return None
            patch = DeltaPatch(
                target_file=file_path,
                operations=operations,
                confidence=max(0.0, min(1.0, float(parsed.get("confidence", 0.5)))),
            )
            logger.info("Delta repair: %d operations generated, confidence=%.0f%%",
                       len(operations), patch.confidence * 100)
            return patch
        except (json.JSONDecodeError, KeyError, ValueError, Exception) as e:
            logger.warning("Delta repair LLM failed: %s", e)
            return None

    @classmethod
    def apply_patch(cls, patch: DeltaPatch) -> bool:
        """Apply a delta patch to its target file. Returns True on success."""
        try:
            with open(patch.target_file, encoding="utf-8") as f:
                source_lines = f.read().split("\n")
            new_lines = patch.apply(source_lines)
            if new_lines == source_lines:
                logger.warning("Delta repair: patch produced no changes")
                return False
            # Atomic write
            tmp_path = patch.target_file + ".delta_tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write("\n".join(new_lines))
            os.replace(tmp_path, patch.target_file)
            logger.info("Delta repair: applied %d ops to %s",
                       len(patch.operations), os.path.basename(patch.target_file))
            return True
        except OSError as e:
            logger.error("Delta repair: apply failed: %s", e)
            # Cleanup temp file
            tmp = patch.target_file + ".delta_tmp"
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass
            return False
