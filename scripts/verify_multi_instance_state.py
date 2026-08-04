#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["redis>=5", "websockets>=12"]
# ///

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import redis
from redis.exceptions import RedisError
from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
PYTHON = BACKEND / ".venv" / "bin" / "python"
HOST_REDIS_URL = "redis://localhost:6379/0"


def _port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _request(base: str, path: str, method: str = "GET", payload: dict | None = None, token: str | None = None) -> tuple[int, dict]:
    body = None if payload is None else json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(base + path, data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=10) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else {}
    except HTTPError as error:
        raw = error.read()
        return error.code, json.loads(raw) if raw else {}


def _login(base: str) -> str:
    body = b"username=admin%40demo.disaster&password=demo1234"
    request = Request(
        base + "/api/auth/login",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urlopen(request, timeout=15) as response:
        return str(json.loads(response.read())["access_token"])


def _wait(base: str) -> None:
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        try:
            status, _ = _request(base, "/healthz")
            if status == 200:
                return
        except (URLError, TimeoutError):
            pass
        time.sleep(0.25)
    raise RuntimeError(f"backend did not become healthy: {base}")


def _resolve_redis_url(redis_url: str | None) -> str:
    return redis_url or os.environ.get("REDIS_URL") or HOST_REDIS_URL


def _redis_available(redis_url: str) -> bool:
    try:
        redis.Redis.from_url(redis_url, socket_connect_timeout=2).ping()
    except (OSError, RedisError, TimeoutError, ValueError): return False
    return True


def _start(instances: int, redis_url: str | None) -> tuple[list[subprocess.Popen[bytes]], list[str]]:
    processes: list[subprocess.Popen[bytes]] = []
    bases: list[str] = []
    selected_redis_url = _resolve_redis_url(redis_url)
    try:
        for _ in range(instances):
            port = _port()
            env = os.environ.copy()
            env["PYTHONPATH"] = str(BACKEND)
            env["REDIS_URL"] = selected_redis_url
            process = subprocess.Popen(
                [str(PYTHON), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
                cwd=BACKEND,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            processes.append(process)
            base = f"http://127.0.0.1:{port}"
            bases.append(base)
            _wait(base)
    except (OSError, RuntimeError):
        _stop(processes); raise
    return processes, bases


def _stop(processes: list[subprocess.Popen[bytes]]) -> None:
    for process in processes:
        process.terminate()
    for process in processes:
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def _hash(value: dict) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


def _happy(args: argparse.Namespace) -> dict:
    redis_url = _resolve_redis_url(None)
    processes, bases = _start(args.instances, redis_url)
    try:
        token = _login(bases[0])
        run_status, run = _request(
            bases[0], "/api/eval/run", "POST", {"seed": 7, "duration_hours": 1}, token
        )
        if run_status != 200:
            raise RuntimeError(f"evaluation job failed: {run_status} {run}")
        task_id = str(run["task_id"])
        hashes = []
        for base in bases:
            status, result = _request(base, f"/api/eval/results/{task_id}", token=token)
            if status != 200:
                raise RuntimeError(f"job lookup failed on {base}: {status} {result}")
            hashes.append(_hash(result))

        incident_status, incident = _request(
            bases[0], "/api/incidents", "POST", {"title": "Task 7 verifier", "disaster_type": "flood"}, token
        )
        if incident_status not in {200, 201}:
            raise RuntimeError(f"incident setup failed: {incident_status} {incident}")
        incident_id = str(incident["id"])
        ws_url = bases[1].replace("http://", "ws://") + f"/ws/realtime/{incident_id}?token={token}"
        broker = redis.Redis.from_url(redis_url)
        with connect(ws_url, open_timeout=10) as stream:
            time.sleep(1)
            broker.publish(
                "resqnet:realtime",
                json.dumps(
                    {
                        "origin": "task7-verifier",
                        "incident_id": incident_id,
                        "org_id": "org_demo",
                        "message": {"type": "task7", "payload": {"access_policy": "public", "state": "shared"}},
                    },
                    separators=(",", ":"),
                ),
            )
            message = json.loads(stream.recv(timeout=10))
            if message["type"] != "task7":
                raise RuntimeError(f"unexpected fanout message: {message}")
            logout_status, _ = _request(bases[0], "/api/auth/logout", "POST", token=token)
            if logout_status != 204:
                raise RuntimeError(f"logout failed: {logout_status}")
            started = time.monotonic()
            try:
                stream.recv(timeout=args.revocation_deadline_s)
            except ConnectionClosed as error:
                if error.code != args.expect_stream_close_code:
                    raise RuntimeError(f"wrong stream close code: {error.code}") from error
            else:
                raise RuntimeError("revoked stream remained open")
            convergence_seconds = time.monotonic() - started
        return {
            "scenario": args.scenario,
            "instances": args.instances,
            "task_id": task_id,
            "state_hashes": hashes,
            "identical_state_hashes": len(set(hashes)) == 1,
            "fanout": "shared",
            "revocation_convergence_seconds": round(convergence_seconds, 3),
            "stream_close_code": args.expect_stream_close_code,
        }
    finally:
        _stop(processes)


def _partition(args: argparse.Namespace) -> dict:
    processes, bases = _start(args.instances, "redis://127.0.0.1:63999/0")
    try:
        token = _login(bases[0])
        status, _ = _request(bases[0], "/api/auth/me", token=token)
        if args.expect_protected_deny and status not in {401, 403}:
            raise RuntimeError(f"protected endpoint did not deny: {status}")
        ws_url = bases[0].replace("http://", "ws://") + f"/ws/realtime/unknown?token={token}"
        try:
            with connect(ws_url, open_timeout=10) as stream:
                try:
                    stream.recv(timeout=5)
                except ConnectionClosed as error:
                    if error.code != args.expect_stream_close_code:
                        raise RuntimeError(f"wrong stream close code: {error.code}") from error
                else:
                    raise RuntimeError("protected stream remained open during Redis partition")
        except ConnectionClosed as error:
            if error.code != args.expect_stream_close_code:
                raise RuntimeError(f"wrong stream close code: {error.code}") from error
        return {
            "scenario": args.scenario,
            "instances": len(bases),
            "protected_status": status,
            "stream_close_code": args.expect_stream_close_code,
            "authorization": "fail-closed",
        }
    finally:
        _stop(processes)


def _stale_replica(args: argparse.Namespace) -> dict:
    redis_url = _resolve_redis_url(None)
    processes, bases = _start(args.instances, redis_url)
    try:
        token = _login(bases[0])
        logout_status, _ = _request(bases[0], "/api/auth/logout", "POST", token=token)
        if logout_status != 204:
            raise RuntimeError(f"logout failed: {logout_status}")
        redis.Redis.from_url(redis_url).delete("revoked_token:" + hashlib.sha256(token.encode()).hexdigest())
        status, _ = _request(bases[1], "/api/auth/me", token=token)
        if status not in {401, 403}:
            raise RuntimeError(f"stale replica resurrected protected access: {status}")
        ws_url = bases[1].replace("http://", "ws://") + "/ws/realtime/unknown?token=" + token
        try:
            with connect(ws_url, open_timeout=10) as stream:
                stream.recv(timeout=5)
        except ConnectionClosed as error:
            if error.code != args.expect_stream_close_code:
                raise RuntimeError(f"wrong stream close code: {error.code}") from error
        return {
            "scenario": args.scenario,
            "instances": len(bases),
            "protected_status": status,
            "stream_close_code": args.expect_stream_close_code,
            "authorization": "durable-authority-fail-closed",
        }
    finally:
        _stop(processes)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--instances", type=int, default=2)
    parser.add_argument("--scenario", choices=("revoke-and-fanout", "redis-partition", "stale-replica", "split-brain"), required=True)
    parser.add_argument("--revocation-deadline-s", type=int, default=60)
    parser.add_argument("--expect-protected-deny", action="store_true")
    parser.add_argument("--expect-stream-close-code", type=int, default=4401)
    args = parser.parse_args()
    if args.scenario in {"revoke-and-fanout", "stale-replica"} and not _redis_available(_resolve_redis_url(None)):
        print(json.dumps({
            "scenario": args.scenario,
            "status": "DEFERRED_EXTERNAL",
            "reason": "shared Redis is unavailable for multi-instance fanout evidence",
        }, sort_keys=True))
        return 2
    if args.scenario == "revoke-and-fanout":
        result = _happy(args)
    elif args.scenario == "stale-replica":
        result = _stale_replica(args)
    else:
        result = _partition(args)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
