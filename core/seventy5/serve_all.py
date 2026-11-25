"""Everything the phone needs, on this laptop, in one window: `python -m seventy5.serve_all`.

Why: on demo day nobody should type an IP or juggle three terminals. This starts the core
(8000), PortMax's phone API (8002) and the mock college portal (8765) on every interface; tells
PortMax where the phone reaches the portal (this laptop's LAN address); and restarts PortMax by
itself when that address changes, as it does when a phone hotspot restarts. The app finds the
laptop on its own by asking the local network for GET /api/health.
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

CORE = Path(__file__).resolve().parents[1]
DATA = CORE / "data"
PORTS = {"core": 8000, "portmax": 8002, "portal": 8765}
# The phone polls /api/cards every 7 s; printing each poll would bury everything else.
QUIET = ('"GET /api/cards HTTP/1.1" 200', '"GET /api/health HTTP/1.1" 200')


def lan_ip() -> str | None:
    """The address this laptop uses on its network. UDP connect sends no packet."""
    for target in ("8.8.8.8", "10.255.255.255", "192.168.255.255", "172.31.255.255"):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect((target, 80))
                ip = str(s.getsockname()[0])
        except OSError:
            continue
        if not ip.startswith(("127.", "0.")):
            return ip
    return None


def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def answers(port: int, path: str = "/") -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=1):
            return True
    except Exception:  # noqa: BLE001 - any answer, even an error page, means it is up
        return False


class Service:
    def __init__(self, name: str, args: list[str], env: dict[str, str]) -> None:
        self.name, self.args, self.env = name, args, env
        self.proc: subprocess.Popen[str] | None = None
        self.stopping = False

    def start(self) -> None:
        self.stopping = False
        self.proc = subprocess.Popen(
            [sys.executable, *self.args],
            cwd=CORE,
            env=self.env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        threading.Thread(target=self._relay, args=(self.proc,), daemon=True).start()

    def _relay(self, proc: subprocess.Popen[str]) -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            if not any(q in line for q in QUIET):
                print(f"[{self.name:7}] {line.rstrip()}", flush=True)

    def stop(self) -> None:
        self.stopping = True
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    def died(self) -> bool:
        return self.proc is not None and not self.stopping and self.proc.poll() is not None


def banner(ip: str | None) -> None:
    where = f"http://{ip}:{PORTS['core']}" if ip else "(no network found yet)"
    print(
        "\n"
        "  ============================================================\n"
        "   7even5ive is running on this laptop\n"
        f"   Address: {where}\n"
        "   Phone: same Wi-Fi or hotspot, open 7even5ive. It finds this\n"
        "   laptop by itself. Portal login: USN 1MC24CS042, DOB 14/08/2005,\n"
        "   code PM42X, then 2345.\n"
        "   Stop: Ctrl+C or close this window.\n"
        "  ============================================================\n",
        flush=True,
    )


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

    # Every way of stopping (Ctrl+C, closing the window, a kill) stops the servers too, so
    # their ports are free for the next start.
    stop_signals = [getattr(signal, n) for n in ("SIGINT", "SIGTERM", "SIGBREAK", "SIGHUP")
                    if hasattr(signal, n)]

    def interrupt(*_: object) -> None:
        # Once only: a second signal must not cut the shutdown short.
        for sig in stop_signals:
            signal.signal(sig, signal.SIG_IGN)
        raise KeyboardInterrupt

    for sig in stop_signals:
        signal.signal(sig, interrupt)
    busy = [f"{name} ({port})" for name, port in PORTS.items() if not port_free(port)]
    if busy:
        print(
            "Already in use: " + ", ".join(busy) + ".\n"
            "Close the other windows running 7even5ive's servers, then start again."
        )
        return 1
    DATA.mkdir(exist_ok=True)

    env = dict(os.environ)
    env.setdefault("PORTMAX_DATABASE_URL", f"sqlite:///{(DATA / 'portmax.db').as_posix()}")
    env.setdefault("PORTMAX_DEV_TOKENS", "demo-student-token:demo")
    env.update(HOST="0.0.0.0", PORT=str(PORTS["core"]), PYTHONUNBUFFERED="1",
               PYTHONIOENCODING="utf-8")
    env.pop("PORTMAX_PORTAL_ORIGINS", None)  # set below from the address we find

    ip = lan_ip()

    def portmax_args(address: str | None) -> list[str]:
        args = ["-m", "portmax.cli", "api", "--host", "0.0.0.0", "--port", str(PORTS["portmax"])]
        if address:
            args += ["--portal-origin", f"mockcollege=http://{address}:{PORTS['portal']}"]
        return args

    services = {
        "portal": Service("portal", ["-m", "portmax.cli", "mock", "serve", "--host", "0.0.0.0",
                                     "--port", str(PORTS["portal"]), "--fixed-captcha"], env),
        "portmax": Service("portmax", portmax_args(ip), env),
        "core": Service("core", ["-m", "seventy5.demo"], env),
    }
    for service in services.values():
        service.start()

    def ready() -> bool:
        return (answers(PORTS["core"], "/api/health")
                and answers(PORTS["portmax"], "/v1/runner.js")
                and answers(PORTS["portal"]))

    deadline = time.time() + 120
    while time.time() < deadline and not ready():
        if any(s.died() for s in services.values()):
            break
        time.sleep(1)
    banner(ip)

    try:
        while True:
            time.sleep(5)
            now = lan_ip()
            if now and now != ip:
                print(f"\n  Network changed: {ip} -> {now}. Restarting PortMax for the new "
                      "address; the phone finds the laptop again by itself.", flush=True)
                ip = now
                services["portmax"].stop()
                services["portmax"].args = portmax_args(ip)
                services["portmax"].start()
                banner(ip)
            for name, service in services.items():
                if service.died():
                    print(f"\n  {name} stopped unexpectedly; starting it again.", flush=True)
                    service.start()
    except KeyboardInterrupt:
        print("\nStopping...", flush=True)
    finally:
        for service in services.values():
            service.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
