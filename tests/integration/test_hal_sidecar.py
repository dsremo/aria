from __future__ import annotations

import json
import socket
import time
from typing import Iterator

import pytest

from aria.integrations.hal_sidecar import (
    ActuatorBank,
    ColdGasThruster,
    HalFrame,
    HalSidecarClient,
    HalSidecarServer,
    parse_and_verify_frame,
    sign_frame,
)
from aria.integrations.hal_sidecar.protocol import fresh_nonce


SECRET = b"a" * 32


@pytest.fixture
def server() -> Iterator[HalSidecarServer]:
    bank = ActuatorBank(
        dry_mass_kg=12.0, thruster=ColdGasThruster(propellant_kg=0.50),
    )
    srv = HalSidecarServer(
        bind_host="127.0.0.1", bind_port=0, secret=SECRET, bank=bank,
    )
    srv.start()
    try:
        yield srv
    finally:
        srv.stop()


@pytest.fixture
def client(server: HalSidecarServer) -> HalSidecarClient:
    host, port = server.address
    return HalSidecarClient(host=host, port=port, secret=SECRET, timeout_s=2.0)


class TestProtocolSignVerify:
    def test_round_trip(self):
        frame = HalFrame(
            counter=1, nonce=fresh_nonce(), timestamp_s=time.time(),
            command="ping", params={},
        )
        raw = sign_frame(SECRET, frame)
        verdict = parse_and_verify_frame(raw, SECRET)
        assert verdict.accepted
        assert verdict.frame is not None
        assert verdict.frame.command == "ping"
        assert verdict.frame.counter == 1

    def test_tampered_body_rejected(self):
        frame = HalFrame(
            counter=2, nonce=fresh_nonce(), timestamp_s=time.time(),
            command="thruster.fire", params={"burn_time_s": 1.0},
        )
        raw = bytearray(sign_frame(SECRET, frame))
        envelope = json.loads(raw.decode("utf-8"))
        envelope["params"]["burn_time_s"] = 999.0
        tampered = json.dumps(envelope, separators=(",", ":")).encode("utf-8")
        verdict = parse_and_verify_frame(tampered, SECRET)
        assert not verdict.accepted
        assert verdict.reason == "signature_mismatch"

    def test_wrong_secret_rejected(self):
        frame = HalFrame(
            counter=3, nonce=fresh_nonce(), timestamp_s=time.time(),
            command="ping", params={},
        )
        raw = sign_frame(SECRET, frame)
        verdict = parse_and_verify_frame(raw, b"b" * 32)
        assert not verdict.accepted
        assert verdict.reason == "signature_mismatch"

    def test_short_nonce_rejected(self):
        frame = HalFrame(
            counter=4, nonce="short", timestamp_s=time.time(),
            command="ping", params={},
        )
        raw = sign_frame(SECRET, frame)
        verdict = parse_and_verify_frame(raw, SECRET)
        assert not verdict.accepted
        assert verdict.reason == "nonce_too_short"

    def test_stale_frame_rejected(self):
        frame = HalFrame(
            counter=5, nonce=fresh_nonce(), timestamp_s=time.time() - 600.0,
            command="ping", params={},
        )
        raw = sign_frame(SECRET, frame)
        verdict = parse_and_verify_frame(raw, SECRET, max_age_s=60.0)
        assert not verdict.accepted
        assert verdict.reason == "stale"

    def test_future_dated_rejected(self):
        frame = HalFrame(
            counter=6, nonce=fresh_nonce(), timestamp_s=time.time() + 600.0,
            command="ping", params={},
        )
        raw = sign_frame(SECRET, frame)
        verdict = parse_and_verify_frame(raw, SECRET)
        assert not verdict.accepted
        assert verdict.reason == "future_dated"

    def test_garbage_rejected(self):
        verdict = parse_and_verify_frame(b"not json at all", SECRET)
        assert not verdict.accepted
        assert verdict.reason == "json_decode_error"

    def test_oversize_rejected(self):
        oversize = b"x" * 9000
        verdict = parse_and_verify_frame(oversize, SECRET)
        assert not verdict.accepted
        assert verdict.reason == "frame_oversize"


