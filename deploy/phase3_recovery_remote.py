#!/usr/bin/env python3
"""Attended 3B recovery evidence, not cleanup. Stream exact source over SSH.

Production is only inspected and backed up by its existing encrypted-backup
service. Restore/startup writes and resource removal target a unique disposable
project. Raw logs stay root-only because existing preflight prints names.
"""
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import shutil
import subprocess
import sys
import tempfile
import uuid


ROLLBACK_SHA = "497b6650ed678bc462f85de6bff14692bffd6ace"
CONFIRMATION = "VERIFY-PHASE3B-BACKUP-RESTORE-NO-CLEANUP"
BACKUP_ROOT = Path("/var/lib/financee-backup")
PASSPHRASE = Path("/etc/financee-backup/passphrase")
LOCK_FILE = Path("/var/lock/financee-phase3-recovery.lock")
# Refuse changed host helpers without a new source review. No git pull on EC2.
HOST_HASHES = {
    "deploy/docker-compose.yml": "ff147c3786bb5ebf009e75d23916268f07519967499b23de961be05034c0d07a",
    "deploy/restore_database_backup_rehearsal.sh": "47d92415a4ef280ae48fbfa191f75016bb7672698b9fd77de802d9395caf226d",
    "deploy/database_backup_status.sh": "f5f8180addae3ec0f4340dabaa91ab33e850105a77f6e2214d9369367935c0bc",
    "build_multitenant_db.sql": "7f92b288cc7729728ac01382a07fd0549a89db20fda3f5b007d276102e832eb0",
}
LIMITS = {"db": (768 * 1024**2, 500000000),
          "web": (512 * 1024**2, 350000000),
          "redis": (64 * 1024**2, 50000000)}


class GateError(RuntimeError):
    pass


def require(ok, message):
    if not ok:
        raise GateError(message)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run(args, *, env=None, log=None, timeout=120):
    # Do not inherit DB/Compose settings into a different environment.
    clean = {k: os.environ[k] for k in ("PATH", "HOME", "LANG", "LC_ALL") if k in os.environ}
    clean.update(env or {})
    process = subprocess.Popen(args, env=clean, text=True, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, start_new_session=True)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except BaseException as exc:
        # Stop the whole helper process group before attempting stack cleanup.
        # Otherwise a timed-out shell could leave a child compose command running.
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            stdout, stderr = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate()
        if log:
            log.write_text(stdout + stderr)
            log.chmod(0o600)
        if isinstance(exc, subprocess.TimeoutExpired):
            raise GateError("Operation timed out; recovery is not certified") from exc
        raise
    if log:
        log.write_text(stdout + stderr)
        log.chmod(0o600)
    require(process.returncode == 0, "Operation failed; inspect protected host evidence")
    return stdout.strip()


def key_values(text):
    result = {}
    for line in text.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
                continue
            require(key not in result, "Duplicate evidence key")
            result[key] = value
    return result


def snapshot(compose, expected_sha):
    result = {}
    for service in ("web", "db", "redis", "nginx"):
        cid = run([*compose, "ps", "-q", service])
        require(re.fullmatch(r"[0-9a-f]{64}", cid), "Expected exactly one running service container")
        raw = run(["docker", "inspect", "--format",
                   "{{.Image}}|{{.Config.Image}}|{{.State.Running}}|"
                   "{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}", cid])
        fields = raw.split("|")
        require(len(fields) == 4, "Unexpected container inspection response")
        image_id, tag, running, health = fields
        require(re.fullmatch(r"sha256:[0-9a-f]{64}", image_id), "Invalid running image identity")
        require(running == "true" and health in ("healthy", "none"), "Production service unhealthy")
        if service in ("web", "db"):
            require(health == "healthy", "Production web/database health is not ready")
        if service == "web":
            require(tag == f"ghcr.io/maaz-bin-haider/financee-web:{expected_sha}",
                    "Deployed image does not match approved 3A")
        require(run(["docker", "image", "inspect", "--format", "{{.Architecture}}", image_id]) == "arm64",
                "Production image is not ARM64")
        result[service] = {"id": cid, "image": image_id}
    return result


