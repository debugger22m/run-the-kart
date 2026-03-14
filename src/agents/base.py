"""
Base agent class.

All agents share the same async Anthropic client and agentic loop pattern:
  1. Send messages to Claude with tool definitions.
  2. If Claude responds with tool_use blocks, execute them and feed results back.
  3. Repeat until Claude returns a plain text response (stop_reason == "end_turn").
"""

import json
import logging
import os
from abc import ABC, abstractmethod
from typing import Any

import anthropic

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
        self.system_prompt = system_prompt
        self.tools = tools
        self.model = model
        self.max_tokens = max_tokens
        self.max_iterations = max_iterations
        self._client = anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    @abstractmethod
    async def handle_tool_call(self, tool_name: str, tool_input: dict[str, Any]) -> str:
        """Execute a tool and return the result as a JSON string."""

    async def run(self, user_message: str) -> str:
        """
        Run the agentic loop for a single task.

        Returns the final text response from Claude once it stops requesting tools.
        """
        messages: list[dict] = [{"role": "user", "content": user_message}]
        logger.info("[%s] Starting run. Task: %s", self.name, user_message[:120])

        for iteration in range(self.max_iterations):
            response = await self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=self.system_prompt,
                tools=self.tools,
                messages=messages,
            )

            logger.debug("[%s] Iteration %d — stop_reason: %s", self.name, iteration, response.stop_reason)

            # Collect all content blocks into the conversation history
            assistant_content = [block.model_dump() for block in response.content]
            messages.append({"role": "assistant", "content": assistant_content})

            if response.stop_reason == "end_turn":
                # Extract the final text reply
                for block in response.content:
                    if block.type == "text":
                        logger.info("[%s] Finished after %d iteration(s).", self.name, iteration + 1)
                        return block.text
                return ""

            if response.stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        logger.info("[%s] Calling tool: %s", self.name, block.name)
                        result = await self.handle_tool_call(block.name, block.input)
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": result,
                            }
                        )

                messages.append({"role": "user", "content": tool_results})

        logger.warning("[%s] Reached max iterations (%d).", self.name, self.max_iterations)
        return "Max iterations reached without a final answer."
