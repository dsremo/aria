"""ARIA Dashboard Demo — Basilisk → ARIA → OpenMCT pipeline.

Runs a complete end-to-end demo:
  1. Starts Basilisk spacecraft simulation (ISS-like orbit, 400 km)
  2. Feeds telemetry through ARIA's message bus
  3. Serves telemetry via WebSocket to OpenMCT dashboard
  4. Opens browser to OpenMCT (if available)

Usage:
    python -m aria.dashboard.run_demo [--port 8080] [--speed 10]

Then open: http://localhost:8080 (OpenMCT) or ws://localhost:8080/realtime (raw WS)
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import structlog

logger = structlog.get_logger()


async def run_demo(port: int = 8080, speed: float = 10.0, duration_s: float = 5520.0) -> None:
    """Run the full Basilisk → ARIA → OpenMCT demo."""
    from aria.simulation.basilisk_runner import (
        BasiliskSimRunner, SimConfig, OrbitConfig, SpacecraftConfig,
        BASILISK_AVAILABLE,
    )
    from aria.dashboard.telemetry_server import ARIATelemetryServer

    if not BASILISK_AVAILABLE:
        logger.error("demo.basilisk_not_installed", msg="Install with: pip install bsk")
        sys.exit(1)

    # ─── Configure simulation ───
    config = SimConfig(
        timestep_s=1.0,
        output_interval_s=10.0,  # Telemetry every 10 seconds
        duration_s=duration_s,
        orbit=OrbitConfig(
            altitude_km=400.0,
            inclination_deg=51.6,  # ISS inclination
        ),
        spacecraft=SpacecraftConfig(
            mass_kg=420000.0,      # ISS mass
            solar_panel_area_m2=2500.0,  # ISS solar array area
            battery_capacity_whr=2800.0,
            nominal_power_w=75000.0,  # ISS average power
        ),
    )

    # ─── Start telemetry server ───
    server = ARIATelemetryServer(host="0.0.0.0", port=port)  # nosec B104 (demo runner; production binds via reverse proxy)
    await server.start()
    logger.info("demo.server_ready", port=port,
                endpoints={
                    "dictionary": f"http://localhost:{port}/dictionary",
                    "health": f"http://localhost:{port}/health",
                    "websocket": f"ws://localhost:{port}/realtime",
                })

    # ─── Start Basilisk simulation ───
    runner = BasiliskSimRunner(config)
    runner.setup()
    logger.info("demo.basilisk_ready", orbit="ISS-like 400km", speed=f"{speed}x")

    # ─── Run simulation loop ───
    step_s = config.output_interval_s
    elapsed = 0.0
    frame_count = 0

    print(f"\n{'='*60}")
    print(f"  ARIA Dashboard Demo")
    print(f"  Basilisk ISS orbit simulation at {speed}x speed")
    print(f"  Telemetry: http://localhost:{port}/dictionary")
    print(f"  WebSocket: ws://localhost:{port}/realtime")
    print(f"  Health:    http://localhost:{port}/health")
    print(f"{'='*60}\n")

    try:
        while elapsed < duration_s:
            frames = runner.step(step_s)

            for frame in frames:
                server.push_basilisk_frame(frame)
                frame_count += 1

                if frame_count % 10 == 0:
                    logger.info(
                        "demo.telemetry",
                        t=f"{frame.timestamp_s:.0f}s",
                        alt=f"{frame.altitude_km:.1f}km",
                        lat=f"{frame.ground_track_lat_deg:.1f}°",
                        lon=f"{frame.ground_track_lon_deg:.1f}°",
                        solar=f"{frame.solar_power_w:.0f}W",
                        eclipse=frame.in_eclipse,
                    )

            elapsed += step_s

            # Real-time pacing
            if speed > 0:
                await asyncio.sleep(step_s / speed)

    except KeyboardInterrupt:
        logger.info("demo.stopped", frames=frame_count)

    logger.info("demo.complete", total_frames=frame_count, sim_time_s=elapsed)


def main() -> None:
    parser = argparse.ArgumentParser(description="ARIA Dashboard Demo")
    parser.add_argument("--port", type=int, default=8080, help="Server port (default: 8080)")
    parser.add_argument("--speed", type=float, default=10.0, help="Simulation speed multiplier (default: 10x)")
    parser.add_argument("--duration", type=float, default=5520.0, help="Simulation duration in seconds")
    args = parser.parse_args()

    asyncio.run(run_demo(port=args.port, speed=args.speed, duration_s=args.duration))


if __name__ == "__main__":
    main()