def production_audits(before, evidence, label):
    web = before["web"]["id"]
    for command, args in (
        ("serial_only_phase3_audit", ["--strict"]),
        ("serial_only_phase0_audit", ["--include-continuity", "--strict-serial"]),
    ):
        text = run(["docker", "exec", "-e", "PGOPTIONS=-c default_transaction_read_only=on",
                    web, "python", "manage.py", command, *args],
                   log=evidence / f"production-{label}-{command}.json", timeout=180)
        report = json.loads(text)
        require(report.get("mode") == "database-enforced-read-only", "Production audit was not read-only")
        if command == "serial_only_phase3_audit":
            require(report.get("inventory_review_ready") is True and report.get("authorizes_cleanup") is False,
                    "Metadata inventory is not ready")
        else:
            require(report.get("ready_for_phase_1") is True, "Strict serial continuity failed")
            db_bytes = report.get("database", {}).get("bytes")
            require(type(db_bytes) is int and db_bytes > 0, "Missing database size evidence")
    return db_bytes


def capacity():
    mem = re.search(r"^MemAvailable:\s+(\d+) kB$", Path("/proc/meminfo").read_text(), re.M)
    require(mem and int(mem[1]) >= 1572864, "Less than 1.5 GiB host memory available; stop and review capacity")
    root = run(["docker", "info", "--format", "{{.DockerRootDir}}"])
    require(root.startswith("/"), "Docker storage path unavailable")
    require(shutil.disk_usage(root).free >= 1024**3, "Less than 1 GiB Docker storage free")


def fresh_backup(evidence):
    started = int(dt.datetime.now(dt.timezone.utc).timestamp())
    run(["systemctl", "start", "financee-db-backup.service"], log=evidence / "backup-service.log", timeout=600)
    status = key_values(run(["bash", "database_backup_status.sh"], log=evidence / "backup-status.log"))
    state = key_values((BACKUP_ROOT / "last-success.env").read_text())
    release = state.get("LAST_RELEASE", "")
    require(re.fullmatch(r"db-backup-[0-9]{8}T[0-9]{6}Z", release), "Invalid managed backup release")
    created = dt.datetime.strptime(release[len("db-backup-"):], "%Y%m%dT%H%M%SZ").replace(tzinfo=dt.timezone.utc)
    require(started <= int(created.timestamp()) <= int(dt.datetime.now(dt.timezone.utc).timestamp()),
            "Backup is not from this operation")
    require(state.get("REMOTE_VERIFIED") == "true" and status.get("REMOTE_BACKUP_STATUS") == "FRESH"
            and status.get("REMOTE_LAST_RELEASE") == release and status.get("LOCAL_LAST_RELEASE") == release,
            "Fresh remotely verified backup state mismatch")
    name = f"financee-db-{release[len('db-backup-'):]}.dump.tar.enc"
    require(state.get("LAST_BACKUP_FILE") == name, "Unexpected backup filename in service state")
    bundle = BACKUP_ROOT / name
    sidecar = BACKUP_ROOT / (name + ".sha256")
    require(bundle.is_file() and not bundle.is_symlink() and sidecar.is_file() and not sidecar.is_symlink(),
            "Managed local backup missing or symlinked")
    parts = sidecar.read_text().split()
    require(len(parts) == 2 and parts[1] == name and parts[0] == sha256(bundle), "Encrypted checksum mismatch")
    require(str(bundle.stat().st_size) == state.get("LAST_BACKUP_BYTES"), "Managed backup size mismatch")
    return release, bundle


def override_config(before):
    services = {}
    for service, (memory, nano) in LIMITS.items():
        services[service] = {
            "image": before[service]["image"], "pull_policy": "never", "restart": "no",
            "deploy": {"resources": {"limits": {"memory": str(memory), "cpus": str(nano / 10**9)}}},
        }
    services["db"]["command"] = ["postgres", "-c", "max_connections=30", "-c", "shared_buffers=128MB",
                                  "-c", "effective_cache_size=384MB", "-c", "work_mem=2MB",
                                  "-c", "maintenance_work_mem=64MB"]
    services["web"]["environment"] = {"WEB_CONCURRENCY": "1", "GUNICORN_THREADS": "2"}
    return {"services": services, "networks": {"default": {"internal": True}}}


def no_resources(project):
    for args in (["ps", "-aq"], ["volume", "ls", "-q"], ["network", "ls", "-q"]):
        require(not run(["docker", *args, "--filter", f"label=com.docker.compose.project={project}"]),
                "Disposable project collision or incomplete cleanup")


