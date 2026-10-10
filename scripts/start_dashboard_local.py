"""Run the workstation dashboard stack using backend/.venv; Ctrl-C stops owned processes.

Uses the extracted PostgreSQL/Redis runtime prepared under /tmp/ieee-runtime.
Existing services are reused. No system installation or database reseeding.
"""

from __future__ import annotations

import os
import socket
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = Path(os.environ.get('DASHBOARD_RUNTIME', '/tmp/ieee-runtime'))
PYTHON = ROOT / 'backend/.venv/bin/python'


def listening(port: int) -> bool:
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=0.5):
            return True
    except OSError:
        return False


def main() -> None:
    if not PYTHON.exists() or not (ROOT / 'backend/.env').exists():
        raise SystemExit('Prepare backend/.venv and backend/.env first; see docs/LOCAL_DASHBOARD.md.')
    if not (ROOT / 'frontend/.env.local').exists():
        raise SystemExit('Configure frontend/.env.local; see docs/LOCAL_DASHBOARD.md.')
    pg = RUNTIME / 'root/usr/lib/postgresql/18/bin/postgres'
    redis = RUNTIME / 'root/usr/bin/redis-server'
    runtime_env = {**os.environ,
        'LD_LIBRARY_PATH': str(RUNTIME / 'root/usr/lib/x86_64-linux-gnu'),
        'PROJ_DATA': str(RUNTIME / 'root/usr/share/proj')}
    services = [
        ('postgres', 55432, ROOT, [str(pg), '-D', str(RUNTIME / 'pgdata'), '-p', '55432',
            '-k', str(RUNTIME), '-c', 'listen_addresses=127.0.0.1', '-c',
            'shared_preload_libraries=age', '-c', 'max_connections=40'], runtime_env),
        ('redis', 56379, ROOT, [str(redis), '--bind', '127.0.0.1', '--port', '56379',
            '--dir', str(RUNTIME), '--save', '', '--appendonly', 'no'], runtime_env),
        ('api', 8000, ROOT / 'backend', [str(PYTHON), '-m', 'uvicorn', 'app.main:app',
            '--host', '127.0.0.1', '--port', '8000'], {**os.environ, 'OTEL_EXPORTER': 'none'}),
        ('mesh', 8001, ROOT / 'modules', [str(PYTHON), '-m', 'uvicorn',
            'ble_localization.main:app', '--host', '127.0.0.1', '--port', '8001'], os.environ.copy()),
        ('thermal', 8765, ROOT / 'modules/route_engine', [str(PYTHON), '-m', 'uvicorn',
            'thermal_server:app', '--host', '127.0.0.1', '--port', '8765'], os.environ.copy()),
        ('frontend', 5173, ROOT / 'frontend', ['npm', 'run', 'dev'], os.environ.copy()),
    ]
    owned = []
    logs = []
    log_dir = RUNTIME / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)
    try:
        for name, port, cwd, command, env in services:
            if listening(port):
                print(f'{name}: already running on {port}', flush=True)
                continue
            if name in {'postgres', 'redis'} and not Path(command[0]).exists():
                raise RuntimeError(f'{name} runtime missing; see docs/LOCAL_DASHBOARD.md.')
            log_path = log_dir / f'{name}.log'
            log = log_path.open('a')
            log_path.chmod(0o600)
            logs.append(log)
            process = subprocess.Popen(command, cwd=cwd, env=env, stdout=log, stderr=log)
            owned.append((name, process))
            deadline = time.monotonic() + 30
            while not listening(port):
                if process.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError(f'{name} failed to start; inspect {log_path}')
                time.sleep(0.2)
            print(f'{name}: started on {port}', flush=True)
        print('Dashboard: http://localhost:5173/dashboard', flush=True)
        if not owned:
            return
        while all(process.poll() is None for _, process in owned):
            time.sleep(1)
        raise RuntimeError('A service stopped; inspect the local runtime logs.')
    except KeyboardInterrupt:
        pass
    finally:
        for _, process in reversed(owned):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        for log in logs:
            log.close()


if __name__ == '__main__':
    main()
