"""
Base agent class.

Agentic loop pattern:
  1. Send messages to Claude with tool definitions (from the agent + all loaded skills).
  2. If Claude responds with tool_use blocks, route them to the right handler.
  3. Repeat until Claude returns a plain text response (stop_reason == "end_turn").

Skills extend an agent's capabilities without changing its core loop:
  - agent.load_skill(skill)   → merges tools + injects prompt module
  - agent.delegate_to(other)  → sub-agent call (agent-to-agent)
"""

import logging
import os
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

import anthropic

if TYPE_CHECKING:
    from ..skills.base import Skill

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-opus-4-5"


class BaseAgent(ABC):
    """Abstract base for all fleet management agents."""

    def __init__(
        self,
        name: str,
        system_prompt: str,
        tools: list[dict],
        model: str = DEFAULT_MODEL,
        max_tokens: int = 4096,
        max_iterations: int = 10,
    ) -> None:
        self.name = name
        self._base_system_prompt = system_prompt
        self._base_tools = tools
        self.model = model
        self.max_tokens = max_tokens
        self.max_iterations = max_iterations
        self._skills: list["Skill"] = []
        self._client = anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    # ------------------------------------------------------------------
    # Skill management
    # ------------------------------------------------------------------

    def load_skill(self, skill: "Skill") -> None:
        """Attach a skill to this agent, merging its tools and prompt module."""
        self._skills.append(skill)
        logger.info("[%s] Loaded skill: %s", self.name, skill.name)

    def load_skills(self, skills: list["Skill"]) -> None:
        for skill in skills:
            self.load_skill(skill)

    @property
    def tools(self) -> list[dict]:
        """All tools: agent's own + every loaded skill's tools."""
        skill_tools = [t for skill in self._skills for t in skill.tools]
        return self._base_tools + skill_tools

    @property
    def system_prompt(self) -> str:
        """Base system prompt + prompt modules from every loaded skill."""
        modules = "\n".join(skill.prompt_module for skill in self._skills if skill.prompt_module)
        return f"{self._base_system_prompt}\n{modules}".strip()

    def loaded_skills(self) -> list[str]:
        return [s.name for s in self._skills]

    # ------------------------------------------------------------------
    # Sub-agent delegation
    # ------------------------------------------------------------------

    async def delegate_to(self, agent: "BaseAgent", task: str) -> str:
        """
        Delegate a task to another agent and return its text response.
        Useful for orchestrator → sub-agent or agent → specialist agent calls.
        """
        logger.info("[%s] Delegating to [%s]: %s", self.name, agent.name, task[:100])
        return await agent.run(task)

    # ------------------------------------------------------------------
    # Tool routing
    # ------------------------------------------------------------------

    @abstractmethod
    async def handle_own_tool_call(self, tool_name: str, tool_input: dict[str, Any]) -> str:
        """Handle tool calls that belong to this agent (not skills)."""

    async def handle_tool_call(self, tool_name: str, tool_input: dict[str, Any]) -> str:
        """Route a tool call to the owning skill or this agent's own handler."""
        for skill in self._skills:
            if skill.owns_tool(tool_name):
                logger.info("[%s] Skill '%s' handling tool: %s", self.name, skill.name, tool_name)
                return skill.handle_tool_call(tool_name, tool_input)
        return await self.handle_own_tool_call(tool_name, tool_input)

    # ------------------------------------------------------------------
    # Agentic loop
    # ------------------------------------------------------------------

    async def run(self, user_message: str) -> str:
        """
        Run the agentic loop for a single task.
        Returns the final text response from Claude once it stops requesting tools.
        """
        messages: list[dict] = [{"role": "user", "content": user_message}]
        logger.info("[%s] Starting run. Skills: %s. Task: %s", self.name, self.loaded_skills(), user_message[:100])

        for iteration in range(self.max_iterations):
            response = await self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=self.system_prompt,
                tools=self.tools,
                messages=messages,
            )

            logger.debug("[%s] Iteration %d — stop_reason: %s", self.name, iteration, response.stop_reason)

            assistant_content = [block.model_dump() for block in response.content]
            messages.append({"role": "assistant", "content": assistant_content})

            if response.stop_reason == "end_turn":
                for block in response.content:
                    if block.type == "text":
                        logger.info("[%s] Finished after %d iteration(s).", self.name, iteration + 1)
                        return block.text
                return ""

            if response.stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        logger.info("[%s] Tool call: %s", self.name, block.name)
                        result = await self.handle_tool_call(block.name, block.input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })
                messages.append({"role": "user", "content": tool_results})

        logger.warning("[%s] Reached max iterations (%d).", self.name, self.max_iterations)
        return "Max iterations reached without a final answer."
