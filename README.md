# Update Check and Rollback Script

A script that upgrades a made-up service to a target release, checks its health before and after,
and rolls back to the previous release automatically if the new one fails. Runs from a GitHub
Actions workflow. Self-directed, built as practice.

**Made-up service only.** `service/app.py` is a small HTTP service on 127.0.0.1 with a `/health`
endpoint. Releases are folders in `service/releases/`. A release with a `BROKEN` file fails its
health check, which is how the rollback path gets exercised.

## What the upgrade does

1. Checks the target release exists. If not, stops without changing anything.
2. Starts the current release and checks its health. If it is already unhealthy, stops without
   changing anything.
3. Switches the pointer (`service/current.txt`) to the target, starts it, and checks its health.
   The health check requires the expected version, so a release that answers with the wrong
   version fails.
4. If the new release is unhealthy, switches the pointer back, starts the previous release, and
   checks it.

Every step is written to a JSON-lines log.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Upgraded, and the new release is healthy |
| 1 | Nothing changed (unknown target, or the current release was unhealthy) |
| 2 | New release failed; rolled back; previous release is healthy |
| 3 | New release failed and the rollback is not healthy: a person needs to act now |

## Run

```bash
echo v1.0 > service/current.txt
python3 -m upgrader.upgrade --target v1.1 --port 8201 --log upgrade.log.jsonl        # exit 0
python3 -m upgrader.upgrade --target v1.2-bad --port 8202 --log upgrade.log.jsonl    # exit 2
python3 -m pytest -q                                                                  # 6 tests
```

Demo output from the second command:

```
pre_check_ok     {"version": "v1.1"}
switched         {"to": "v1.2-bad"}
health_failed    {"version": "v1.2-bad", "detail": {"http_status": 500}}
rollback_switch  {"to": "v1.1"}
rolled_back      {"version": "v1.1", "healthy": true, ...}
```

## Verified and not verified

| Check | Result |
|---|---|
| 6 tests: good upgrade, bad release rolled back, unknown target, unhealthy starting point, wrong version rejected, bad release fails health | pass |
| Command-line demo: good upgrade exits 0; broken release exits 2 and leaves v1.1 live | pass |
| GitHub Actions workflow | **Not run.** Written and reviewed only. |

## Limits

- The "service" is a local process that the script starts and stops itself. A real deployment has a
  process manager, a load balancer and a rollout strategy, none of which are here.
- Health is checked once after a switch, with 15 short retries. A failure that appears minutes
  later is not caught.
- The pointer is a text file. Two upgrades running at once could interleave; there is no lock.
- Rollback is to the previous pointer value only, not to an arbitrary earlier release.
