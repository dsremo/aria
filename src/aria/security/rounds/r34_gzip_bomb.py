"""R34 — Gzip / Brotli decompression bomb.

Threat: a fetched response advertises ``Content-Encoding: gzip``; the
compressed body is 10 KiB but expands to 10 GiB, exhausting RAM.
ARIA fetches from external feeds (CISA KEV, NTRS, JPL Horizons) which
default to gzip transport.  CWE-409.

Defence: decode in chunks, never let the decompressed total exceed
``max_uncompressed_bytes``.  Aborts with ``ResponseTooLarge`` (already
raised in ``aria.security.guard.safe_open_url`` for the compressed
size; this round adds the *decompressed* axis).
"""

from __future__ import annotations

import gzip
import io
import zlib
from typing import Optional

from aria.security.plugins import DefencePlugin, register


_DEFAULT_MAX = 256 * 1024 * 1024     # 256 MiB


def safe_gunzip(payload: bytes, *, max_bytes: int = _DEFAULT_MAX) -> bytes:
    """gzip-decode while bounding the output size; raise on bomb."""
    out = bytearray()
    with gzip.GzipFile(fileobj=io.BytesIO(payload)) as gz:
        while True:
            chunk = gz.read(64 * 1024)
            if not chunk:
                break
            out.extend(chunk)
            if len(out) > max_bytes:
                raise ValueError(
                    f"R34.gzip_bomb: decompressed > {max_bytes} bytes"
                )
    return bytes(out)


def safe_zlib_decompress(payload: bytes, *, max_bytes: int = _DEFAULT_MAX) -> bytes:
    d = zlib.decompressobj()
    out = bytearray()
    chunk_size = 64 * 1024
    pos = 0
    while pos < len(payload):
        chunk = payload[pos: pos + chunk_size]
        pos += chunk_size
        out.extend(d.decompress(chunk))
        if len(out) > max_bytes:
            raise ValueError(
                f"R34.zlib_bomb: decompressed > {max_bytes} bytes"
            )
    out.extend(d.flush())
    return bytes(out)


register(DefencePlugin(
    round_id="R34",
    name="gzip_bomb",
    description="Bounded-output gzip + zlib decoders; raise on decompression bomb.",
))
