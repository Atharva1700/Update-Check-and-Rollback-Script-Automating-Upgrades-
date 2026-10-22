"""Upgrades the made-up service to a target release. Checks health before and after.
If the new release fails its health check, switches back to the previous release and checks that.

Usage: python -m upgrader.upgrade --target v1.1 --port 8201 [--root .] [--log upgrade.log.jsonl]

Exit codes:
  0  upgraded and the new release is healthy
  1  nothing changed: unknown target, or the current release was unhealthy before the upgrade
  2  new release failed its health check; rolled back, and the previous release is healthy
  3  new release failed AND the rollback is not healthy: needs a person now
"""

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


class Paths:
    def __init__(self, root):
        self.root = Path(root)
        self.service = self.root / "service"
        self.app = self.service / "app.py"
        self.releases = self.service / "releases"
        self.pointer = self.service / "current.txt"


class Service:
    def __init__(self, paths, port):
        self.paths, self.port, self.proc = paths, port, None

    def start(self, version):
        self.proc = subprocess.Popen([
            sys.executable, str(self.paths.app),
            "--release", str(self.paths.releases / version), "--port", str(self.port)])

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            self.proc.wait(timeout=5)
        self.proc = None


def health(port, expect_version, timeout=1.0):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=timeout) as r:
            body = json.loads(r.read())
            return r.status == 200 and body.get("version") == expect_version, body
    except urllib.error.HTTPError as e:
        return False, {"http_status": e.code}
    except Exception as e:  # not listening yet, refused, or timed out
        return False, {"error": type(e).__name__}


def wait_healthy(port, version, attempts=15, delay=0.3):
    body = {}
    for _ in range(attempts):
        ok, body = health(port, version)
        if ok:
            return True, body
        time.sleep(delay)
    return False, body


class Log:
    def __init__(self, path):
        self.path = Path(path) if path else None

    def __call__(self, event, **fields):
        line = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "event": event, **fields}
        print(f"{event:<16} {json.dumps(fields)}")
        if self.path:
            with self.path.open("a") as f:
                f.write(json.dumps(line) + "\n")


def upgrade(paths, target, port, log):
    current = paths.pointer.read_text().strip()
    if not (paths.releases / target / "VERSION").exists():
        log("abort", reason=f"unknown target {target}")
        return 1

    svc = Service(paths, port)
    svc.start(current)
    ok, body = wait_healthy(port, current)
    svc.stop()
    if not ok:
        log("abort", reason=f"current release {current} unhealthy before upgrade", detail=body)
        return 1
    log("pre_check_ok", version=current)

    paths.pointer.write_text(target + "\n")
    log("switched", to=target)
    svc.start(target)
    ok, body = wait_healthy(port, target)
    svc.stop()
    if ok:
        log("upgraded", version=target)
        return 0

    log("health_failed", version=target, detail=body)
    paths.pointer.write_text(current + "\n")
    log("rollback_switch", to=current)
    svc.start(current)
    ok2, body2 = wait_healthy(port, current)
    svc.stop()
    log("rolled_back", version=current, healthy=ok2, detail=body2)
    return 2 if ok2 else 3


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True)
    ap.add_argument("--port", type=int, default=8201)
    ap.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    ap.add_argument("--log", default=None)
    args = ap.parse_args(argv)
    return upgrade(Paths(args.root), args.target, args.port, Log(args.log))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
