#!/usr/bin/env python3
"""Explicitly approved 3B maintenance; not an application deployment.

Only the checksum-pinned reviewed core mutates production metadata. Fresh managed
backup and exact-image isolated round-trip rehearsal must finish first. On an
uncertain write result, stop for attended inspection; never retry or auto-restore.
All subprocess output is retained privately on the host, not echoed to CI.
"""
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import sys
import tempfile
import traceback
import uuid

import phase3_recovery_remote as recovery

CORE_SHA256 = "9699731c843b02c213c99cb4efaa8c79d75dcd6c7fb3752d0b03816b876a1a00"
CONFIRMATIONS = {"apply": "APPLY-PHASE3B-REVIEWED-METADATA", "restore": "RESTORE-PHASE3B-ARCHIVED-METADATA"}
require = recovery.require
GateError = recovery.GateError


def utc_now():
    return dt.datetime.now(dt.timezone.utc)


def validate_window(start, end, *, remaining=0):
    require(all(re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", x) for x in (start, end)),
            "Explicit UTC maintenance-window timestamps required")
    left, right = (dt.datetime.strptime(x, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc) for x in (start, end))
    require(0 < (right-left).total_seconds() <= 3600, "Maintenance window must be at most one hour")
    require(left <= utc_now() and (right-utc_now()).total_seconds() >= remaining,
            "Outside maintenance window or insufficient time remaining")


def validate_inputs(expected_sha, source_sha, action, expected_state, confirmation, start, end, owner, core):
    require(expected_sha == recovery.ROLLBACK_SHA and re.fullmatch(r"[0-9a-f]{40}", source_sha),
            "Exact approved 3A image and reviewed source SHA required")
    require(action in CONFIRMATIONS and confirmation == CONFIRMATIONS[action], "Exact action confirmation required")
    require(re.fullmatch(r"[0-9a-f]{64}", expected_state), "Exact reviewed state SHA-256 required")
    require(owner.strip() and len(owner) <= 120 and not any(ord(c) < 32 for c in owner), "Named attended rollback owner required")
    require(hashlib.sha256(core.encode()).hexdigest() == CORE_SHA256, "Cleanup core changed; re-review and re-inspect")
    validate_window(start, end)


def record(path, value):
    """Durable private operation status, including uncertain commit outcomes."""
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w") as stream:
        os.chmod(temporary, 0o600)
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def cleanup_call(web, core, evidence, label, *, action="inspect", expected="", release=""):
    require(re.fullmatch(r"[0-9a-f]{64}", web), "Invalid exact web container ID")
    require(action in ("inspect", "apply", "restore"), "Unsupported maintenance action")
    operation = "financee_phase3b_" + uuid.uuid4().hex
    options = "-c statement_timeout=30000 -c lock_timeout=2000 -c application_name=" + operation
    if action == "inspect":
        options += " -c default_transaction_read_only=on"
    arguments = ["--action", action]
    if action != "inspect":
        arguments += ["--expected-state-sha256", expected, "--confirmation", CONFIRMATIONS[action], "--backup-release", release]
    # The deadline runs INSIDE the container. Killing a docker CLI alone does
    # not reliably stop its server-side process. An interrupted response is still
    # considered uncertain: commit may have happened immediately before failure.
    driver = f'''import os,signal
os.environ.setdefault("DJANGO_SETTINGS_MODULE","financee.settings")
def deadline(signum, frame):
    raise TimeoutError("Maintenance worker exceeded its bounded deadline")
signal.signal(signal.SIGALRM, deadline)
signal.alarm(90)
try:
    exec(compile({core!r}, "reviewed_phase3b_core", "exec"), {{"__name__": "__main__"}})
finally:
    signal.alarm(0)
    from django.db import connections
    connections.close_all()
'''
    output = recovery.run(["docker", "exec", "-i", "-e", "PGCONNECT_TIMEOUT=10", "-e", "PGOPTIONS=" + options,
                           web, "python", "-", *arguments], input_text=driver,
                          log=evidence / (label + ".log"), timeout=120)
    report = json.loads(output)
    require(report.get("action") == action and report.get("authorizes_cleanup") is False
            and re.fullmatch(r"[0-9a-f]{64}", report.get("state_sha256", "")), "Malformed maintenance result")
    if action == "inspect":
        require(report.get("mode") == "database-enforced-read-only", "Inspection not certified read-only")
    else:
        require(report.get("result") == "PASS" and report.get("unrelated_metadata_preserved") is True,
                "Metadata mutation was not certified")
        require(report.get("archive_state") == ("applied" if action == "apply" else "restored")
                and report.get("column_present") is (action == "restore"), "Unexpected post-mutation state")
    return report


def continuity(web, evidence, label):
    report = json.loads(recovery.run([
        "docker", "exec", "-e", "PGOPTIONS=-c default_transaction_read_only=on", web,
        "python", "manage.py", "serial_only_phase0_audit", "--include-continuity", "--strict-serial"],
        log=evidence / (label + ".json"), timeout=180))
    require(report.get("mode") == "database-enforced-read-only" and report.get("ready_for_phase_1") is True,
            "Serial continuity failed")
    require(type(report.get("database", {}).get("bytes")) is int and report["database"]["bytes"] > 0,
            "Missing database size")
    require(report.get("schemas") and all(s.get("continuity", {}).get("available") is True
            and s["continuity"].get("journal_balanced") is True for s in report["schemas"]), "Missing balanced serial evidence")
    return report


def serial_witness(report, *, include_balances=False):
    # Live business balances may legitimately change. Compare them only inside
    # the disconnected, disposable restored database with no client traffic.
    result = {}
    for schema in report["schemas"]:
        fingerprint = schema["structure"]["fingerprint"]
        require(re.fullmatch(r"[0-9a-f]{64}", fingerprint), "Missing serial structure fingerprint")
        result[schema["schema"]] = [fingerprint]
        if include_balances:
            result[schema["schema"]].append(schema["continuity"]["fingerprint"])
    return result


def candidate_shape(report):
    return {key: report[key] for key in ("company_count", "permissions", "direct_grant_count",
                                        "group_grant_count", "retired_feature_occurrences", "column_present")}


def rehearse(compose, env, before, core, evidence, action, release, live_metadata, live_serial):
    project = compose[compose.index("--project-name") + 1]
    require(re.fullmatch(r"dbbackup_rehearsal_phase3_[0-9a-f]{32}", project), "Rehearsal project is not uniquely isolated")
    web = recovery.run([*compose, "ps", "-q", "web"], env=env)
    require(web != before["web"]["id"], "Refusing production container as rehearsal target")
    first = cleanup_call(web, core, evidence, "rehearsal-before")
    require(candidate_shape(first) == candidate_shape(live_metadata), "Restored candidate counts differ from reviewed live state")
    initial_serial = continuity(web, evidence, "rehearsal-continuity-before")
    require(serial_witness(initial_serial) == serial_witness(live_serial), "Restored serial structures differ from production")
    current = first
    reverse = "restore" if action == "apply" else "apply"
    for index, step in enumerate((action, reverse, action)):
        current = cleanup_call(web, core, evidence, f"rehearsal-{index}-{step}", action=step,
                               expected=current["state_sha256"], release=release)
        checked = continuity(web, evidence, f"rehearsal-{index}-continuity")
        require(serial_witness(checked, include_balances=True) == serial_witness(initial_serial, include_balances=True),
                "Serial structure or business continuity changed in isolated rehearsal")
        if index == 1:
            require(candidate_shape(current) == candidate_shape(first), "Isolated reversal did not restore metadata shape")
    # Recreate ONLY disposable web. Production never restarts or switches image.
    recovery.run([*compose, "up", "-d", "--force-recreate", "--wait", "--wait-timeout", "180", "web"],
                 env=env, log=evidence / "rehearsal-old-image-startup.log", timeout=240)
    restarted = recovery.run([*compose, "ps", "-q", "web"], env=env)
    require(restarted != before["web"]["id"], "Unexpected production container after rehearsal restart")
    observed = recovery.run(["docker", "inspect", "--format", "{{.Image}}|{{.HostConfig.Memory}}|{{.HostConfig.NanoCpus}}", restarted])
    memory, nano = recovery.LIMITS["web"]
    require(observed == f"{before['web']['image']}|{memory}|{nano}", "Recreated rehearsal image/resource mismatch")
    after = cleanup_call(restarted, core, evidence, "rehearsal-after-startup")
    require(after["state_sha256"] == current["state_sha256"], "Published image startup changed cleanup state")
    checked = continuity(restarted, evidence, "rehearsal-continuity-after-startup")
    require(serial_witness(checked, include_balances=True) == serial_witness(initial_serial, include_balances=True),
            "Published image startup changed isolated serial continuity")
    return {"result": "PASS", "round_trip": True, "published_image_startup": True, "serial_continuity_preserved": True}


def http_check(evidence):
    recovery.run(["curl", "-fsS", "--max-time", "30", "--retry", "3", "--retry-delay", "2",
                  "--retry-all-errors", "-o", "/dev/null", "http://localhost/authentication/login/"],
                 log=evidence / "production-http.log", timeout=150)


def final_review(compose, expected_sha, before, core, evidence):
    results = {}
    for name, check in (
        ("containers", lambda: recovery.snapshot(compose, expected_sha)),
        ("metadata", lambda: cleanup_call(before["web"]["id"], core, evidence, "production-final-state")),
        ("continuity", lambda: continuity(before["web"]["id"], evidence, "production-final-continuity")),
        ("http", lambda: http_check(evidence)),
    ):
        try:
            results[name] = check()
        except Exception as exc:
            results[name] = None
            results[name + "_failed"] = True
            record(evidence / ("final-" + name + "-failure.json"), {"type": type(exc).__name__, "message": str(exc)})
    results["passed"] = (not any(k.endswith("_failed") for k in results) and results.get("containers") == before)
    return results


def execute(app_dir, expected_sha, source_sha, action, expected_state, confirmation, start, end, owner, core):
    require(os.geteuid() == 0, "Root execution required")
    validate_inputs(expected_sha, source_sha, action, expected_state, confirmation, start, end, owner, core)
    app = Path(app_dir)
    require(app.is_absolute() and (app / "deploy/.env").is_file(), "Exact production application directory unavailable")
    require(recovery.PASSPHRASE.is_file() and recovery.PASSPHRASE.stat().st_size > 0, "Managed backup passphrase unavailable")
    for name, expected in recovery.HOST_HASHES.items():
        require(recovery.sha256(app / name) == expected, "Host helper drift; review required")
    os.chdir(app / "deploy")
    compose = ["docker", "compose", "--env-file", str(app / "deploy/.env"), "-f", "docker-compose.yml"]
    if Path("docker-compose.tls.yml").is_file():
        compose += ["-f", "docker-compose.tls.yml"]
    before = recovery.snapshot(compose, expected_sha)
    recovery.capacity()
    evidence = recovery.BACKUP_ROOT / "phase3b-cleanup-evidence" / (utc_now().strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex)
    evidence.mkdir(mode=0o700, parents=True)
    evidence.parent.chmod(0o700)
    print(f"PHASE3B_EVIDENCE_DIR={evidence}", flush=True)
    status = {"source_sha": source_sha, "deployed_sha": expected_sha, "action": action,
              "expected_state_sha256": expected_state, "mutation_outcome": "not_attempted", "result": "FAIL"}
    record(evidence / "intent.json", {**status, "window_start": start, "window_end": end, "rollback_owner": owner})
    record(evidence / "status.json", status)
    failure = None
    committed = None
    try:
        initial = cleanup_call(before["web"]["id"], core, evidence, "production-before-state")
        require(initial["state_sha256"] == expected_state, "Reviewed target fingerprint changed; new inspection/approval required")
        require(initial["archive_state"] in (("absent", "restored") if action == "apply" else ("applied",)),
                "Operation already applied or not applicable; do not retry automatically")
        baseline = continuity(before["web"]["id"], evidence, "production-before-continuity")
        http_check(evidence)
        release, bundle = recovery.fresh_backup(evidence)
        status["backup_release"] = release
        required_free = max(1024**3, baseline["database"]["bytes"] * 4 + bundle.stat().st_size * 2)
        for storage in (recovery.run(["docker", "info", "--format", "{{.DockerRootDir}}"]), tempfile.gettempdir()):
            require(shutil.disk_usage(storage).free >= required_free, "Insufficient storage for isolated cleanup rehearsal")
        restored = recovery.restore(before, bundle, evidence, verifier=lambda c, e:
            rehearse(c, e, before, core, evidence, action, release, initial, baseline))
        require(restored.get("verification", {}).get("result") == "PASS", "Missing isolated cleanup certification")
        status["recovery"] = restored
        # Restore() returns only after exact disposable resource removal succeeds.
        require(recovery.snapshot(compose, expected_sha) == before, "Production containers changed before mutation")
        recovery.capacity()
        validate_window(start, end, remaining=120)
        immediate = cleanup_call(before["web"]["id"], core, evidence, "production-prewrite-state")
        require(immediate["state_sha256"] == expected_state, "Metadata drift after rehearsal; stop without cleanup")
        current_serial = continuity(before["web"]["id"], evidence, "production-prewrite-continuity")
        require(serial_witness(current_serial) == serial_witness(baseline), "Serial structure changed during rehearsal")
        status["mutation_outcome"] = "unknown"
        record(evidence / "status.json", status)  # Durable BEFORE sending a write.
        committed = cleanup_call(before["web"]["id"], core, evidence, "production-mutation", action=action,
                                 expected=expected_state, release=release)
        status["mutation_outcome"] = "confirmed_committed"
        status["result_state_sha256"] = committed["state_sha256"]
        record(evidence / "status.json", status)
    except Exception as exc:
        failure = exc
        # Diagnostic details can contain private subprocess context. Persist them
        # only in the protected directory, never in the printed summary.
        record(evidence / "failure.json", {"type": type(exc).__name__, "message": str(exc),
               "traceback": traceback.format_exc()})
    finally:
        checks = final_review(compose, expected_sha, before, core, evidence)
        status["final_checks_passed"] = checks["passed"]
        if committed is not None and checks["passed"]:
            valid = (checks["metadata"]["state_sha256"] == committed["state_sha256"]
                     and serial_witness(checks["continuity"]) == serial_witness(baseline))
            if not valid:
                status["final_checks_passed"] = False
                failure = failure or GateError("Post-mutation state drift; attended review required")
        elif not checks["passed"]:
            failure = failure or GateError("Final production checks failed; attended review required")
        if failure is None and committed is not None:
            status["result"] = "PASS"
        record(evidence / "status.json", status)
        print(json.dumps(status, sort_keys=True), flush=True)
    if failure is not None:
        raise GateError("Maintenance failed; inspect protected status and evidence. Do not retry or restore automatically.") from failure
    require(status["result"] == "PASS", "No confirmed maintenance result")
    print("PHASE3B_RESULT=PASS\nPHASE3B_OWNER_MANUAL_CHECK_REQUIRED=yes", flush=True)
    return status


def main(core):
    os.umask(0o077)
    def interrupted(signum, frame):
        raise GateError("Maintenance interrupted; attended outcome inspection required")
    for signum in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT, signal.SIGALRM):
        signal.signal(signum, interrupted)
    require(len(sys.argv) == 10, "Expected app, image/source SHAs, action, state digest, confirmation, UTC window and owner")
    # Shared with the approved recovery controller, in addition to workflow
    # production-deploy concurrency and the core's transaction advisory lock.
    with recovery.LOCK_FILE.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise GateError("Another production recovery/cleanup holds the host lock") from exc
        signal.alarm(2100)
        try:
            return execute(*sys.argv[1:], core)
        finally:
            signal.alarm(0)


if __name__ == "__main__":
    raise SystemExit("Use the reviewed stdin bundle; direct execution is disabled")
