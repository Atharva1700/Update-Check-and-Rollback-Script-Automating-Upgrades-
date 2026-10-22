import json
import shutil
import socket
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from upgrader import upgrade  # noqa: E402


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def root(tmp_path):
    """A private copy of the made-up service, so tests never touch the real pointer file."""
    dst = tmp_path / "project"
    shutil.copytree(ROOT / "service", dst / "service")
    return dst


def set_current(root, version):
    (root / "service" / "current.txt").write_text(version + "\n")


def current(root):
    return (root / "service" / "current.txt").read_text().strip()


def events(path):
    return [json.loads(line)["event"] for line in path.read_text().splitlines()]


def test_good_upgrade_switches_and_is_healthy(root, tmp_path):
    set_current(root, "v1.0")
    log = tmp_path / "log.jsonl"
    code = upgrade.main(["--target", "v1.1", "--port", str(free_port()), "--root", str(root),
                         "--log", str(log)])
    assert code == 0
    assert current(root) == "v1.1"
    assert events(log) == ["pre_check_ok", "switched", "upgraded"]


def test_bad_release_is_rolled_back(root, tmp_path):
    set_current(root, "v1.1")
    log = tmp_path / "log.jsonl"
    code = upgrade.main(["--target", "v1.2-bad", "--port", str(free_port()), "--root", str(root),
                         "--log", str(log)])
    assert code == 2
    assert current(root) == "v1.1"
    assert events(log) == ["pre_check_ok", "switched", "health_failed", "rollback_switch", "rolled_back"]
    rolled = json.loads(log.read_text().splitlines()[-1])
    assert rolled["healthy"] is True and rolled["version"] == "v1.1"


def test_unknown_target_changes_nothing(root, tmp_path):
    set_current(root, "v1.0")
    log = tmp_path / "log.jsonl"
    code = upgrade.main(["--target", "v9.9", "--port", str(free_port()), "--root", str(root),
                         "--log", str(log)])
    assert code == 1
    assert current(root) == "v1.0"
    assert events(log) == ["abort"]


def test_unhealthy_current_release_aborts_before_any_switch(root, tmp_path):
    set_current(root, "v1.2-bad")  # the release we are on is already broken
    log = tmp_path / "log.jsonl"
    code = upgrade.main(["--target", "v1.1", "--port", str(free_port()), "--root", str(root),
                         "--log", str(log)])
    assert code == 1
    assert current(root) == "v1.2-bad"
    assert events(log) == ["abort"]


def test_health_check_requires_the_expected_version(root):
    """A release that answers 200 but reports the wrong version must not pass the check."""
    port = free_port()
    svc = upgrade.Service(upgrade.Paths(root), port)
    svc.start("v1.0")
    try:
        ok, body = upgrade.wait_healthy(port, "v1.0")
        assert ok and body["version"] == "v1.0"
        ok, body = upgrade.health(port, "v1.1")
        assert not ok and body["version"] == "v1.0"
    finally:
        svc.stop()


def test_bad_release_fails_health_directly(root):
    port = free_port()
    svc = upgrade.Service(upgrade.Paths(root), port)
    svc.start("v1.2-bad")
    try:
        ok, body = upgrade.wait_healthy(port, "v1.2-bad", attempts=5, delay=0.2)
        assert not ok and body == {"http_status": 500}
    finally:
        svc.stop()
