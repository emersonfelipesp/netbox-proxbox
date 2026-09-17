"""Pure helpers for reading proxbox-api error bodies.

Kept free of NetBox and Django imports so both the sync-stage composer and the
backend proxy can share one rule, and so the focused test harnesses can load it
without stubbing anything.
"""

from __future__ import annotations

import json
from collections.abc import Mapping


def _detail_text(value: object, *, render_structured: bool) -> str:
    """Render a ``detail`` value as text.

    Strings are used as-is. A dict or list is serialised as compact,
    deterministic JSON only when ``render_structured`` is set: FastAPI reports
    validation errors as a *list* under ``detail`` and those must survive as
    diagnostics on the HTTP-error path, which redacts the result. Callers whose
    output feeds the retry classifier keep structures out, because a FastAPI
    ``input`` echo carries the submitted body (credentials, arbitrary names)
    and must never be scanned for cause words.
    """
    if isinstance(value, str):
        return value.strip()
    if render_structured and isinstance(value, (dict, list)) and value:
        return json.dumps(value, sort_keys=True, default=str)
    return ""


def combine_backend_message_and_detail(
    payload: Mapping[str, object], *, render_structured: bool = False
) -> str | None:
    """Return the backend's ``message`` and ``detail`` as one operator-facing line.

    proxbox-api answers every handled failure as ``{"message", "detail",
    "python_exception"}``. Reading ``detail or message`` treats the two as
    alternatives, so a populated ``detail`` hid the message and an empty
    ``detail`` hid the cause. The rule here: both present and distinct gives
    ``"<message>: <detail>"``; otherwise whichever is present.

    A ``detail`` holding JSON text (an object or array) is returned without the
    message prefix so it stays parseable by the stage-failure composer. A dict
    or list ``detail`` is rendered the same way only with ``render_structured``;
    otherwise it is ignored and the message stands alone (see ``_detail_text``).
    ``python_exception`` is deliberately never read: it can echo request content.
    """
    message = payload.get("message")
    message = message.strip() if isinstance(message, str) else ""
    detail = _detail_text(payload.get("detail"), render_structured=render_structured)
    if not detail:
        return message or None
    if not message or message == detail or message in detail:
        return detail
    if detail.startswith(("{", "[")):
        return detail
    return f"{message}: {detail}"
