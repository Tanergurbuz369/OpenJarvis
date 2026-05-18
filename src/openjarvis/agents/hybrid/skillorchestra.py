"""SkillOrchestraAgent — inference-time router (Wang et al., 2026).

Paper: arXiv:2602.19672. The published pipeline is four phases — explore
(run every pool model, collect traces), learn (induce a skill handbook
with per-agent Beta competences and per-skill cost stats), select (Pareto-
optimal handbook subset on a live val set), test. At deployment, the
orchestrator reads the user query, infers skill demands, then picks the
agent that maximizes weighted competence minus λ·cost.

What we reproduce here: the **deployment-time** step only. The full
explore/learn/select pipeline requires multi-model serving + the FRAMES
wiki retriever + a multi-hour LLM-driven learning loop that's out of
scope for the OpenJarvis port (and was out of scope in the hybrid harness).

So this agent uses the orchestrator's *inference logic* with a small
handbook that's synthesized per-task on the fly: cloud (Opus) reads the
question, identifies which skills it needs (from a fixed catalog),
assigns weights, scores each of our two agents (local Qwen-27B vs
cloud Opus) under a cost-discounted weighted-competence rule, then
routes. The chosen agent answers the question.

Hybrid harness result (n=30 GAIA): ``skillorchestra-gaia-qwen27b-opus-30``
= 0.500 acc, $0.02/task — 30× cheaper than baseline-cloud (0.567 / $0.66)
for ~7pp lower accuracy. Best cost-efficient GAIA paradigm by a wide
margin.

Ported from ``hybrid-local-cloud-compute/adapters/skillorchestra_adapter.py``.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from openjarvis.agents._stubs import AgentContext
from openjarvis.agents.hybrid._base import (
    WEB_SEARCH_COST_PER_CALL,
    LocalCloudAgent,
    build_web_search_tool,
    web_search_cfg,
)
from openjarvis.agents.hybrid._prices import supports_temperature
from openjarvis.agents.hybrid.mini_swe_agent import run_swe_agent_loop
from openjarvis.core.registry import AgentRegistry

# ---------- Skill catalog (compact, GAIA-relevant) ----------
#
# SkillOrchestra learns its taxonomy from execution traces. Without traces
# we use a hand-curated taxonomy covering the kinds of competences GAIA
# actually exercises. Per-agent competences are fixed priors calibrated to
# typical Qwen3.5-27B-FP8 vs cloud-model behavior — what a 1-iteration learn
# would seed before any oracle update.

SKILL_CATALOG: Dict[str, str] = {
    "factual_recall":     "Recall named entities, dates, places, well-known facts from training data without external lookup.",
    "multi_step_reasoning": "Chain several inference steps together (e.g. compose dates, traverse relationships, decompose then aggregate).",
    "arithmetic":         "Exact numeric computation on values already given in the question.",
    "web_grounding":      "Question needs information likely NOT in a small model's parametric memory (rare facts, recent events, niche sources).",
    "long_text_extraction": "Read a long supplied document/context and extract a specific piece.",
    "format_compliance":  "Strict output formatting (e.g. GAIA's `FINAL ANSWER: <answer>` rule, comma-separated lists with no units).",
    "code_or_logic":      "Write or trace code, or apply logical/symbolic constraints precisely.",
}

# Competence priors for the *local* student (Qwen3.5-27B-FP8). Calibrated
# so that on skill mixes where small models genuinely shine (strict format
# compliance, arithmetic on supplied values, short factual extraction), the
# local agent can plausibly beat a cloud model net of cost. Web-grounding /
# multi-step reasoning stay low — those are the cloud's lane.
LOCAL_COMPETENCE_PRIOR: Dict[str, float] = {
    "factual_recall":       0.35,
    "multi_step_reasoning": 0.30,
    "arithmetic":           0.65,
    "web_grounding":        0.10,
    "long_text_extraction": 0.60,
    "format_compliance":    0.75,
    "code_or_logic":        0.50,
}

# Per-cloud-model competence priors. Tier roughly tracks the n=100 GAIA
# baseline accuracy gap (opus 0.60 ≫ gemini-pro 0.28 ≫ gpt-5 0.18 ≈ haiku
# 0.15 ≈ flash 0.16). Stronger models get higher ceilings; weaker / cheaper
# models get priors that overlap with the local floor on the right skill
# mix. Floors brought down to ~0.50 so local can win on format-heavy /
# arithmetic-heavy questions without cost penalty even helping.
_CLOUD_COMPETENCE_PRIORS: Dict[str, Dict[str, float]] = {
    "claude-opus-4-7": {
        "factual_recall":       0.85,
        "multi_step_reasoning": 0.88,
        "arithmetic":           0.80,
        "web_grounding":        0.70,
        "long_text_extraction": 0.88,
        "format_compliance":    0.85,
        "code_or_logic":        0.88,
    },
    "claude-haiku-4-5": {
        "factual_recall":       0.65,
        "multi_step_reasoning": 0.55,
        "arithmetic":           0.65,
        "web_grounding":        0.55,
        "long_text_extraction": 0.70,
        "format_compliance":    0.78,
        "code_or_logic":        0.65,
    },
    "gpt-5": {
        "factual_recall":       0.75,
        "multi_step_reasoning": 0.78,
        "arithmetic":           0.75,
        "web_grounding":        0.60,
        "long_text_extraction": 0.80,
        "format_compliance":    0.78,
        "code_or_logic":        0.82,
    },
    "gpt-5-mini": {
        "factual_recall":       0.60,
        "multi_step_reasoning": 0.55,
        "arithmetic":           0.65,
        "web_grounding":        0.50,
        "long_text_extraction": 0.70,
        "format_compliance":    0.72,
        "code_or_logic":        0.65,
    },
    "gemini-2.5-pro": {
        "factual_recall":       0.75,
        "multi_step_reasoning": 0.78,
        "arithmetic":           0.75,
        "web_grounding":        0.65,
        "long_text_extraction": 0.85,
        "format_compliance":    0.75,
        "code_or_logic":        0.78,
    },
    "gemini-2.5-flash": {
        "factual_recall":       0.60,
        "multi_step_reasoning": 0.55,
        "arithmetic":           0.62,
        "web_grounding":        0.55,
        "long_text_extraction": 0.75,
        "format_compliance":    0.70,
        "code_or_logic":        0.62,
    },
}

# Fallback prior for any cloud model not in the table above. Conservative
# mid-tier — slightly above local on every skill, no extreme highs.
_GENERIC_CLOUD_COMPETENCE: Dict[str, float] = {
    "factual_recall":       0.70,
    "multi_step_reasoning": 0.65,
    "arithmetic":           0.70,
    "web_grounding":        0.55,
    "long_text_extraction": 0.75,
    "format_compliance":    0.75,
    "code_or_logic":        0.70,
}

# Empirical per-task USD cost on GAIA n=100 (from cloud-only-*-gaia-n100/
# summary.json, 2026-05-17). Local Qwen at $0 — vLLM is GPU-amortized.
# Router uses these as the "avg cost" reference in its prompt; the cost
# penalty in `_score_agents` multiplies by `lambda_cost` (default 2.0).
MODEL_COST_USD_PER_TASK: Dict[str, float] = {
    "Qwen/Qwen3.5-27B-FP8":         0.0,
    "claude-opus-4-7":              0.014,
    "claude-haiku-4-5":             0.002,
    "claude-haiku-4-5-20251001":    0.002,
    "gpt-5":                        0.025,
    "gpt-5-mini":                   0.003,
    "gpt-5-mini-2025-08-07":        0.003,
    "gemini-2.5-pro":               0.002,
    "gemini-2.5-flash":             0.0006,
    "gemini-2.5-flash-lite":        0.0002,
}


def _cloud_competence_for(model: str) -> Dict[str, float]:
    """Look up cloud competence prior; fall back to generic mid-tier."""
    return dict(_CLOUD_COMPETENCE_PRIORS.get(model, _GENERIC_CLOUD_COMPETENCE))


def _cloud_cost_for(model: str) -> float:
    """Empirical avg per-task USD for the named cloud model. 0 if unknown
    (treats unknown models as free — caller should add them to the table)."""
    return MODEL_COST_USD_PER_TASK.get(model, 0.0)


def _default_agent_competence(local_model: str, cloud_model: str) -> Dict[str, Dict[str, float]]:
    """Build per-cell competence dict keyed by `local-<model>` / `cloud-<model>`."""
    return {
        f"local-{local_model}": dict(LOCAL_COMPETENCE_PRIOR),
        f"cloud-{cloud_model}": _cloud_competence_for(cloud_model),
    }


def _default_agent_cost(local_model: str, cloud_model: str) -> Dict[str, float]:
    return {
        f"local-{local_model}": MODEL_COST_USD_PER_TASK.get(local_model, 0.0),
        f"cloud-{cloud_model}": _cloud_cost_for(cloud_model),
    }


# Kept for back-compat with any caller that imported the legacy two-agent
# default. New cells should rely on the per-cell builders above. Mirrors the
# pre-2026-05-17 hardcoded Qwen-27B / Opus-4-7 pair.
DEFAULT_AGENT_COMPETENCE: Dict[str, Dict[str, float]] = _default_agent_competence(
    "qwen-27b", "claude-opus-4-7"
)
DEFAULT_AGENT_COST_USD: Dict[str, float] = _default_agent_cost(
    "qwen-27b", "claude-opus-4-7"
)

DEFAULT_LAMBDA_COST: float = 2.0

ROUTER_SYS_MARKER = "<<SKILLORCHESTRA-ROUTER>>"


def _format_catalog() -> str:
    return "\n".join(f"- {sid}: {desc}" for sid, desc in SKILL_CATALOG.items())


def _format_agents(
    competence: Dict[str, Dict[str, float]],
    cost: Dict[str, float],
) -> str:
    lines: List[str] = []
    for aid in competence:
        comp = competence[aid]
        comp_str = ", ".join(f"{k}={v:.2f}" for k, v in comp.items())
        lines.append(f"- **{aid}** (avg cost ${cost.get(aid, 0.0):.4f}/task)")
        lines.append(f"  Skill competences: {comp_str}")
    return "\n".join(lines)


def _build_router_sys(
    competence: Dict[str, Dict[str, float]],
    cost: Dict[str, float],
    lambda_cost: float,
) -> str:
    return f"""{ROUTER_SYS_MARKER}
