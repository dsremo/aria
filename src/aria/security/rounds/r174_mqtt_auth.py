"""R174 — MQTT broker auth + TLS audit.

Threat: a public MQTT broker without auth (or with anon=true) is the
classic IoT botnet pivot — Shodan lists 100K+ open Mosquitto instances
at any given time.  Many leak telemetry from medical devices, fleet
trackers, building HVAC.

Defence: validate a connect-args dict — refuse anonymous in prod,
require TLS, refuse port 1883 (cleartext) outside localhost.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


def audit_mqtt_connect(args: Dict[str, Any]) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    host = (args.get("host") or "").lower()
    port = int(args.get("port") or 0)
    use_tls = bool(args.get("tls"))
    username = args.get("username") or ""
    password = args.get("password") or ""

    if not username or not password:
        issues.append("mqtt.no_auth")

    if not use_tls and host not in ("localhost", "127.0.0.1", "::1"):
        issues.append(f"mqtt.cleartext_to_remote_host:{host}")

    if port == 1883 and host not in ("localhost", "127.0.0.1", "::1"):
        issues.append("mqtt.unencrypted_port_1883")

    if port == 8883 and not use_tls:
        issues.append("mqtt.tls_port_no_tls_flag")

    if username == "admin" and password in ("admin", "public", "mqtt"):
        issues.append("mqtt.default_credential")

    return not issues, issues


register(DefencePlugin(
    round_id="R174",
    name="mqtt_auth",
    description="MQTT broker connect audit; refuse anonymous + cleartext in prod.",
))