class TestActuatorBank:
    def test_thruster_burn_produces_delta_v(self):
        bank = ActuatorBank(
            dry_mass_kg=12.0, thruster=ColdGasThruster(propellant_kg=0.50),
        )
        ok, detail = bank.dispatch(
            command="thruster.fire", params={"burn_time_s": 5.0}, counter=1,
        )
        assert ok, detail
        snap = bank.snapshot()
        assert snap.delta_v_total_m_s > 0
        assert snap.propellant_remaining_kg < 0.50

    def test_thruster_runs_dry_after_excessive_burn(self):
        bank = ActuatorBank(
            dry_mass_kg=12.0, thruster=ColdGasThruster(propellant_kg=0.001),
        )
        bank.dispatch(
            command="thruster.fire", params={"burn_time_s": 1000.0}, counter=1,
        )
        ok, detail = bank.dispatch(
            command="thruster.fire", params={"burn_time_s": 1.0}, counter=2,
        )
        assert not ok
        assert "propellant_exhausted" in detail

    def test_wheel_torque_accumulates_momentum(self):
        bank = ActuatorBank()
        bank.dispatch(
            command="wheel.torque",
            params={"torque_nm": [0.05, 0.0, 0.0], "dt_s": 1.0},
            counter=1,
        )
        snap = bank.snapshot()
        assert abs(snap.rw_momentum_nms[0] - 0.05) < 1e-9

    def test_wheel_saturates_at_limit(self):
        bank = ActuatorBank()
        for index in range(20):
            bank.dispatch(
                command="wheel.torque",
                params={"torque_nm": [0.10, 0.0, 0.0], "dt_s": 1.0},
                counter=index + 1,
            )
        snap = bank.snapshot()
        assert snap.rw_saturated
        assert abs(snap.rw_momentum_nms[0]) <= 0.40 + 1e-9

    def test_heater_warms_when_on(self):
        bank = ActuatorBank()
        bank.dispatch(command="heater.on", params={}, counter=1)
        bank.dispatch(command="heater.step", params={"dt_s": 60.0}, counter=2)
        snap = bank.snapshot()
        assert snap.heater_on
        assert snap.heater_temp_k > 293.15

    def test_unknown_command_rejected(self):
        bank = ActuatorBank()
        ok, detail = bank.dispatch(
            command="self.destruct", params={}, counter=1,
        )
        assert not ok
        assert "unknown_command" in detail


class TestServerOverLoopback:
    def test_ping_round_trip(self, client: HalSidecarClient):
        result = client.ping()
        assert result.accepted
        assert result.detail == "pong"
        assert "heater_temp_k" in result.state

    def test_thruster_fire_via_udp(self, client: HalSidecarClient):
        result = client.fire_thruster(burn_time_s=2.0)
        assert result.accepted
        assert result.state["delta_v_total_m_s"] > 0
        assert result.state["propellant_remaining_kg"] < 0.50

    def test_replay_rejected(self, server: HalSidecarServer):
        host, port = server.address
        frame = HalFrame(
            counter=42, nonce=fresh_nonce(), timestamp_s=time.time(),
            command="ping", params={},
        )
        raw = sign_frame(SECRET, frame)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(2.0)
        try:
            sock.sendto(raw, (host, port))
            first_reply = json.loads(sock.recv(8192).decode("utf-8"))
            assert first_reply["accepted"]
            sock.sendto(raw, (host, port))
            second_reply = json.loads(sock.recv(8192).decode("utf-8"))
            assert not second_reply["accepted"]
            assert "replay" in second_reply["detail"]
        finally:
            sock.close()

    def test_counter_must_be_monotonic(self, server: HalSidecarServer):
        host, port = server.address
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(2.0)
        try:
            for desired_counter in (10, 11, 5):
                frame = HalFrame(
                    counter=desired_counter,
                    nonce=fresh_nonce(),
                    timestamp_s=time.time(),
                    command="ping",
                    params={},
                )
                sock.sendto(sign_frame(SECRET, frame), (host, port))
                reply = json.loads(sock.recv(8192).decode("utf-8"))
                if desired_counter == 5:
                    assert not reply["accepted"]
                    assert "replay" in reply["detail"]
                else:
                    assert reply["accepted"]
        finally:
            sock.close()

    def test_unsigned_garbage_rejected(self, server: HalSidecarServer):
        host, port = server.address
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(2.0)
        try:
            sock.sendto(b"not a frame", (host, port))
            reply = json.loads(sock.recv(8192).decode("utf-8"))
            assert not reply["accepted"]
            assert "reject:" in reply["detail"]
        finally:
            sock.close()

    def test_stats_count_accepts_and_rejects(
        self, server: HalSidecarServer, client: HalSidecarClient,
    ):
        client.ping()
        client.ping()
        host, port = server.address
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(2.0)
        try:
            sock.sendto(b"junk", (host, port))
            sock.recv(8192)
        finally:
            sock.close()
        time.sleep(0.05)
        stats = server.stats
        assert stats["accepted"] >= 2
        assert stats["rejected"] >= 1
