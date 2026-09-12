"""Portable Memory Engine for self-correcting loop learning."""
import hashlib, json, logging, os, shutil, tempfile, time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional
from .pattern_extractor import ErrorCategory, ExtractedPattern, PatternExtractor

__all__ = ["PortableMemory", "MemoryExperience", "AntiPatternRecord", "StrategyStats"]
logger = logging.getLogger(__name__)
DEFAULT_MEMORY_PATH = Path(__file__).parent / "portable_memory.jsonl"
SCHEMA_VERSION = "1.0"
MAX_ENTRIES = 10000
MAX_SIZE_MB = 50
MAX_FIELD_LENGTH = 512
BACKUP_SUFFIX = ".bak"

@dataclass
class MemoryExperience:
    pattern_id: str
    error_pattern: str
    root_cause_category: str
    fix_strategy: str
    language: str
    module_type: str
    success_after_fix: bool
    quality_before: float
    quality_after: float
    quality_delta: float
    occurrences: int = 1
    last_seen: str = ""
    created_at: str = ""
    def __post_init__(self) -> None:
        if not self.last_seen:
            self.last_seen = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        if not self.created_at:
            self.created_at = self.last_seen
        self.error_pattern = self.error_pattern[:MAX_FIELD_LENGTH]
        self.fix_strategy = self.fix_strategy[:MAX_FIELD_LENGTH]
        self.module_type = self.module_type[:128]
        self.quality_before = max(0.0, min(1.0, self.quality_before))
        self.quality_after = max(0.0, min(1.0, self.quality_after))
        self.quality_delta = max(-1.0, min(1.0, self.quality_delta))
        self.occurrences = max(1, self.occurrences)
    def validate(self) -> bool:
        req = [self.pattern_id, self.error_pattern, self.root_cause_category, self.fix_strategy, self.language]
        if any(not s or not isinstance(s, str) for s in req):
            return False
        return self.language in ("rust", "go", "python")

@dataclass
class AntiPatternRecord:
    pattern_id: str
    description: str
    language: str
    severity: str
    confidence: float
    promoted_from_experiences: int = 0
    fix_hint: str = ""
    def __post_init__(self) -> None:
        self.description = self.description[:MAX_FIELD_LENGTH]
        self.fix_hint = self.fix_hint[:MAX_FIELD_LENGTH]
        self.confidence = max(0.0, min(1.0, self.confidence))
        if self.severity not in ("low", "medium", "high", "critical"):
            self.severity = "medium"

@dataclass
class StrategyStats:
    total_attempts: int = 0
    total_successes: int = 0
    score_sum: float = 0.0
    last_used: str = ""
    @property
    def avg_score(self) -> float:
        return self.score_sum / self.total_attempts if self.total_attempts > 0 else 0.0
    @property
    def success_rate(self) -> float:
        return self.total_successes / self.total_attempts if self.total_attempts > 0 else 0.0
    def record(self, score: float, success: bool) -> None:
        self.total_attempts += 1
        self.score_sum += max(0.0, min(1.0, score))
        if success:
            self.total_successes += 1
        self.last_used = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    def weighted_success_rate(self, decay_days: float = 30.0) -> float:
        if self.total_attempts < 1:
            return 0.0
        base_rate = self.success_rate
        if not self.last_used:
            return base_rate
        try:
            last = time.strptime(self.last_used, "%Y-%m-%dT%H:%M:%SZ")
            age_days = (time.time() - time.mktime(last)) / 86400.0
        except (ValueError, OverflowError):
            return base_rate
        decay = max(0.0, 1.0 - (age_days / decay_days))
        return base_rate * decay + 0.5 * (1.0 - decay)

