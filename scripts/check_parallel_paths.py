#!/usr/bin/env python3
"""Atlas AI implementation-boundary overlap detector."""
from __future__ import annotations
import os, sys
from dataclasses import dataclass
from pathlib import Path

DOMAINS = ("market_data", "risk_engine", "memory_storage", "execution", "strategy")
SOURCE_EXTENSIONS = {".rs": "rust", ".py": "python", ".go": "go"}
EXCLUDED_PARTS = frozenset({"contracts","tests","output","sdk","fixtures","target",".git","__pycache__",".venv","node_modules"})

@dataclass(frozen=True)
class Implementation:
    path: Path
    languages: frozenset[str]
    source_files: tuple[Path, ...]

def is_excluded(path: Path) -> bool:
    return any(part in EXCLUDED_PARTS for part in path.parts)

def domain_matches(name: str, domain: str) -> bool:
    normalized = name.lower().replace("-", "_")
    return normalized == domain or normalized.startswith(domain + "_") or normalized.endswith("_" + domain)

def collect_source_files(path: Path) -> tuple[Path, ...]:
    found: list[Path] = []
    for root, dirs, files in os.walk(path):
        root_path = Path(root)
        if is_excluded(root_path):
            dirs[:] = []
            continue
        dirs[:] = [d for d in dirs if not is_excluded(root_path / d)]
        for filename in files:
            file_path = root_path / filename
            if file_path.suffix in SOURCE_EXTENSIONS:
                found.append(file_path)
    return tuple(sorted(found))

def find_implementations(domain: str, project_root: Path) -> list[Implementation]:
    candidates: list[Implementation] = []
    for root, dirs, _ in os.walk(project_root):
        root_path = Path(root)
        if is_excluded(root_path):
            dirs[:] = []
            continue
        dirs[:] = [d for d in dirs if not is_excluded(root_path / d)]
        for directory in dirs:
            candidate_path = root_path / directory
            if not domain_matches(directory, domain):
                continue
            files = collect_source_files(candidate_path)
            if not files:
                continue
            languages = frozenset(SOURCE_EXTENSIONS[file.suffix] for file in files)
            candidates.append(Implementation(path=candidate_path, languages=languages, source_files=files))
    candidates.sort(key=lambda item: (len(item.path.parts), str(item.path)))
    selected: list[Implementation] = []
    for candidate in candidates:
        if any(candidate.path != existing.path and candidate.path.is_relative_to(existing.path) for existing in selected):
            continue
        selected.append(candidate)
    return selected

def classify(implementations: list[Implementation]) -> str:
    if len(implementations) <= 1:
        return "ok"
    shared = set(implementations[0].languages)
    for implementation in implementations[1:]:
        shared.intersection_update(implementation.languages)
    return "violation" if shared else "polyglot"

def main() -> int:
    root = Path.cwd().resolve()
    governance = root / "governance" / "01_ARCHITECTURE_LOCK.md"
    if not governance.is_file():
        print("ERROR: governance/01_ARCHITECTURE_LOCK.md not found", file=sys.stderr)
        return 2
    violations = 0
    polyglot = 0
    print("Atlas AI - Implementation Boundary Detector")
    print(f"Root: {root}")
    for domain in DOMAINS:
        implementations = find_implementations(domain, root)
        status = classify(implementations)
        if status == "ok":
            if not implementations:
                print(f"INFO {domain}: no implementation found")
            else:
                impl = implementations[0]
                languages = ", ".join(sorted(impl.languages))
                print(f"OK {domain}: ./{impl.path.relative_to(root)} [{languages}]")
        elif status == "polyglot":
            polyglot += 1
            print(f"INFO {domain}: {len(implementations)} candidates (POLYGLOT)")
            for impl in implementations:
                languages = ", ".join(sorted(impl.languages))
                print(f"  ./{impl.path.relative_to(root)} [{languages}]")
        else:
            violations += 1
            print(f"WARN {domain}: {len(implementations)} candidates share language (VIOLATION)")
            for impl in implementations:
                languages = ", ".join(sorted(impl.languages))
                print(f"  ./{impl.path.relative_to(root)} [{languages}]")
    if violations:
        print(f"FAIL: {violations} same-language overlap(s)")
        return 1
    print("OK: No same-language overlaps")
    if polyglot:
        print(f"INFO: {polyglot} cross-language overlap(s) for review")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