def validate_config(config, before, project):
    for service, (memory, nano) in LIMITS.items():
        current = config["services"][service]
        limits = current["deploy"]["resources"]["limits"]
        require(current["image"] == before[service]["image"] and current.get("pull_policy") == "never",
                "Restore image pin/pull policy mismatch")
        require(int(limits["memory"]) == memory and float(limits["cpus"]) == nano / 10**9,
                "Restore resource limit mismatch")
        require(not current.get("ports") and not current.get("network_mode") and not current.get("privileged"),
                "Unexpected restore network/privilege exposure")
        for mount in current.get("volumes", []):
            require(mount["type"] == "volume" or (
                service == "db" and mount["type"] == "bind" and mount.get("read_only") is True
                and mount["target"] == "/docker-entrypoint-initdb.d/01_build.sql"), "Unexpected restore bind mount")
    for volume in config["volumes"].values():
        require(not volume.get("external") and volume["name"].startswith(project + "_"),
                "Restore volume is not isolated")
    for network in config["networks"].values():
        require(not network.get("external") and network.get("internal") is True
                and network["name"].startswith(project + "_"), "Restore network is not isolated")


def restore(before, bundle, evidence):
    work = Path(tempfile.mkdtemp(prefix="financee-phase3-recovery-"))
    project = "dbbackup_rehearsal_phase3_" + uuid.uuid4().hex
    env_file = work / "restore.env"
    override = work / "restore.json"
    env_file.write_text("\n".join([
        "SECRET_KEY=" + uuid.uuid4().hex + uuid.uuid4().hex, "DEBUG=False",
        "ALLOWED_HOSTS=localhost,127.0.0.1", "CSRF_TRUSTED_ORIGINS=http://localhost",
        "DB_NAME=financee_phase3_restore", "DB_USER=financee_phase3_restore",
        "DB_PASSWORD=" + uuid.uuid4().hex + uuid.uuid4().hex, "DB_HOST=db", "DB_PORT=5432", "",
    ]))
    env_file.chmod(0o600)
    override.write_text(json.dumps(override_config(before)))
    restore_env = {"WEB_IMAGE": before["web"]["image"], "WEB_ENV_FILE": str(env_file)}
    compose = ["docker", "compose", "--project-name", project, "--env-file", str(env_file),
               "-f", "docker-compose.yml", "-f", str(override)]
    attempted = False
    cleaned = False
    try:
        no_resources(project)
        config = json.loads(run([*compose, "config", "--format", "json"], env=restore_env))
        validate_config(config, before, project)
        # Keep a verified encrypted copy during restore: the existing backup
        # timer legitimately retains only its newest local recovery point.
        copied = work / bundle.name
        shutil.copyfile(bundle, copied)
        shutil.copyfile(Path(str(bundle) + ".sha256"), Path(str(copied) + ".sha256"))
        attempted = True
        output = run(["bash", "restore_database_backup_rehearsal.sh"], timeout=900,
                     log=evidence / "restore-private.log", env={**restore_env,
                         "BACKUP_FILE": str(copied), "BACKUP_PASSPHRASE_FILE": str(PASSPHRASE),
                         "RESTORE_ENV_FILE": str(env_file), "RESTORE_PROJECT": project,
                         "RESTORE_COMPOSE_OVERRIDE": str(override), "KEEP_RESTORE_STACK": "1"})
        result = key_values(output)
        require(result.get("RESTORE_RESULT") == "PASS", "Restore helper did not certify success")
        require(result.get("RESTORE_RTO_SECONDS", "").isdigit(), "Missing restore duration")
        for service, (memory, nano) in LIMITS.items():
            cid = run([*compose, "ps", "-q", service], env=restore_env)
            require(re.fullmatch(r"[0-9a-f]{64}", cid), "Missing isolated service")
            observed = run(["docker", "inspect", "--format",
                            "{{.Image}}|{{.HostConfig.Memory}}|{{.HostConfig.NanoCpus}}", cid])
            require(observed == f"{before[service]['image']}|{memory}|{nano}",
                    "Actual restore image/resource limits differ from approval")
        for command, args in (("serial_only_phase3_audit", ["--strict"]),
                              ("serial_only_phase0_audit", ["--include-continuity", "--strict-serial"])):
            run([*compose, "exec", "-T", "-e", "PGOPTIONS=-c default_transaction_read_only=on",
                 "web", "python", "manage.py", command, *args], env=restore_env,
                log=evidence / f"restored-{command}.json", timeout=180)
        return {"project": project, "restore_rto_seconds": int(result["RESTORE_RTO_SECONDS"])}
    finally:
        if attempted:
            try:
                run([*compose, "down", "-v"], env=restore_env, log=evidence / "cleanup-private.log", timeout=180)
                no_resources(project)
                cleaned = True
            except GateError:
                print(f"PHASE3_RECOVERY_MANUAL_CLEANUP_WORKDIR={work}", flush=True)
                raise
        if not attempted or cleaned:
            shutil.rmtree(work)


