"""HTTP route: ``POST /api/research`` — agentic research over the knowledge store.

Drives :class:`openjarvis.agents.research_loop.ResearchAgent` and streams a
custom SSE event schema back to the client:

* ``search_call``     — about to invoke ``HybridSearch.search`` (with arguments)
* ``search_result``   — search returned (num_hits, top_titles)
* ``synthesis``       — final answer, emitted in word-window chunks for an
  incremental UX (the agent itself returns the full string in one shot;
  chunking happens in the router so we don't need to rewire the loop)
* ``done``            — sentinel marking the end of the stream

Clarify is **disabled for the web session** — the agent's clarify_handler is
overridden to return a fixed "no clarification available" string so the
loop never blocks waiting for terminal stdin. Bringing real clarify back
to the browser will require a two-step session protocol; that's a future
endpoint, not this one.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, AsyncGenerator, Dict, Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from openjarvis.agents.research_loop import (
    DEFAULT_PLANNER_MODEL,
    ResearchAgent,
)
from openjarvis.connectors.embeddings import OllamaEmbedder
from openjarvis.connectors.hybrid_search import HybridSearch
from openjarvis.connectors.store import KnowledgeStore
from openjarvis.engine.ollama import OllamaEngine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["research"])

_WEB_CLARIFY_RESPONSE = "no clarification available in web session"

# Sentinel placed on the queue when the agent thread terminates.
_DONE = object()


# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------


class ResearchRequest(BaseModel):
    query: str = Field(..., description="Natural-language question to research.")
    model: Optional[str] = Field(
        default=None,
        description=(
            "Planner model tag. Defaults to the configured "
            "DEFAULT_PLANNER_MODEL (gemma4:31b)."
        ),
    )


# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------


def _sse(event: Dict[str, Any]) -> str:
    """Serialize one event dict to an SSE ``data: ...\\n\\n`` frame."""
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _chunk_synthesis(text: str, window_chars: int = 40) -> list[str]:
    """Slice synthesis text into client-streaming-friendly chunks.

    We break on word boundaries so partial deltas always render cleanly in
    the browser. Each chunk is roughly ``window_chars`` characters long.
    """
    if not text:
        return []
    tokens = re.findall(r"\S+\s*", text)
    chunks: list[str] = []
    buf = ""
    for tok in tokens:
        if len(buf) + len(tok) > window_chars and buf:
            chunks.append(buf)
            buf = tok
        else:
            buf += tok
    if buf:
        chunks.append(buf)
    return chunks


# ---------------------------------------------------------------------------
# Stream generator
# ---------------------------------------------------------------------------


async def _stream_research(query: str, model: str) -> AsyncGenerator[str, None]:
    """Drive ResearchAgent on a worker thread; yield SSE frames as they land."""
    loop = asyncio.get_event_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def on_event(event: Dict[str, Any]) -> None:
        # Called from the agent's worker thread; bounce onto the event loop.
        loop.call_soon_threadsafe(queue.put_nowait, event)

    # Each request gets its own thin set of connectors. Constructing them is
    # cheap (SQLite open + HTTP keepalive) and avoids state leaks between
    # concurrent requests.
    store = KnowledgeStore()
    embedder = OllamaEmbedder()
    if not embedder.is_available():
        logger.warning("research: Ollama embedder unavailable; BM25-only retrieval.")
        embedder = None

    engine = OllamaEngine()
    agent = ResearchAgent(
        engine=engine,
        search=HybridSearch(store, embedder),
        model=model,
        clarify_handler=lambda question: _WEB_CLARIFY_RESPONSE,
        on_event=on_event,
    )

    def _run() -> None:
        try:
            agent.run(query)
        except Exception as exc:  # noqa: BLE001
            logger.exception("research agent crashed: %s", exc)
            loop.call_soon_threadsafe(
                queue.put_nowait,
                {"type": "error", "message": f"{type(exc).__name__}: {exc}"},
            )
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, _DONE)

    task = asyncio.create_task(asyncio.to_thread(_run))

    final_answer: Optional[str] = None
    try:
        while True:
            event = await queue.get()
            if event is _DONE:
                break
            if not isinstance(event, dict):
                continue

            etype = event.get("type")
            # We translate the agent's `final_answer` event into a stream of
            # `synthesis` chunks so the client sees the answer materialize
            # incrementally rather than as a single blob.
            if etype == "final_answer":
                final_answer = event.get("text", "")
                for piece in _chunk_synthesis(final_answer or ""):
                    yield _sse({"type": "synthesis", "text": piece})
                continue

            yield _sse(event)

        # If the agent thread crashed before producing a final answer, the
        # client still gets the error frame (emitted above) followed by done.
        yield _sse({"type": "done"})
    finally:
        # The worker may still be cleaning up (rarely) — make sure we don't
        # leak a dangling task.
        if not task.done():
            await task


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.post("/research")
async def research(req: ResearchRequest) -> StreamingResponse:
    """Run a research query and stream the agent's trace + synthesis via SSE.

    Response is ``text/event-stream`` with one JSON event per frame. See the
    module docstring for the schema; a final ``{"type": "done"}`` always
    terminates the stream so clients can detect end-of-response without
    parsing the underlying ``[DONE]`` sentinel used by OpenAI-style routes.
    """
    model = req.model or DEFAULT_PLANNER_MODEL
    return StreamingResponse(
        _stream_research(req.query, model),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


__all__ = ["router", "ResearchRequest"]
