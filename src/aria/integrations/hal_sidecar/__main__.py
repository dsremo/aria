from __future__ import annotations

import argparse
import os
import signal
import sys
import time
from pathlib import Path
from typing import Optional

from aria.integrations.hal_sidecar.actuators import ActuatorBank, ColdGasThruster
from aria.integrations.hal_sidecar.server import HalSidecarServer


def _load_secret(arg_value: Optional[str], env_var: str) -> bytes:
    if arg_value:
        path = Path(arg_value)
        if path.exists():
            return path.read_bytes().strip()
        return arg_value.encode("utf-8")
    env_secret = os.environ.get(env_var, "").strip()
    if env_secret:
        return env_secret.encode("utf-8")
    raise SystemExit(
        f"HAL secret missing: pass --key-file or set {env_var}; "
        f"must be >= 16 bytes."
    )


def _build_bank(*, dry_mass_kg: float, propellant_kg: float) -> ActuatorBank:
    return ActuatorBank(
        dry_mass_kg=dry_mass_kg,
        thruster=ColdGasThruster(propellant_kg=propellant_kg),
    )


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m aria.integrations.hal_sidecar",
        description=(
            "ARIA HAL sidecar (Jetson Orin / x86). Listens on UDP for "
            "HMAC-signed command frames from the ARIA agent and dispatches "
            "them to a simulated actuator bank (thruster / RW / heater / "
            "payload). Replace actuators.py with real GPIO drivers when "
            "deploying on the actual flight computer."
        ),
    )
    parser.add_argument("--bind", default="127.0.0.1", help="Bind address")
    parser.add_argument("--port", type=int, default=5870, help="UDP port")
    parser.add_argument("--key-file", default=None,
                        help="Path to HAL shared-secret key file")
    parser.add_argument(
        "--dry-mass-kg", type=float, default=12.0,
        help="Spacecraft dry mass for thruster Δv accounting",
    )
    parser.add_argument(
        "--propellant-kg", type=float, default=0.50,
        help="Initial propellant mass",
    )
    parser.add_argument(
        "--max-frame-age-s", type=float, default=60.0,
        help="Reject frames older than this many seconds",
    )
    parser.add_argument(
        "--print-snapshot-every-s", type=float, default=0.0,
        help="If > 0, print actuator snapshot every N seconds",
    )
    args = parser.parse_args(argv)

    secret = _load_secret(args.key_file, "ARIA_HAL_SECRET")
    bank = _build_bank(
        dry_mass_kg=args.dry_mass_kg, propellant_kg=args.propellant_kg,
    )
    server = HalSidecarServer(
        bind_host=args.bind,
        bind_port=args.port,
        secret=secret,
        bank=bank,
        max_frame_age_s=args.max_frame_age_s,
    )
    server.start()
    addr = server.address
    print(f"hal-sidecar listening on udp://{addr[0]}:{addr[1]}", file=sys.stderr)

    stop_signal = {"received": False}

    def _on_signal(*_args) -> None:
        stop_signal["received"] = True

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    last_print = 0.0
    try:
        while not stop_signal["received"]:
            time.sleep(0.25)
            if args.print_snapshot_every_s > 0:
                now = time.time()
                if now - last_print >= args.print_snapshot_every_s:
                    snap = bank.snapshot_dict()
                    print(f"[snapshot] {snap}", file=sys.stderr)
                    last_print = now
    finally:
        server.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