You are a skill-aware model router for a compound AI system (the SkillOrchestra deployment-time orchestrator). For each user question you must:

1. Assign weights over the skill catalog (numbers in [0, 1], summing to ~1.0). \
The weights reflect how much each skill matters for *this* question.
2. Score each candidate agent: score(agent) = sum_skill weight_skill * competence(agent, skill) - lambda_cost * avg_cost(agent), with lambda_cost = {lambda_cost:.2f}.
3. Pick the highest-scoring agent. Tie-break in favor of the cheaper agent.

Skill catalog:
{_format_catalog()}

Agent pool (with learned-prior competences and average costs):
{_format_agents(competence, cost)}

Respond with ONLY a JSON object: {{"chosen_agent": ..., "skill_weights": {{...}}, "reasoning": "..."}}. No prose outside JSON.
"""


def _build_router_schema(agent_ids: List[str]) -> Dict[str, Any]:
    return {
        "format": {
            "type": "json_schema",
            "schema": {
                "type": "object",
                "properties": {
                    "chosen_agent": {"type": "string", "enum": agent_ids},
                    "skill_weights": {
                        "type": "object",
                        "properties": {
                            sid: {"type": "number"} for sid in SKILL_CATALOG
                        },
                        "required": list(SKILL_CATALOG.keys()),
                        "additionalProperties": False,
                    },
                    "reasoning": {"type": "string"},
                },
                "required": ["chosen_agent", "skill_weights", "reasoning"],
                "additionalProperties": False,
            },
        }
    }


def _parse_router_json(text: str) -> Dict[str, Any]:
    s = (text or "").strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    start = s.find("{")
    if start == -1:
        raise ValueError(f"router emitted no JSON: {s[:200]!r}")
    depth = 0
    for i in range(start, len(s)):
        c = s[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return json.loads(s[start : i + 1])
    raise ValueError(f"router JSON not balanced: {s[:200]!r}")


def _score_agents(
    skill_weights: Dict[str, float],
    competence: Dict[str, Dict[str, float]],
    cost: Dict[str, float],
    lambda_cost: float = DEFAULT_LAMBDA_COST,
) -> Dict[str, Dict[str, float]]:
    scores: Dict[str, Dict[str, float]] = {}
    for aid, comps in competence.items():
        comp = sum(
            skill_weights.get(sid, 0.0) * comps.get(sid, 0.0)
            for sid in SKILL_CATALOG
        )
        cost_pen = lambda_cost * cost.get(aid, 0.0)
        scores[aid] = {
            "competence": comp,
            "cost_penalty": cost_pen,
            "final_score": comp - cost_pen,
        }
    return scores


def _merge_competence(
    defaults: Dict[str, Dict[str, float]],
    override: Optional[Dict[str, Dict[str, float]]],
) -> Dict[str, Dict[str, float]]:
    """Partial-merge: cell-supplied competences win per-agent / per-skill,
    everything else falls back to the per-cell defaults."""
    if not override:
        return defaults
    merged: Dict[str, Dict[str, float]] = {aid: dict(s) for aid, s in defaults.items()}
    for aid, skills in override.items():
        if aid not in merged:
            merged[aid] = {}
        merged[aid].update(skills or {})
    return merged


def _merge_cost(
    defaults: Dict[str, float],
    override: Optional[Dict[str, float]],
) -> Dict[str, float]:
    if not override:
        return defaults
    merged = dict(defaults)
    merged.update(override)
    return merged


@AgentRegistry.register("skillorchestra")
class SkillOrchestraAgent(LocalCloudAgent):
    """Inference-time skill-aware router. See module docstring."""

    agent_id = "skillorchestra"

    def _is_soft_failure(self, exc: BaseException) -> Optional[str]:
        # Empty/unbalanced router JSON — treat as soft failure to match the
        # hybrid adapter's behavior (matches `err=1` rows in the n=30 cell).
        if isinstance(exc, (ValueError, json.JSONDecodeError)):
            return f"{type(exc).__name__}: {str(exc)[:120]}"
        return None

    def _run_paradigm(
        self,
        input: str,
        context: Optional[AgentContext],
        **kwargs: Any,
    ) -> Tuple[str, Dict[str, Any]]:
        cfg = self._cfg
        question = input

        # Per-cell agent keys: `local-<local_model>` and `cloud-<cloud_model>`.
        # The router prompt now names the actually-configured cloud, so cost
        # and competence priors match what the cell will pay / call. Cells
        # can override either with `method_cfg.agent_competence` /
        # `method_cfg.agent_cost_usd` (partial overrides merge).
        local_key = f"local-{self._local_model}" if self._local_model else "local"
        cloud_key = f"cloud-{self._cloud_model}"

        defaults_competence = _default_agent_competence(
            self._local_model or "qwen-27b", self._cloud_model
        )
        defaults_cost = _default_agent_cost(
            self._local_model or "qwen-27b", self._cloud_model
        )
        competence: Dict[str, Dict[str, float]] = _merge_competence(
            defaults_competence, cfg.get("agent_competence")
        )
        cost: Dict[str, float] = _merge_cost(
            defaults_cost, cfg.get("agent_cost_usd")
        )
        lambda_cost: float = float(cfg.get("lambda_cost", DEFAULT_LAMBDA_COST))
        agent_ids = list(competence.keys())
        router_sys = _build_router_sys(competence, cost, lambda_cost)
        router_schema = _build_router_schema(agent_ids)

        # 1. Route — uses Anthropic's output_config schema by default since
        # that's how the published paradigm forces strict JSON. For ablation
        # cells where the *worker* cloud is OpenAI / Gemini, the router can
        # still stay on Anthropic via the `router_model` + `router_endpoint`
        # cfg keys (Opus is the cheapest reliable router we have). Falls back
        # to plain JSON-prompted calls on non-Anthropic endpoints if a cell
        # explicitly opts in.
        router_model = cfg.get("router_model") or self._cloud_model
        router_endpoint = (cfg.get("router_endpoint") or self._cloud_endpoint).lower()
        router_max = int(cfg.get("router_max_tokens", 1024))

        if router_endpoint == "anthropic":
            anthropic_kwargs: Dict[str, Any] = dict(
                user=f"Question:\n{question}",
                system=router_sys,
                max_tokens=router_max,
                output_config=router_schema,
            )
            if supports_temperature(router_model):
                anthropic_kwargs["temperature"] = 0.0
            router_text, r_in, r_out, _ = self._call_anthropic(
                router_model, **anthropic_kwargs
            )
        else:
            # Fallback path: ask for JSON in the prompt, no schema-enforced
            # output. Less reliable than Anthropic's output_config but
            # available for OpenAI / Gemini routers.
            json_sys = (
                router_sys
                + "\n\nReply with ONLY a JSON object matching this shape "
                "(no prose, no code fence): {\"skill_weights\": {<skill>: <float>}, "
                "\"chosen_agent\": \"<agent_id>\", \"reasoning\": \"<string>\"}."
            )
            r_kwargs: Dict[str, Any] = dict(
                user=f"Question:\n{question}",
                system=json_sys,
                max_tokens=router_max,
                temperature=0.0,
            )
            if router_endpoint == "openai":
                router_text, r_in, r_out = self._call_openai(router_model, **r_kwargs)
            elif router_endpoint == "gemini":
                router_text, r_in, r_out = self._call_gemini(router_model, **r_kwargs)
            else:
                raise ValueError(f"unsupported router endpoint: {router_endpoint!r}")

        decision = _parse_router_json(router_text)
        skill_weights: Dict[str, float] = decision.get("skill_weights") or {}
        for sid in SKILL_CATALOG:
            skill_weights.setdefault(sid, 0.0)
        chosen = decision.get("chosen_agent") or ""

        scored = _score_agents(skill_weights, competence, cost, lambda_cost)
        if chosen not in competence:
            chosen = max(scored, key=lambda a: scored[a]["final_score"])

        self.record_trace_event({
            "kind": "skillorchestra_route",
            "chosen_agent": chosen,
            "skill_weights": skill_weights,
            "agent_scores": scored,
            "reasoning": decision.get("reasoning", ""),
            "router_raw": router_text,
        })

        tokens_local = 0
        tokens_cloud = r_in + r_out
        run_cost = self.cost_usd(router_model, r_in, r_out)
        self._web_search_uses_last = 0

        # 2. Execute via chosen agent
        task_meta = (context.metadata.get("task") if context is not None else {}) or {}
        swe_mode = (
            bool(cfg.get("swe_use_agent_loop"))
            and bool(task_meta.get("problem_statement"))
            and bool(task_meta.get("repo"))
            and bool(task_meta.get("base_commit"))
        )
        if chosen.startswith("local-"):
            if not (self._local_model and self._local_endpoint):
                raise ValueError(
                    "SkillOrchestra route hit local agent but local_model/"
                    f"local_endpoint missing: {self._local_model!r}/{self._local_endpoint!r}"
                )
            if swe_mode:
                out = run_swe_agent_loop(
                    task_meta,
                    backbone="local",
                    backbone_model=self._local_model,
                    local_endpoint=self._local_endpoint,
                    initial_prompt=question,
                    max_turns=int(cfg.get("swe_max_turns", 30)),
                    bash_timeout=int(cfg.get("swe_bash_timeout_s", 120)),
                    output_cap=int(cfg.get("swe_output_cap", 10_000)),
                    turn_max_tokens=int(cfg.get("swe_turn_max_tokens", 4096)),
                    trace_prefix="skillorch_local",
                )
                ans = out["answer"]
                tokens_local += out["tokens_in"] + out["tokens_out"]
            else:
                ans, w_in, w_out = self._call_vllm(
                    self._local_model,
                    self._local_endpoint,
                    user=question,
                    max_tokens=int(cfg.get("local_max_tokens", 4096)),
                    temperature=float(cfg.get("local_temperature", 0.2)),
                    enable_thinking=False,
                )
                tokens_local += w_in + w_out
            worker_model = self._local_model
        else:
            # SWE agent loop supports anthropic/openai/gemini (extended
            # 2026-05-15 — see mini_swe_agent._loop_cloud_{openai,gemini}).
            if swe_mode:
                out = run_swe_agent_loop(
                    task_meta,
                    backbone="cloud",
                    backbone_model=self._cloud_model,
                    cloud_endpoint=self._cloud_endpoint,
                    initial_prompt=question,
                    max_turns=int(cfg.get("swe_max_turns", 30)),
                    bash_timeout=int(cfg.get("swe_bash_timeout_s", 120)),
                    output_cap=int(cfg.get("swe_output_cap", 10_000)),
                    turn_max_tokens=int(cfg.get("swe_turn_max_tokens", 4096)),
                    trace_prefix="skillorch_cloud",
                )
                ans = out["answer"]
                tokens_cloud += out["tokens_in"] + out["tokens_out"]
                run_cost += out["cost_usd"]
            else:
                # GAIA cloud worker: opt-in native web_search via the new
                # method_cfg.web_search schema. Only fires when the chosen
                # worker is on Anthropic (server-side tool).
                ws_enabled, ws_max_uses = web_search_cfg(cfg)
                gaia_max_turns = int(cfg.get("gaia_max_turns", 8))
                n_searches = 0
                if ws_enabled and self._cloud_endpoint == "anthropic":
                    ans, w_in, w_out, n_searches, _ = self._call_anthropic_agent(
                        self._cloud_model,
                        user=question,
                        max_tokens=int(cfg.get("cloud_max_tokens", 4096)),
                        temperature=0.0,
                        tools=[build_web_search_tool(ws_max_uses)],
                        max_turns=gaia_max_turns,
                    )
                else:
                    ans, w_in, w_out = self._call_cloud(
                        user=question,
                        max_tokens=int(cfg.get("cloud_max_tokens", 4096)),
                        temperature=0.0,
                    )
                tokens_cloud += w_in + w_out
                run_cost += self.cost_usd(self._cloud_model, w_in, w_out)
                run_cost += n_searches * WEB_SEARCH_COST_PER_CALL
                self._web_search_uses_last = n_searches
            worker_model = self._cloud_model

        meta = {
            "tokens_local": tokens_local,
            "tokens_cloud": tokens_cloud,
            "cost_usd": run_cost,
            "turns": 2,  # router + worker
            "web_search_uses": self._web_search_uses_last,
            "traces": {
                "chosen_agent": chosen,
                "worker_model": worker_model,
                "skill_weights": skill_weights,
                "agent_scores": scored,
                "reasoning": decision.get("reasoning", ""),
                "n_web_searches": self._web_search_uses_last,
            },
        }
        return ans, meta


__all__ = [
    "DEFAULT_AGENT_COMPETENCE",
    "DEFAULT_AGENT_COST_USD",
    "SKILL_CATALOG",
    "SkillOrchestraAgent",
]
