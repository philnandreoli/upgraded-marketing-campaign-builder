"""
Marketing Campaign Builder — Agent registry.

.. deprecated::
    This package is a backward-compatibility shim.  All runtime code should
    import agents directly from ``backend.orchestration``, e.g.::

        from backend.orchestration.strategy_agent import StrategyAgent

    The shim re-exports the canonical classes for convenience; do not rely on
    it for new code.
"""

from backend.orchestration.base_agent import BaseAgent
from backend.orchestration.strategy_agent import StrategyAgent
from backend.orchestration.content_creator_agent import ContentCreatorAgent
from backend.orchestration.channel_planner_agent import ChannelPlannerAgent
from backend.orchestration.analytics_agent import AnalyticsAgent
from backend.orchestration.review_qa_agent import ReviewQAAgent
from backend.orchestration.scheduling_agent import SchedulingAgent
from backend.orchestration.coordinator_agent import CoordinatorAgent

__all__ = [
    "BaseAgent",
    "StrategyAgent",
    "ContentCreatorAgent",
    "ChannelPlannerAgent",
    "AnalyticsAgent",
    "ReviewQAAgent",
    "SchedulingAgent",
    "CoordinatorAgent",
]