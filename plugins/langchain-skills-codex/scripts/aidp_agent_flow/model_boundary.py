"""Final-text and thread-lifetime contracts shared with generated native agents."""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from contextvars import ContextVar

_completion = ContextVar("aidp_completion", default=None)


@contextmanager
def final_text_scope():
    # Child graph tasks inherit this invocation's record, not another user's.
    state = {"failed": False}
    token = _completion.set(state)
    try:
        yield
        if state["failed"]:
            raise ValueError("OCI model produced an incomplete response, even if the graph recovered")
    finally:
        _completion.reset(token)


def _reject(message):
    state = _completion.get()
    if state is not None:
        state["failed"] = True
    raise ValueError(message)


def final_text(response):
    choices = getattr(response, "choices", None)
    choice = choices[0] if isinstance(choices, list) and len(choices) == 1 else None
    message = getattr(choice, "message", None)
    content = getattr(message, "content", None)
    if (getattr(choice, "finish_reason", None) != "stop"
            or getattr(message, "role", None) != "ASSISTANT"
            or getattr(message, "tool_calls", None) or not isinstance(content, list)
            or not 1 <= len(content) <= 256
            or any(getattr(part, "type", None) != "TEXT" or not isinstance(getattr(part, "text", None), str)
                   for part in content)):
        _reject("OCI model did not return a complete supported final text response")
    answer = "".join(part.text for part in content)
    if not answer.strip() or len(answer) > 1_000_000:
        _reject("OCI model final text is empty or exceeds the supported output limit")
    return answer


async def run_blocking(function, *args, **kwargs):
    task = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        # Cancellation cannot stop a running SDK thread. Drain before its owner
        # closes a client; the provider operation still needs reconciliation.
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if not task.cancelled():
            task.exception()
        raise
