# atlas_agent/access_control.py
"""Atlas AI Access Control Layer."""
from __future__ import annotations
import hashlib, logging, time
from enum import StrEnum
from pydantic import BaseModel, ConfigDict, Field
logger = logging.getLogger('atlas_agent.access_control')

class UserTier(StrEnum):
    STANDARD = 'standard'
    PRO = 'pro'
    PROFESSIONAL = 'professional'

class UserIdentity(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    user_id: str
    tier: UserTier
    api_key_hash: str
    created_at: float = Field(default_factory=time.time)
    max_concurrent_pipelines: int = 1
    allowed_languages: tuple[str, ...] = ('python',)
    @staticmethod
    def hash_api_key(raw_key: str) -> str:
        return hashlib.sha256(raw_key.encode('utf-8')).hexdigest()

class TierCapabilities(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    tier: UserTier
    can_request_implementation: bool
    can_use_multi_module: bool
    can_use_delta_repair: bool
    can_read_portable_memory: bool
    can_query_strategy_confidence: bool
    can_select_language: tuple[str, ...]
    max_modules_per_request: int
    max_prompt_length: int
    requires_scaffold_markers_for_restricted: bool

TIER_CAPABILITIES: dict[UserTier, TierCapabilities] = {
    UserTier.STANDARD: TierCapabilities(tier=UserTier.STANDARD, can_request_implementation=False, can_use_multi_module=False, can_use_delta_repair=False, can_read_portable_memory=False, can_query_strategy_confidence=False, can_select_language=('python',), max_modules_per_request=1, max_prompt_length=2000, requires_scaffold_markers_for_restricted=True),
    UserTier.PRO: TierCapabilities(tier=UserTier.PRO, can_request_implementation=True, can_use_multi_module=True, can_use_delta_repair=True, can_read_portable_memory=False, can_query_strategy_confidence=False, can_select_language=('python','go','rust'), max_modules_per_request=4, max_prompt_length=8000, requires_scaffold_markers_for_restricted=True),
    UserTier.PROFESSIONAL: TierCapabilities(tier=UserTier.PROFESSIONAL, can_request_implementation=True, can_use_multi_module=True, can_use_delta_repair=True, can_read_portable_memory=True, can_query_strategy_confidence=True, can_select_language=('python','go','rust'), max_modules_per_request=8, max_prompt_length=16000, requires_scaffold_markers_for_restricted=False),
}

PROTECTED_PATHS: frozenset[str] = frozenset({'contracts/','configs/','.git/','.githooks/','.husky/','core_engine/','intelligence/','services/','atlas_agent/restriction_guard.py','atlas_agent/governance.py','atlas_agent/access_control.py','atlas_agent/models.py','atlas_agent/orchestrator.py','CONSTITUTION.md'})
FORBIDDEN_ACTIONS: frozenset[str] = frozenset({'modify_contract','modify_schema','modify_governance','read_source_code','write_source_code','delete_file','execute_shell','access_filesystem','change_tier','modify_access_control','export_portable_memory','alter_seed_knowledge'})

class AccessDecision(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    allowed: bool
    tier: UserTier
    reason: str
    requested_action: str
    timestamp: float = Field(default_factory=time.time)

class AccessGate:
    def __init__(self) -> None:
        self._audit_log: list[AccessDecision] = []
        logger.info('AccessGate initialized: %d tiers, %d protected paths, %d forbidden actions', len(TIER_CAPABILITIES), len(PROTECTED_PATHS), len(FORBIDDEN_ACTIONS))
    def get_capabilities(self, tier: UserTier) -> TierCapabilities:
        return TIER_CAPABILITIES[tier]
    def check_action(self, user: UserIdentity, action: str) -> AccessDecision:
        if action in FORBIDDEN_ACTIONS:
            d = AccessDecision(allowed=False, tier=user.tier, reason=f'SECURITY GATE: Action {action!r} prohibited for ALL tiers. Operator authorization required. Logged.', requested_action=action)
            self._audit_log.append(d)
            logger.warning('ACCESS DENIED: user=%s tier=%s action=%s', user.user_id, user.tier.value, action)
            return d
        caps = TIER_CAPABILITIES[user.tier]
        m = {'request_scaffold': True, 'request_implementation': caps.can_request_implementation, 'use_multi_module': caps.can_use_multi_module, 'use_delta_repair': caps.can_use_delta_repair, 'read_portable_memory': caps.can_read_portable_memory, 'query_strategy_confidence': caps.can_query_strategy_confidence}
        ok = m.get(action, False)
        d = AccessDecision(allowed=ok, tier=user.tier, reason=f'AUTHORIZED: {user.tier.value} permits {action}.' if ok else f'ACCESS DENIED: {action!r} requires higher tier. Current: {user.tier.value}. Upgrade to unlock.', requested_action=action)
        self._audit_log.append(d)
        return d
    def check_path_access(self, user: UserIdentity, path: str) -> AccessDecision:
        n = path.removeprefix('/').removeprefix('./')
        for p in PROTECTED_PATHS:
            if n.startswith(p.rstrip('/')):
                d = AccessDecision(allowed=False, tier=user.tier, reason=f'SECURITY GATE: Path {path!r} is protected infrastructure. No user tier has access. Quarantined.', requested_action=f'path:{path}')
                self._audit_log.append(d)
                logger.warning('PATH BLOCKED: user=%s path=%s', user.user_id, path)
                return d
        return AccessDecision(allowed=True, tier=user.tier, reason='Path within scope.', requested_action=f'path:{path}')
    def check_language_allowed(self, user: UserIdentity, language: str) -> AccessDecision:
        caps = TIER_CAPABILITIES[user.tier]
        if language in caps.can_select_language:
            return AccessDecision(allowed=True, tier=user.tier, reason=f'Language {language!r} authorized.', requested_action=f'lang:{language}')
        d = AccessDecision(allowed=False, tier=user.tier, reason=f'ACCESS DENIED: Language {language!r} unavailable for {user.tier.value}. Allowed: {caps.can_select_language}.', requested_action=f'lang:{language}')
        self._audit_log.append(d)
        return d
    def validate_requirement(self, user: UserIdentity, description: str, language: str, modules: list[str], target_folder: str) -> AccessDecision:
        pd = self.check_path_access(user, target_folder)
        if not pd.allowed: return pd
        ld = self.check_language_allowed(user, language)
        if not ld.allowed: return ld
        caps = TIER_CAPABILITIES[user.tier]
        if len(modules) > caps.max_modules_per_request:
            d = AccessDecision(allowed=False, tier=user.tier, reason=f'LIMIT EXCEEDED: {len(modules)} modules, max {caps.max_modules_per_request} for {user.tier.value}.', requested_action='multi_module')
            self._audit_log.append(d); return d
        if len(description) > caps.max_prompt_length:
            d = AccessDecision(allowed=False, tier=user.tier, reason=f'LIMIT EXCEEDED: Prompt {len(description)} chars exceeds {caps.max_prompt_length} limit for {user.tier.value}.', requested_action='prompt_length')
            self._audit_log.append(d); return d
        is_scaffold = any(kw in description.lower() for kw in ['scaffold','stub','definition only','do not implement'])
        if not is_scaffold and not caps.can_request_implementation:
            d = AccessDecision(allowed=False, tier=user.tier, reason='TIER RESTRICTION: Implementation requires Pro+ tier. Standard supports scaffold-only. Add scaffold directives or upgrade.', requested_action='request_implementation')
            self._audit_log.append(d); return d
        d = AccessDecision(allowed=True, tier=user.tier, reason=f'AUTHORIZED: All checks passed for {user.tier.value}. Pipeline approved.', requested_action='run_pipeline')
        self._audit_log.append(d)
        logger.info('ACCESS GRANTED: user=%s tier=%s lang=%s modules=%d', user.user_id, user.tier.value, language, len(modules))
        return d
    def get_audit_log(self) -> list[AccessDecision]:
        return list(self._audit_log)
