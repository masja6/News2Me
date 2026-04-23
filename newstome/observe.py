"""
Thin Langfuse wrapper. All calls are no-ops when LANGFUSE_PUBLIC_KEY is not set,
so the app runs fine without any observability credentials.
"""
from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any

from .config import secrets

_lf = None


def _client():
    global _lf
    if _lf is not None:
        return _lf
    if not secrets.langfuse_public_key or not secrets.langfuse_secret_key:
        return None
    try:
        from langfuse import Langfuse
        _lf = Langfuse(
            public_key=secrets.langfuse_public_key,
            secret_key=secrets.langfuse_secret_key,
            host=secrets.langfuse_host,
        )
    except Exception:
        pass
    return _lf


# Active trace held per pipeline run (one trace = one digest run)
_active_trace = None


def start_trace(name: str, metadata: dict | None = None):
    global _active_trace
    lf = _client()
    if lf is None:
        return
    _active_trace = lf.trace(name=name, metadata=metadata or {})


def end_trace():
    global _active_trace
    lf = _client()
    if lf:
        lf.flush()
    _active_trace = None


@contextmanager
def span(name: str, input: Any = None, metadata: dict | None = None):
    """Context manager that records a span under the active trace."""
    lf = _client()
    if lf is None or _active_trace is None:
        yield _NoopSpan()
        return

    s = _active_trace.span(name=name, input=input, metadata=metadata or {})
    t0 = time.perf_counter()
    try:
        yield s
    finally:
        s.end(metadata={**(metadata or {}), "latency_ms": round((time.perf_counter() - t0) * 1000)})


def log_generation(
    name: str,
    model: str,
    prompt: str,
    completion: str,
    input_tokens: int,
    output_tokens: int,
    metadata: dict | None = None,
):
    """Records a single LLM generation under the active trace."""
    lf = _client()
    if lf is None or _active_trace is None:
        return
    _active_trace.generation(
        name=name,
        model=model,
        input=prompt,
        output=completion,
        usage={"input": input_tokens, "output": output_tokens, "unit": "TOKENS"},
        metadata=metadata or {},
    )


class _NoopSpan:
    def end(self, **_): pass
    def __enter__(self): return self
    def __exit__(self, *_): pass
