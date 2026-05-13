"""R86 — HTTP request smuggling (CL.TE / TE.CL / TE.TE).

Threat: a frontend (Caddy / nginx) and backend (aiohttp) disagree on
where the request body ends — different parsers honour
``Transfer-Encoding`` and ``Content-Length`` differently.  An attacker
crafts a request that the frontend forwards as one whole, while the
backend reads two — the second is unauthenticated and queue-poisoned.
Cited PortSwigger 2019 + ongoing 2024 chains.

Defence: a request hook that refuses any inbound request carrying
both ``Transfer-Encoding`` and ``Content-Length``, and any
``Transfer-Encoding`` whose value isn't simply ``chunked``.  aiohttp
already does most of this; the hook explicitly catches the residue and
emits a CRITICAL audit event.
"""

from __future__ import annotations

from aria.security.plugins import DefencePlugin, register


_TE_OK = {"chunked"}


def _on_request(request, _body):
    headers = request.headers
    cl = headers.get("Content-Length")
    te = headers.get("Transfer-Encoding")
    if cl is not None and te is not None:
        raise RuntimeError("R86.smuggling: both Content-Length + Transfer-Encoding")
    if te is not None and te.strip().lower() not in _TE_OK:
        raise RuntimeError(f"R86.smuggling: unsupported Transfer-Encoding {te!r}")
    # Multiple CL headers
    if cl is not None and "," in cl:
        raise RuntimeError(f"R86.smuggling: multi-value Content-Length {cl!r}")


register(DefencePlugin(
    round_id="R86",
    name="smuggling_v2",
    description="Refuse CL+TE combination and unsupported Transfer-Encoding values.",
    on_request=_on_request,
))
