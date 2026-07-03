"""Single-turn specialist agent used for fleet subtasks without tools."""

from __future__ import annotations

from typing import Any, Optional

from openjarvis.agents._stubs import AgentContext, AgentResult, BaseAgent
from openjarvis.core.registry import AgentRegistry


@AgentRegistry.register("fleet_specialist")
class FleetSpecialistAgent(BaseAgent):
    """Like ``SimpleAgent`` but with a per-role system prompt.

    Fleet roles that declare tools are run through ``OrchestratorAgent``
    instead; this class covers the (cheap, fast) pure-LLM specialists.
    """

    agent_id = "fleet_specialist"

    def __init__(
        self, engine: Any, model: str, *, system_prompt: str = "", **kwargs: Any
    ) -> None:
        super().__init__(engine, model, **kwargs)
        self._system_prompt = system_prompt

    def run(
        self,
        input: str,
        context: Optional[AgentContext] = None,
        **kwargs: Any,
    ) -> AgentResult:
        self._emit_turn_start(input)
        messages = self._build_messages(
            input, context, system_prompt=self._system_prompt or None
        )
        result = self._generate(messages)
        content = self._strip_think_tags(result.get("content", "") or "")
        self._emit_turn_end(content_length=len(content))
        usage = result.get("usage") or {}
        return AgentResult(content=content, turns=1, metadata={"usage": usage})


__all__ = ["FleetSpecialistAgent"]
