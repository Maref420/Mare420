"""
Agent Context Builder — Aggregates sensory agent signals into AgentContext.

Bridges the gap between raw AgentSignals from News/Social/Wallet agents
and the AgentContext consumed by Strategy Evaluators.

Governed by:
- SE-4: Agent Cross-Validation
- Rule 12: Minimal Blast Radius
"""
from __future__ import annotations

from intelligence.sensory_agents.models import AgentSignal, AgentType
from intelligence.sensory_agents.news_agent import merge_news_signals_into_context
from intelligence.sensory_agents.social_agent import merge_social_signals_into_context
from intelligence.sensory_agents.wallet_agent import compute_wallet_context
from intelligence.strategy_intelligence.strategy_evaluator.base import AgentContext


class AgentContextBuilder:
    """
    Collects signals from all sensory agents and builds a unified
    AgentContext for strategy evaluation.
    """

    @staticmethod
    def build(signals: list[AgentSignal]) -> AgentContext:
        """
        Build AgentContext from a collection of agent signals.

        Groups signals by agent type, aggregates each group using
        type-specific merge functions, and constructs frozen AgentContext.

        Args:
            signals: List of AgentSignal from all sensory agents.

        Returns:
            Frozen AgentContext ready for strategy evaluators.
        """
        news_signals: list[AgentSignal] = []
        social_signals: list[AgentSignal] = []
        wallet_signals: list[AgentSignal] = []

        for sig in signals:
            if sig.agent_type == AgentType.NEWS:
                news_signals.append(sig)
            elif sig.agent_type == AgentType.SOCIAL:
                social_signals.append(sig)
            elif sig.agent_type == AgentType.WALLET:
                wallet_signals.append(sig)

        news_sentiment = merge_news_signals_into_context(news_signals)
        social_hype = merge_social_signals_into_context(social_signals)
        whale_flow, exchange_inflow = compute_wallet_context(wallet_signals)

        return AgentContext(
            news_sentiment=news_sentiment,
            social_hype=social_hype,
            wallet_whale_flow=whale_flow,
            wallet_exchange_inflow=exchange_inflow,
        )
