"""
Skill base class.

A Skill is a self-contained capability that can be loaded into any agent.
It contributes three things:
  1. tools         — Anthropic tool schemas Claude can call
  2. prompt_module — Domain expertise injected into the agent's system prompt
  3. handle_tool_call — Executes the tool and returns a JSON string result

Usage:
    agent.load_skill(WeatherSkill())
    agent.load_skill(DemandForecastingSkill())
"""

from abc import ABC, abstractmethod
from typing import Any


class Skill(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this skill."""

    @property
    @abstractmethod
    def description(self) -> str:
        """One-line description shown in logs and the agent system prompt."""

    @property
    def tools(self) -> list[dict]:
        """Anthropic tool schemas this skill exposes. Override to add tools."""
        return []

    @property
    def prompt_module(self) -> str:
        """
        Extra instructions injected into the agent's system prompt when this
        skill is loaded. Override to give Claude domain expertise.
        """
        return ""

    @abstractmethod
    def handle_tool_call(self, tool_name: str, tool_input: dict[str, Any]) -> str:
        """Execute a tool call and return the result as a JSON string."""

    def owns_tool(self, tool_name: str) -> bool:
        """Return True if this skill owns the given tool name."""
        return any(t["name"] == tool_name for t in self.tools)