class PortableMemory:
    MIN_STRATEGY_SAMPLES = 3
    MIN_STRATEGY_SUCCESS_RATE = 0.4
    def __init__(self, memory_path: Path = DEFAULT_MEMORY_PATH) -> None:
        self.path = memory_path
        self._experiences: dict[str, MemoryExperience] = {}
        self._anti_patterns: dict[str, AntiPatternRecord] = {}
        self._strategy_stats: dict[str, StrategyStats] = {
            "patch": StrategyStats(), "rewrite": StrategyStats(),
            "different_model": StrategyStats(), "different_prompt": StrategyStats(),
        }
        self._knowledge: dict[str, KnowledgeEntry] = {}
        self._seed_knowledge()
        self._load()
    def learn(self, patterns: list[ExtractedPattern], language: str, module_type: str,
              quality_before: float, quality_after: float, strategy_used: str, success: bool) -> int:
        delta = quality_after - quality_before
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        new_count = 0
        for pat in patterns:
            if PatternExtractor._contains_sensitive_data(pat.description) or PatternExtractor._contains_sensitive_data(pat.suggested_fix):
                logger.warning("Blocked sensitive pattern: %s", pat.pattern_id)
                continue
            if pat.pattern_id in self._experiences:
                exp = self._experiences[pat.pattern_id]
                exp.occurrences += 1
                exp.last_seen = now
                exp.quality_delta = max(-1.0, min(1.0, delta))
                if success:
                    exp.success_after_fix = True
                    exp.quality_after = max(exp.quality_after, quality_after)
            else:
                exp = MemoryExperience(pattern_id=pat.pattern_id, error_pattern=pat.description[:MAX_FIELD_LENGTH],
                    root_cause_category=pat.category.value, fix_strategy=pat.suggested_fix[:MAX_FIELD_LENGTH],
                    language=language, module_type=module_type[:128], success_after_fix=success,
                    quality_before=quality_before, quality_after=quality_after, quality_delta=delta,
                    occurrences=1, last_seen=now, created_at=now)
                if not exp.validate():
                    continue
                self._experiences[pat.pattern_id] = exp
                new_count += 1
            if not success and PatternExtractor.should_promote_to_anti_pattern(exp.occurrences, pat.category):
                self._promote_to_anti_pattern(exp, pat)
        if strategy_used in self._strategy_stats:
            self._strategy_stats[strategy_used].record(quality_after, success)
        self._flush()
        logger.info("Learned: %d new, %d total, strategy=%s score=%.2f->%.2f",
                     new_count, len(self._experiences), strategy_used, quality_before, quality_after)
        return new_count
    def recall(self, language: str, error_categories: Optional[list[str]] = None, limit: int = 5) -> list[MemoryExperience]:
        cands = [e for e in self._experiences.values() if e.language == language and (error_categories is None or e.root_cause_category in error_categories)]
        cands.sort(key=lambda e: (e.occurrences, e.last_seen), reverse=True)
        return cands[:limit]
    def get_repair_hints(self, language: str, error_categories: list[str]) -> list[str]:
        hints, seen = [], set()
        for exp in self.recall(language, error_categories, limit=5):
            if exp.fix_strategy and exp.fix_strategy not in seen:
                hints.append(f"[LEARNED x{exp.occurrences}] {exp.error_pattern} -> {exp.fix_strategy}"[:300])
                seen.add(exp.fix_strategy)
        return hints
    def predict_best_first_attempt(
        self, language: str, requirement_keywords: list[str],
        module_type: str = "*",
    ) -> dict:
        """Predict the best FIRST attempt strategy BEFORE generating code.

        This is what makes Atlas AI unique: proactive failure prevention
        instead of reactive fixing. No competitor does this.

        Analyzes historical data to predict which strategy will succeed
        on the FIRST attempt for this specific combination of:
        - target language
        - requirement patterns (keywords extracted from description)
        - module type

        Returns:
            {
                "strategy": "patch|rewrite|different_prompt",
                "confidence": 0.0-1.0,
                "reason": "why this strategy is predicted to work",
                "historical_matches": int,
                "predicted_attempts_saved": float,
            }
        """
        lang_stats = self._strategy_stats.get(language)
        if not lang_stats or len(self._experiences) < 5:
            return {
                "strategy": "patch",
                "confidence": 0.0,
                "reason": "insufficient historical data",
                "historical_matches": 0,
                "predicted_attempts_saved": 0.0,
            }

        # Find experiences matching this language + keyword overlap
        matched_experiences: list[tuple] = []
        req_kw_set = set(k.lower() for k in requirement_keywords)

        for exp in self._experiences:
            if not hasattr(exp, "language") or exp.language != language:
                continue
            # Keyword overlap scoring
            exp_keywords = set()
            if hasattr(exp, "requirement_summary"):
                exp_keywords = set(
                    w.lower() for w in str(exp.requirement_summary).split()
                    if len(w) > 3
                )
            overlap = len(req_kw_set & exp_keywords) if req_kw_set and exp_keywords else 0
            # Module type match bonus
            module_match = (
                hasattr(exp, "module_type") and
                (exp.module_type == module_type or exp.module_type == "*")
            )
            relevance = overlap + (2 if module_match else 0)
            if relevance > 0:
                matched_experiences.append((exp, relevance))

        if not matched_experiences:
            # No keyword matches — fall back to overall best
            best_strat = self.get_best_strategy(language)
            stat = lang_stats.get(best_strat)
            conf = stat.success_rate if stat else 0.0
            return {
                "strategy": best_strat,
                "confidence": round(conf * 0.5, 2),  # Lower confidence without keyword match
                "reason": f"no keyword match, using overall best for {language}",
                "historical_matches": 0,
                "predicted_attempts_saved": 0.0,
            }

        # Weight strategies by relevance-weighted success
        strategy_scores: dict[str, float] = {}
        strategy_counts: dict[str, int] = {}
        total_relevance = 0

        for exp, relevance in sorted(matched_experiences, key=lambda x: -x[1])[:20]:
            strat = getattr(exp, "strategy_used", "patch")
            success = getattr(exp, "success", False)
            weight = relevance * (getattr(exp, "weight", 1.0) if hasattr(exp, "weight") else 1.0)
            strategy_scores[strat] = strategy_scores.get(strat, 0.0) + (weight if success else 0.0)
            strategy_counts[strat] = strategy_counts.get(strat, 0) + 1
            total_relevance += weight

        if total_relevance == 0:
            return {
                "strategy": "patch",
                "confidence": 0.0,
                "reason": "matched experiences but zero weight",
                "historical_matches": len(matched_experiences),
                "predicted_attempts_saved": 0.0,
            }

        # Normalize scores
        for strat in strategy_scores:
            strategy_scores[strat] /= total_relevance

        best_strat = max(strategy_scores, key=strategy_scores.get)
        confidence = round(strategy_scores[best_strat], 2)
        n_matches = sum(strategy_counts.values())

        # Estimate attempts saved vs naive PATCH-first approach
        patch_rate = strategy_scores.get("patch", 0.0)
        attempts_saved = max(0.0, round((confidence - patch_rate) * 2.5, 1))

        return {
            "strategy": best_strat,
            "confidence": confidence,
            "reason": (
                f"{n_matches} similar past attempts matched, "
                f"'{best_strat}' succeeded {confidence:.0%} of the time"
            ),
            "historical_matches": n_matches,
            "predicted_attempts_saved": attempts_saved,
        }

    def get_best_strategy(self, language: str) -> str:
        """Return the best-performing strategy for a language."""
        best_name, best_rate = "patch", -1.0
        for name, stats in self._strategy_stats.items():
            if stats.total_attempts < self.MIN_STRATEGY_SAMPLES:
                continue
            w = stats.weighted_success_rate(decay_days=30.0)
            if w > best_rate and w >= self.MIN_STRATEGY_SUCCESS_RATE:
                best_rate, best_name = w, name
        return best_name
    def get_anti_patterns(self, language: Optional[str] = None) -> list[AntiPatternRecord]:
        pats = [p for p in self._anti_patterns.values() if language is None or p.language == language]
        pats.sort(key=lambda p: p.confidence, reverse=True)
        return pats
    def get_anti_pattern_descriptions(self, language: Optional[str] = None) -> list[str]:
        return [f"[ANTI-PATTERN conf={p.confidence:.0%}] {p.description}" for p in self.get_anti_patterns(language)]
    def export_json(self) -> str:
        return json.dumps({"version": SCHEMA_VERSION,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "experiences": [asdict(e) for e in self._experiences.values()],
            "anti_patterns": [asdict(a) for a in self._anti_patterns.values()],
            "strategy_scores": {n: {"avg_score": s.avg_score, "success_rate": s.success_rate,
                "total_attempts": s.total_attempts, "last_used": s.last_used}
                for n, s in self._strategy_stats.items()}}, indent=2, ensure_ascii=False)
    def import_json(self, json_str: str) -> int:
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse memory JSON: %s", e)
            return 0
        imported = 0
        for ed in data.get("experiences", []):
            pid = ed.get("pattern_id", "")
            if pid and pid not in self._experiences:
                try:
                    f = {k: v for k, v in ed.items() if k in MemoryExperience.__dataclass_fields__}
                    exp = MemoryExperience(**f)
                    if exp.validate():
                        self._experiences[pid] = exp
                        imported += 1
                except TypeError:
                    pass
        for ad in data.get("anti_patterns", []):
            pid = ad.get("pattern_id", "")
            if pid and pid not in self._anti_patterns:
                try:
                    f = {k: v for k, v in ad.items() if k in AntiPatternRecord.__dataclass_fields__}
                    self._anti_patterns[pid] = AntiPatternRecord(**f)
                except TypeError:
                    pass
        self._flush()
        return imported
    def export_to_file(self, path: Optional[Path] = None) -> Path:
        target = path or self.path.with_suffix(".export.json")
        target.write_text(self.export_json(), encoding="utf-8")
        return target
    def import_from_file(self, path: Path) -> int:
        if not path.exists():
            return 0
        return self.import_json(path.read_text(encoding="utf-8"))
    def stats(self) -> dict:
        return {"version": SCHEMA_VERSION, "total_experiences": len(self._experiences),
            "total_anti_patterns": len(self._anti_patterns),
            "knowledge": len(self._knowledge),
            "strategy_scores": {n: {"avg_score": round(s.avg_score, 3), "success_rate": round(s.success_rate, 3),
                "weighted_rate": round(s.weighted_success_rate(), 3), "attempts": s.total_attempts}
                for n, s in self._strategy_stats.items() if s.total_attempts > 0},
            "file_kb": self.path.stat().st_size // 1024 if self.path.exists() else 0}
    def migrate_from_legacy(self, legacy_memory: Any) -> int:
        migrated = 0
        for exp in legacy_memory.experiences:
            raw = f"{exp.artifact.language}:{exp.artifact.module}:{exp.ts}:{exp.outcome.quality_score}"
            pid = f"legacy_{hashlib.sha256(raw.encode()).hexdigest()[:12]}"
            if pid in self._experiences:
                continue
            anti_desc = ", ".join(exp.anti_patterns) if exp.anti_patterns else "none"
            mem_exp = MemoryExperience(pattern_id=pid,
                error_pattern=f"Legacy: {exp.type} for {exp.artifact.module}"[:MAX_FIELD_LENGTH],
                root_cause_category="unknown",
                fix_strategy=f"Anti-patterns: {anti_desc}"[:MAX_FIELD_LENGTH],
                language=exp.artifact.language, module_type=exp.artifact.module[:128],
                success_after_fix=(exp.outcome.human_decision == "approved"),
                quality_before=0.0, quality_after=exp.outcome.quality_score,
                quality_delta=exp.outcome.quality_score,
                occurrences=1, last_seen=exp.ts, created_at=exp.ts)
            if mem_exp.validate():
                self._experiences[pid] = mem_exp
                migrated += 1
            for ap_str in exp.anti_patterns:
                ap_id = f"legacy_ap_{hashlib.sha256(ap_str.encode()).hexdigest()[:12]}"
                if ap_id not in self._anti_patterns:
                    self._anti_patterns[ap_id] = AntiPatternRecord(
                        pattern_id=ap_id, description=ap_str[:MAX_FIELD_LENGTH],
                        language=exp.artifact.language, severity="medium",
                        confidence=0.5, promoted_from_experiences=1, fix_hint="")
        if migrated > 0:
            self._flush()
            logger.info("Migrated %d experiences from legacy memory", migrated)
        return migrated
    def _promote_to_anti_pattern(self, exp: MemoryExperience, pat: ExtractedPattern) -> None:
        if exp.pattern_id in self._anti_patterns:
            self._anti_patterns[exp.pattern_id].promoted_from_experiences = exp.occurrences
            self._anti_patterns[exp.pattern_id].confidence = PatternExtractor.compute_confidence(exp.occurrences)
            return
        sev = pat.severity if hasattr(pat, "severity") else "high"
        record = AntiPatternRecord(pattern_id=exp.pattern_id, description=exp.error_pattern,
            language=exp.language, severity=sev,
            confidence=PatternExtractor.compute_confidence(exp.occurrences),
            promoted_from_experiences=exp.occurrences, fix_hint=exp.fix_strategy)
        self._anti_patterns[exp.pattern_id] = record
        logger.info("Promoted to anti-pattern: %s (conf=%.0f%%, occ=%d)",
                     exp.error_pattern, record.confidence * 100, exp.occurrences)
    def _seed_knowledge(self) -> None:
        """Load seed knowledge entries. Idempotent — skips existing keys."""
        for entry in _build_seed_knowledge():
            if entry.key not in self._knowledge:
                self._knowledge[entry.key] = entry

    def get_knowledge_context(self, language: str, module_type: str = "*",
                               phase: str = "*", limit: int = 12) -> list[str]:
        """Retrieve relevant knowledge entries for LLM prompt injection.

        Returns content strings sorted by priority DESC.
        Filters by language, module_type, phase with wildcard matching.
        Privacy rules (priority 1000) always included regardless of filters.
        """
        lang = language.lower().strip() if language else "*"
        matched: list[KnowledgeEntry] = []
        for entry in self._knowledge.values():
            if not entry.enabled:
                continue
            # Only truly global priority-1000 rules always override.
            # Phase-specific high-priority rules must still respect phase.
            is_global_override = (
                entry.priority >= 1000
                and entry.language == "*"
                and entry.module_type == "*"
                and entry.phase == "*"
            )
            lang_match = entry.language in ("*", lang)
            mod_match = entry.module_type in ("*", module_type)
            phase_match = entry.phase in ("*", phase)
            if is_global_override or (lang_match and mod_match and phase_match):
                matched.append(entry)
        # Sort by priority DESC, take top N
        matched.sort(key=lambda e: e.priority, reverse=True)
        result = [e.content for e in matched[:limit]]
        logger.debug("Knowledge context: %d/%d entries for lang=%s phase=%s",
                     len(result), len(matched), lang, phase)
        return result

    def learn_from_attempt(self, requirement: object, strategy: str,
                           quality_score: float, errors: list[str],
                           security_findings: list[str], governance_passed: bool,
                           language: str, module_type: str = "unknown",
                           quality_before: float = 0.0) -> int:
        """Learn from an attempt outcome. Bridges orchestrator to memory.

        This is the method orchestrator.py calls. It:
        1. Validates language
        2. Extracts patterns via PatternExtractor (two-pass with RCA fallback)
        3. Stores experiences
        4. Auto-generates anti-patterns on repeated failure
        5. Updates strategy stats

        Returns number of new patterns learned.
        """
        lang = language.lower().strip() if language else ""
        if lang not in ("rust", "go", "python"):
            logger.warning("learn_from_attempt: invalid language '%s', defaulting rust", language)
            lang = "rust"

        success = quality_score >= 0.8
        delta = quality_score - quality_before

        # Extract patterns using two-pass extractor (regex + RCA fallback)
        patterns = PatternExtractor.extract(errors, security_findings, lang)

        # Learn via existing method
        new_count = self.learn(
            patterns=patterns,
            language=lang,
            module_type=str(module_type)[:128],
            quality_before=quality_before,
            quality_after=quality_score,
            strategy_used=str(strategy),
            success=success,
        )

        # Auto-generate anti-patterns for stuck patterns (delta=0)
        if not success and delta == 0.0:
            for pat in patterns:
                exp = self._experiences.get(pat.pattern_id)
                if exp and exp.occurrences >= 2:
                    self._promote_to_anti_pattern(exp, pat)
                    logger.info("Auto-promoted anti-pattern: %s (occ=%d, delta=0)",
                               pat.description[:60], exp.occurrences)

        logger.info("learn_from_attempt: lang=%s strategy=%s score=%.2f success=%s new=%d",
                     lang, strategy, quality_score, success, new_count)
        return new_count

    def _create_backup(self) -> None:
        if not self.path.exists():
            return
        try:
            shutil.copy2(self.path, self.path.with_suffix(self.path.suffix + BACKUP_SUFFIX))
        except OSError as e:
            logger.warning("Failed to create memory backup: %s", e)
    def _load(self) -> None:
        if not self.path.exists():
            logger.info("No portable memory found - starting fresh")
            return
        size_mb = self.path.stat().st_size / (1024 * 1024)
        if size_mb > MAX_SIZE_MB:
            self._prune()
        loaded, skipped = 0, 0
        with open(self.path, encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    rt = data.get("_type", "experience")
                    if rt == "knowledge":
                        ke = KnowledgeEntry.from_dict(data)
                        if ke.enabled:
                            self._knowledge[ke.key] = ke
                            loaded += 1
                    elif rt == "experience":
                        data.pop("_type", None)
                        flt = {k: v for k, v in data.items() if k in MemoryExperience.__dataclass_fields__}
                        exp = MemoryExperience(**flt)
                        if exp.validate():
                            self._experiences[exp.pattern_id] = exp
                            loaded += 1
                        else:
                            skipped += 1
                    elif rt == "anti_pattern":
                        data.pop("_type", None)
                        flt = {k: v for k, v in data.items() if k in AntiPatternRecord.__dataclass_fields__}
                        ap = AntiPatternRecord(**flt)
                        self._anti_patterns[ap.pattern_id] = ap
                        loaded += 1
                    elif rt == "strategy_stats":
                        name = data.get("name", "")
                        if name in self._strategy_stats:
                            self._strategy_stats[name].total_attempts = int(data.get("total_attempts", 0))
                            self._strategy_stats[name].total_successes = int(data.get("total_successes", 0))
                            self._strategy_stats[name].score_sum = float(data.get("score_sum", 0.0))
                            self._strategy_stats[name].last_used = data.get("last_used", "")
                            loaded += 1
                except (json.JSONDecodeError, TypeError, KeyError, ValueError) as e:
                    skipped += 1
                    logger.debug("Line %d corrupt: %s", line_num, e)
        if loaded == 0 and skipped > 0:
            self._try_recover_from_backup()
        if len(self._experiences) > MAX_ENTRIES:
            self._enforce_entry_limit()
        logger.info("Portable memory loaded: %d valid, %d skipped, %d anti-patterns",
                     loaded, skipped, len(self._anti_patterns))
    def _try_recover_from_backup(self) -> None:
        backup = self.path.with_suffix(self.path.suffix + BACKUP_SUFFIX)
        if not backup.exists():
            return
        logger.info("Attempting recovery from backup: %s", backup)
        try:
            recovered = self.import_json(backup.read_text(encoding="utf-8"))
            if recovered > 0:
                logger.info("Recovered %d entries from backup", recovered)
        except OSError as e:
            logger.error("Backup recovery failed: %s", e)
    def _flush(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lines = []
        for ke in self._knowledge.values():
            d = asdict(ke)
            d["_type"] = "knowledge"
            lines.append(json.dumps(d, ensure_ascii=False))
        for exp in self._experiences.values():
            d = asdict(exp)
            d["_type"] = "experience"
            lines.append(json.dumps(d, ensure_ascii=False))
        for ap in self._anti_patterns.values():
            d = asdict(ap)
            d["_type"] = "anti_pattern"
            lines.append(json.dumps(d, ensure_ascii=False))
        for name, s in self._strategy_stats.items():
            lines.append(json.dumps({"_type": "strategy_stats", "name": name,
                "total_attempts": s.total_attempts, "total_successes": s.total_successes,
                "score_sum": s.score_sum, "last_used": s.last_used}, ensure_ascii=False))
        content = "\n".join(lines) + "\n" if lines else ""
        fd, tmp_path = tempfile.mkstemp(dir=str(self.path.parent), prefix=".pm_", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            self._create_backup()
            os.replace(tmp_path, str(self.path))
        except OSError as e:
            logger.error("Atomic write failed: %s", e)
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
    def _prune(self) -> None:
        if not self.path.exists():
            return
        try:
            lines = self.path.read_text(encoding="utf-8").strip().split("\n")
            if len(lines) <= MAX_ENTRIES:
                return
            self.path.write_text("\n".join(lines[-MAX_ENTRIES:]) + "\n", encoding="utf-8")
            logger.info("Pruned memory: %d -> %d entries", len(lines), MAX_ENTRIES)
        except OSError as e:
            logger.error("Prune failed: %s", e)
    def _enforce_entry_limit(self) -> None:
        if len(self._experiences) <= MAX_ENTRIES:
            return
        sorted_exps = sorted(self._experiences.values(), key=lambda e: e.last_seen, reverse=True)
        for exp in sorted_exps[MAX_ENTRIES:]:
            del self._experiences[exp.pattern_id]
        logger.info("Enforced entry limit: removed %d oldest", len(sorted_exps) - MAX_ENTRIES)



    # ── Resilience Layer: methods that close the read/write gap ──

    def build_regeneration_prompt(
        self, language: str, original_prompt: str,
        failed_errors: list[str], module_type: str = "*",
    ) -> str:
        """Build an augmented prompt for LLM regeneration after failure.

        Injects three layers of context from memory into the prompt:
        1. Repair hints from past experiences (what worked before)
        2. Anti-pattern descriptions (what to avoid)
        3. Knowledge context rules (governance + language standards)

        This is the READ path that was missing. Without it, regeneration
        calls the LLM with zero memory of previous failures.

        Governed by: learning.strategy_switching seed knowledge entry.
        """
        lang = language.lower().strip() if language else "python"
        sections: list[str] = [original_prompt]

        # Layer 1: Repair hints from past experiences
        categories = self._categorize_errors(failed_errors)
        hints = self.get_repair_hints(lang, categories)
        if hints:
            sections.append("\n## PREVIOUS FIXES THAT WORKED:")
            for hint in hints[:5]:
                sections.append(f"- {hint}")

        # Layer 2: Anti-patterns to avoid
        anti_descs = self.get_anti_pattern_descriptions(lang)
        if anti_descs:
            sections.append("\n## KNOWN ANTI-PATTERNS (DO NOT REPEAT):")
            for desc in anti_descs[:5]:
                sections.append(f"- {desc}")

        # Layer 3: Governance + language knowledge context
        knowledge = self.get_knowledge_context(
            language=lang, module_type=module_type, phase="generation", limit=8,
        )
        if knowledge:
            sections.append("\n## STRICT RULES:")
            for rule in knowledge:
                sections.append(f"- {rule}")

        augmented = "\n".join(sections)
        logger.info(
            "build_regeneration_prompt: lang=%s hints=%d anti=%d rules=%d total_len=%d",
            lang, len(hints), len(anti_descs), len(knowledge), len(augmented),
        )
        return augmented

    def sanitize_code(self, code: str, language: str) -> str:
        """Remove known-dangerous patterns from generated code BEFORE compile check.

        This is a deterministic fix layer that runs without LLM.
        Catches patterns that delta repair misses because they are
        syntactic rather than semantic errors.

        Current fixes:
        - Strip inline comments inside dict/set/list literals (Python)
          e.g., '"__builtins__": None  # Restrict builtins' -> '"__builtins__": None'

        Governed by: constitution.error_handling seed knowledge entry.
        """
        import re as _re
        lang = language.lower().strip() if language else ""
        if lang != "python":
            return code

        sanitized = code
        ops = 0

        # Fix: comments after values inside dict/set/list literals
        pattern = r'(:\s*[^#\n,}\]]+)\s+#[^\n]*(?=\s*[,}\]\n])'
        new_code = _re.sub(pattern, r'\1', sanitized)
        if new_code != sanitized:
            ops += 1
            sanitized = new_code

        # Fix: trailing comment after last dict value before closing brace
        pattern2 = r'(:\s*[^#\n}]+)\s+#[^\n]*(?=\s*\})'
        new_code2 = _re.sub(pattern2, r'\1', sanitized)
        if new_code2 != sanitized:
            ops += 1
            sanitized = new_code2

        if ops > 0:
            logger.info("sanitize_code: applied %d deterministic fixes", ops)
        return sanitized

    def record_repair_coverage(
        self, total_errors: int, fixed_errors: int,
        strategy: str, language: str,
    ) -> float:
        """Record how many errors a repair strategy actually fixed.

        Returns real confidence (fixed/total) instead of inflated metrics.
        Stores as a synthetic experience so future attempts can choose
        the strategy with best actual coverage.

        Governed by: learning.scorecard_policy seed knowledge entry.
        """
        if total_errors <= 0:
            return 1.0

        coverage = fixed_errors / total_errors
        lang = language.lower().strip() if language else "python"
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        pid = f"repair_coverage:{strategy}:{lang}"

        exp = MemoryExperience(
            pattern_id=pid,
            error_pattern=f"Repair coverage: {fixed_errors}/{total_errors} errors fixed",
            root_cause_category="repair_metrics",
            fix_strategy=strategy,
            language=lang,
            module_type="repair_tracker",
            success_after_fix=(coverage >= 0.8),
            quality_before=0.0,
            quality_after=coverage,
            quality_delta=coverage,
            occurrences=1,
            last_seen=now,
            created_at=now,
        )

        if pid in self._experiences:
            existing = self._experiences[pid]
            existing.occurrences += 1
            existing.last_seen = now
            existing.quality_after = (
                (existing.quality_after * (existing.occurrences - 1) + coverage)
                / existing.occurrences
            )
        else:
            self._experiences[pid] = exp

        self._flush()
        logger.info(
            "record_repair_coverage: strategy=%s coverage=%.0f%% (%d/%d)",
            strategy, coverage * 100, fixed_errors, total_errors,
        )
        return coverage

    def get_strategy_confidence(self, strategy: str, language: str) -> float:
        """Get real historical confidence for a repair strategy.

        Replaces hardcoded 'confidence=99%' with actual data from
        record_repair_coverage calls.
        """
        pid = f"repair_coverage:{strategy}:{language.lower().strip()}"
        exp = self._experiences.get(pid)
        if exp and exp.occurrences >= 2:
            return exp.quality_after
        return 0.5  # Unknown strategy, honest default

    def _categorize_errors(self, errors: list[str]) -> list[str]:
        """Extract error categories from raw error strings for recall lookup."""
        categories: set[str] = set()
        lower_errors = [e.lower() for e in errors]
        if any("syntaxerror" in e or "invalid syntax" in e for e in lower_errors):
            categories.add("syntax")
        if any("security" in e or "builtins" in e or "forbidden" in e for e in lower_errors):
            categories.add("security")
        if any("governance" in e or "restriction" in e or "gov=fail" in e for e in lower_errors):
            categories.add("governance")
        if any("import" in e or "modulenotfound" in e or "nameerror" in e for e in lower_errors):
            categories.add("semantic")
        if not categories:
            categories.add("unknown")
        return list(categories)


# ════════════════════════════════════════════════════════════════════
# KNOWLEDGE LAYER — Immutable rules injected into every LLM prompt.
# Separate from experiences to prevent loop confusion.
# Inspired by: Caura R01-R10, System Prompt I1-I10, Error Contract §6
# ════════════════════════════════════════════════════════════════════

@dataclass
class KnowledgeEntry:
    """A governance/standard/policy rule stored in portable memory.

    Unlike experiences (which track attempt outcomes), knowledge entries
    are immutable rules that guide LLM behavior across all attempts.

    Priority ordering (higher = injected first, always wins conflicts):
      1000: privacy rules + provenance (always override everything)
       900: project constitution + ownership + action gates
       800: language-specific coding standards + architecture
       750: LLM interaction rules per phase
       700: module architecture rules
       650: learning policy + scorecard
       600: prompt templates
    """
    knowledge_type: str
    key: str
    priority: int
    language: str
    module_type: str
    phase: str
    content: str
    tags: list[str] = field(default_factory=list)
    version: str = "1.0"
    enabled: bool = True

    def to_dict(self) -> dict:
        return {
            "_type": "knowledge",
            "knowledge_type": self.knowledge_type,
            "key": self.key,
            "priority": self.priority,
            "language": self.language,
            "module_type": self.module_type,
            "phase": self.phase,
            "content": self.content,
            "tags": self.tags,
            "version": self.version,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "KnowledgeEntry":
        return cls(
            knowledge_type=data.get("knowledge_type", "governance_rule"),
            key=data.get("key", "unknown"),
            priority=int(data.get("priority", 500)),
            language=data.get("language", "*"),
            module_type=data.get("module_type", "*"),
            phase=data.get("phase", "*"),
            content=data.get("content", ""),
            tags=data.get("tags", []),
            version=data.get("version", "1.0"),
            enabled=data.get("enabled", True),
        )


def _build_seed_knowledge() -> list[KnowledgeEntry]:
    """Build complete knowledge base from project rules + Caura principles."""
    e: list[KnowledgeEntry] = []

    # Layer 0: Privacy & Provenance (priority 1000)
    e.append(KnowledgeEntry("governance_rule", "privacy.no_source_to_llm", 1000, "*", "*", "*",
        "PRIVACY BOUNDARY [R09]: Never send full source code to external LLM. Send only sanitized error messages, line numbers, RCA categories, and fix directives. Strip file paths, variable names, and business logic. The intelligence asset is the governed memory, not the vendor model.",
        ["privacy", "ownership", "llm-boundary", "R09"]))
    e.append(KnowledgeEntry("governance_rule", "privacy.no_secrets_in_output", 1000, "*", "*", "*",
        "SECURITY [I6]: No secrets in repo. No API keys, passwords, tokens, IP addresses, or internal paths in generated code or logs. Use environment variables. No stack traces to external clients.",
        ["enforce", "privacy", "security", "I6"]))
    e.append(KnowledgeEntry("governance_rule", "privacy.sanitize_errors", 1000, "*", "*", "repair",
        "REPAIR PRIVACY [R06,R09]: Before sending errors to LLM, strip file paths, replace project-specific identifiers with generic placeholders, limit context to failing lines only. Every memory record must have provenance.",
        ["privacy", "repair", "provenance", "R06"]))
    e.append(KnowledgeEntry("governance_rule", "memory.provenance_policy", 1000, "*", "*", "learning",
        "MEMORY GOVERNANCE [R06]: Demand provenance on every record. Expiry on aging facts. Correction workflow propagates. Conflict detection surfaced not averaged. Deletion actually deletes. Treat store like database with DBA.",
        ["memory", "governance", "R06"]))

    # Layer 1: Project Constitution (priority 900)
    e.append(KnowledgeEntry("governance_rule", "constitution.agent_ownership", 900, "*", "*", "*",
        "OWNERSHIP [R02,I2]: One owner per unit of work. Language routing: Python=agents/intelligence, Go=transfer/network, Rust=compute/speed. If answer to who owns this is everyone you have an orphan.",
        ["ownership", "architecture", "R02", "I2"]))
    e.append(KnowledgeEntry("governance_rule", "constitution.error_handling", 900, "*", "*", "*",
        "ERROR CONTRACT [I3]: All cross-service failures MUST use ErrorEnvelope. Stable codes: VAL_, AUTH_, BIZ_, DEP_, RES_, NET_, INT_. Retry only when retryable=true. No panic/unwrap/expect/bare except/ignored err. Consumers key off code+retryable only.",
        ["enforce", "errors", "contracts", "I3"]))
    e.append(KnowledgeEntry("governance_rule", "constitution.contract_first", 900, "*", "*", "generation",
        "CONTRACT FIRST [R04,I1]: Define API/message/error contracts before implementation. One tool layer called identically everywhere. Skills bolted onto unverified substrate industrialize errors.",
        ["architecture", "contracts", "R04", "I1"]))
    e.append(KnowledgeEntry("governance_rule", "constitution.action_gate", 900, "*", "*", "*",
        "ACTION GATE [R08]: Measure then Analyze then Act. Stage 1: every outward move behind a gate. Autonomy expanded per action type as auditable policy not a vibe. Irreversible actions are not callable tools.",
        ["governance", "safety", "R08"]))
    e.append(KnowledgeEntry("governance_rule", "constitution.substrate_first", 900, "*", "*", "*",
        "SUBSTRATE BEFORE SKILLS [R07]: Verify data layer before adding intelligence. If substrate lies every skill industrializes lying faster. Boring first then agents propose moves.",
        ["architecture", "R07"]))
    e.append(KnowledgeEntry("governance_rule", "constitution.logging", 900, "*", "*", "*",
        "OBSERVABILITY [I5]: Structured logs: service, trace_id, span_id, code, duration_ms. Context/deadline/cancellation propagates edge to leaf. Graceful shutdown. Health: liveness vs readiness separated.",
        ["logging", "observability", "I5"]))
    e.append(KnowledgeEntry("governance_rule", "constitution.deterministic", 900, "*", "*", "*",
        "DETERMINISM: Same input equals same output. No random seeds without config. Idempotency required for writes. Deadlines propagate; remaining time honored [I5].",
        ["determinism", "testing", "I5"]))

    # Layer 2: Language Standards (priority 800)
    e.append(KnowledgeEntry("language_standard", "rust.coding_standard", 800, "rust", "*", "*",
        "RUST STANDARDS [COMPUTE]: Result<T,E> on request path no unwrap/expect/panic. checked_add/checked_mul. thiserror for errors. Bounded channels. No hidden globals. Small functions under 50 lines. Clippy clean. Proper ownership/lifetime.",
        ["enforce", "rust", "standards", "compute"]))
    e.append(KnowledgeEntry("language_standard", "go.coding_standard", 800, "go", "*", "*",
        "GO STANDARDS [TRANSFER]: Percent-w wrapping on errors. context.Context on every RPC/IO. Client timeouts. No goroutine leaks. No ignored err. gofmt/go vet clean. Worker pools with backpressure. Graceful shutdown.",
        ["enforce", "go", "standards", "transfer"]))
    e.append(KnowledgeEntry("language_standard", "python.coding_standard", 800, "python", "*", "*",
        "PYTHON STANDARDS [INTELLIGENCE]: Type hints on all signatures. No bare except. No eval/exec. Explicit exception types. pathlib over os.path. dataclasses for structured data. logging not print. AppError domain exceptions. Deterministic tests.",
        ["enforce", "python", "standards", "intelligence"]))
    e.append(KnowledgeEntry("language_standard", "architecture.single_responsibility", 800, "*", "*", "*",
        "SINGLE RESPONSIBILITY [R05]: One bounded agent per credential set. Split only when tools permissions or evaluations diverge. Narrow agents have small blast radius. Fleet is destination not starting point.",
        ["architecture", "R05"]))
    e.append(KnowledgeEntry("language_standard", "architecture.honest_failure", 800, "*", "*", "*",
        "HONEST FAILURE [R10]: Connectors self-test on load. Reports print caveats next to numbers. Failure states honest visible boring. Plan for connector failure enrichment mismatch agent reaching past brief.",
        ["architecture", "resilience", "R10"]))

    # Layer 4: LLM Interaction Rules (priority 750)
    e.append(KnowledgeEntry("llm_interaction_rule", "llm.generation_rules", 750, "*", "*", "generation",
        "GENERATION: Produce complete compilable code. All imports included. Follow language standards. Add structured logging. Handle all errors explicitly. No placeholder comments. No drive-by refactors. Match existing style.",
        ["llm", "generation"]))
    e.append(KnowledgeEntry("llm_interaction_rule", "llm.repair_rules", 750, "*", "*", "repair",
        "REPAIR: Fix ONLY reported errors. Do not rewrite working code. Preserve style. Phase A compile errors first. Phase B after compile passes address warnings. Output complete file. Minimal diff. No unrelated cleanup.",
        ["llm", "repair"]))
    e.append(KnowledgeEntry("llm_interaction_rule", "llm.delta_repair_rules", 750, "*", "*", "delta_repair",
        "DELTA REPAIR: You receive ONLY failing lines with plus-minus 3 context. Fix only those lines. Respond JSON with operations array and confidence float. Ops: replace_lines insert_after delete_lines append. Do NOT include code outside specified range. Preserve indentation.",
        ["llm", "delta_repair"]))
    e.append(KnowledgeEntry("llm_interaction_rule", "llm.adversarial_rules", 750, "*", "*", "adversarial",
        "ADVERSARIAL REVIEW: You are a hostile reviewer. Find edge cases overflow risks security gaps missing error handling. Output JSON findings array. Each finding has severity description suggested_fix. Do NOT see source code only structural description and sanitized errors.",
        ["llm", "adversarial"]))

    # Layer 5: Learning Policy (priority 650)
    e.append(KnowledgeEntry("learning_policy", "learning.scorecard_policy", 650, "*", "*", "learning",
        "SCORECARD [R01]: Define metrics before building. Measure accuracy adoption hours-saved exception-rate. Agent saving 10 hours but shipping 1 wrong result is net negative. Scorecard must see both value and risk.",
        ["learning", "metrics", "R01"]))
    e.append(KnowledgeEntry("learning_policy", "learning.anti_pattern_promotion", 650, "*", "*", "learning",
        "ANTI-PATTERN POLICY: When error repeats 2+ times with quality_delta=0 promote to anti-pattern. When strategy fails 3+ times switch strategy. Unknown category triggers RCA before storage. Never store source code.",
        ["learning", "anti-pattern"]))
    e.append(KnowledgeEntry("learning_policy", "learning.strategy_switching", 650, "*", "*", "learning",
        "STRATEGY SWITCHING: If same strategy produces quality_delta=0 for 2 consecutive attempts switch patch to rewrite or rewrite to patch. Delta repair attempted before full regeneration. Adversarial findings only after compile passes.",
        ["learning", "strategy"]))

    return e
