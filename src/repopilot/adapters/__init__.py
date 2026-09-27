"""Coding-agent adapter interfaces."""

from .base import AgentAdapter, AgentRunResult
from .mini_swe import MiniSWEAgentAdapter

__all__ = [
    "AgentAdapter",
    "AgentRunResult",
    "MiniSWEAgentAdapter",
]
