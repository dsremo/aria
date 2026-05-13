"""R144 — Subdomain takeover detection.

Threat: ARIA's DNS contains ``status.aria.example.com`` pointing at
``aria-status.s3-website.us-east-1.amazonaws.com``.  The S3 bucket is
deleted; an attacker registers the same name in their account and
serves arbitrary content from ARIA's DNS.  Common Linode / GitHub
Pages / Heroku takeovers documented; CISA tracks the pattern.

Defence: ``check_dangling_cname(domain)`` resolves CNAME chains and
flags targets whose name is in a known takeover-prone family AND
whose target doesn't currently resolve to a live A/AAAA.  Operators
run this nightly + on every DNS change.
"""

from __future__ import annotations

import socket
from typing import List, Tuple

from aria.security.plugins import DefencePlugin, register


_TAKEOVER_PRONE = (
    "s3-website",
    "s3.amazonaws.com",
    "azurewebsites.net",
    "azureedge.net",
    "blob.core.windows.net",
    "cloudfront.net",
    "elasticbeanstalk.com",
    "github.io",
    "herokuapp.com",
    "wordpress.com",
    "ghost.io",
    "fastly.net",
    "netlify.app",
    "pantheonsite.io",
    "tumblr.com",
    "shopify.com",
)


def is_takeover_prone(target: str) -> bool:
    target_lower = target.lower().rstrip(".")
    return any(suffix in target_lower for suffix in _TAKEOVER_PRONE)


def check_domain(domain: str) -> Tuple[bool, str]:
    """Return ``(safe, reason)`` — safe=False on suspected takeover.

    Strategy: resolve the domain; if the canonical name (via getaddrinfo)
    sits in a takeover-prone family AND a fresh A lookup returns NXDOMAIN
    or NoAnswer, we flag it.
    """
    try:
        ai = socket.getaddrinfo(domain, None)
    except socket.gaierror:
        # Domain doesn't resolve — could be a stale CNAME at the apex
        return False, f"r144.nxdomain {domain}"
    cnames: List[str] = []
    for entry in ai:
        canon = entry[3] or ""
        if canon and canon != domain:
            cnames.append(canon)
    cnames = list(set(cnames))
    for cn in cnames:
        if is_takeover_prone(cn):
            try:
                socket.gethostbyname(cn)
            except socket.gaierror:
                return False, f"r144.dangling_cname {domain} -> {cn}"
    return True, "ok"


register(DefencePlugin(
    round_id="R144",
    name="subdomain_takeover",
    description="Detect dangling CNAMEs to takeover-prone provider families.",
))