def execute(app_dir, expected_sha, source_sha, confirmation):
    require(os.geteuid() == 0, "Root execution required")
    require(confirmation == CONFIRMATION, "Exact recovery-only confirmation required")
    require(expected_sha == ROLLBACK_SHA and re.fullmatch(r"[0-9a-f]{40}", source_sha),
            "Approved 3A image and exact source SHA required")
    app = Path(app_dir) if app_dir else Path.home() / "Financee_Multitenant_Production"
    require(app.is_absolute() and (app / "deploy/.env").is_file(), "Production application directory unavailable")
    require(PASSPHRASE.is_file() and PASSPHRASE.stat().st_size > 0, "Backup passphrase unavailable")
    for name, expected in HOST_HASHES.items():
        require(sha256(app / name) == expected, "Host helper/source differs; stop for review")
    os.chdir(app / "deploy")
    compose = ["docker", "compose", "--env-file", str(app / "deploy/.env"), "-f", "docker-compose.yml"]
    if Path("docker-compose.tls.yml").is_file():
        compose += ["-f", "docker-compose.tls.yml"]
    before = snapshot(compose, expected_sha)
    capacity()
    evidence = BACKUP_ROOT / "phase3-recovery-evidence" / (dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex)
    evidence.mkdir(mode=0o700, parents=True)
    evidence.parent.chmod(0o700)
    print(f"PHASE3_RECOVERY_EVIDENCE_DIR={evidence}", flush=True)
    print(f"PHASE3_RECOVERY_SOURCE_SHA={source_sha}", flush=True)
    print(f"PHASE3_RECOVERY_DEPLOYED_SHA={expected_sha}", flush=True)
    try:
        db_bytes = production_audits(before, evidence, "before")
        release, bundle = fresh_backup(evidence)
        # Account for encrypted copy, decrypted archive, restored DB and logs.
        required_free = max(1024**3, db_bytes * 4 + bundle.stat().st_size * 2)
        for storage in (run(["docker", "info", "--format", "{{.DockerRootDir}}"]), tempfile.gettempdir()):
            require(shutil.disk_usage(storage).free >= required_free, "Insufficient disk for isolated restore")
        restored = restore(before, bundle, evidence)
    finally:
        require(snapshot(compose, expected_sha) == before, "Production container/image changed during recovery")
        production_audits(before, evidence, "after")
        run(["curl", "-fsS", "--max-time", "30", "--retry", "3", "--retry-delay", "2",
             "--retry-all-errors", "-o", "/dev/null", "http://localhost/authentication/login/"],
            log=evidence / "production-http.log", timeout=150)
    report = {"source_sha": source_sha, "deployed_sha": expected_sha, "backup_release": release,
              **restored, "production_container_images_unchanged": True, "result": "PASS",
              "authorizes_cleanup": False, "scope": "encrypted-database-only-recovery"}
    (evidence / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, sort_keys=True), flush=True)
    print("PHASE3_RECOVERY_RESULT=PASS\nPHASE3_CLEANUP_AUTHORIZED=no", flush=True)


def main():
    os.umask(0o077)
    def interrupted(signum, frame):
        raise GateError("Recovery interrupted; cleanup and production recheck required")
    for signum in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
        signal.signal(signum, interrupted)
    require(len(sys.argv) == 5, "Expected app directory, deployed SHA, source SHA and confirmation")
    with LOCK_FILE.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise GateError("Another recovery operation holds the host lock") from exc
        execute(*sys.argv[1:])


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Never echo subprocess payloads, credentials or customer-bearing logs.
        print("PHASE3_RECOVERY_RESULT=FAIL", flush=True)
        print(str(exc) if isinstance(exc, GateError) else "Unexpected failure; inspect protected host evidence", file=sys.stderr)
        raise SystemExit(1)
