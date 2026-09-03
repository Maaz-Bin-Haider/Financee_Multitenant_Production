#!/usr/bin/env python3
"""Synthetic local integration of the exact-image DB-only backup/restore gate.

Never calls the production orchestrator or backup service. Requires Docker and
the three explicitly named local images; creates/removes only fresh projects.
"""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import uuid


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("phase3_recovery", ROOT / "deploy/phase3_recovery_remote.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def main():
    os.umask(0o077)
    os.chdir(ROOT / "deploy")
    project = "dbbackup_rehearsal_phase3source_" + uuid.uuid4().hex
    work = Path(tempfile.mkdtemp(prefix="phase3-recovery-synthetic-"))
    print(f"SYNTHETIC_EVIDENCE_DIR={work}", flush=True)
    env_file = work / "source.env"
    override = work / "source.json"
    passphrase = work / "synthetic-passphrase"
    passphrase.write_text(uuid.uuid4().hex + uuid.uuid4().hex)
    env_file.write_text("\n".join([
        "SECRET_KEY=" + uuid.uuid4().hex + uuid.uuid4().hex, "DEBUG=False",
        "ALLOWED_HOSTS=localhost,127.0.0.1", "CSRF_TRUSTED_ORIGINS=http://localhost",
        "DB_NAME=financee_phase3_synthetic", "DB_USER=financee_phase3_synthetic",
        "DB_PASSWORD=" + uuid.uuid4().hex, "DB_HOST=db", "DB_PORT=5432", "",
    ]))
    before = {}
    for service, tag in (("web", f"ghcr.io/maaz-bin-haider/financee-web:{gate.ROLLBACK_SHA}"),
                         ("db", "postgres:16"), ("redis", "redis:7-alpine")):
        image = gate.run(["docker", "image", "inspect", "--format", "{{.Id}}", tag])
        before[service] = {"image": image}
    override.write_text(json.dumps(gate.override_config(before)))
    env = {"WEB_ENV_FILE": str(env_file), "WEB_IMAGE": before["web"]["image"]}
    compose = ["docker", "compose", "--project-name", project, "--env-file", str(env_file),
               "-f", "docker-compose.yml", "-f", str(override)]
    gate.no_resources(project)
    attempted = False
    cleaned = False
    try:
        config = json.loads(gate.run([*compose, "config", "--format", "json"], env=env))
        gate.validate_config(config, before, project)
        attempted = True
        gate.run([*compose, "up", "-d", "--wait", "--wait-timeout", "180", "db", "redis", "web"],
                 env=env, timeout=240, log=work / "synthetic-startup.log")
        print("SYNTHETIC_SOURCE_STARTUP=PASS", flush=True)
        backup = gate.run(["bash", "backup_database_encrypted.sh"], timeout=240,
                          log=work / "synthetic-backup.log", env={**env,
                              "BACKUP_DEST": str(work), "BACKUP_PASSPHRASE_FILE": str(passphrase),
                              "BACKUP_COMPOSE_PROJECT": project, "BACKUP_ENV_FILE": str(env_file),
                              "BACKUP_COMPOSE_OVERRIDE": str(override),
                              "DB_USER": "financee_phase3_synthetic", "DB_NAME": "financee_phase3_synthetic"})
        bundle = Path(gate.key_values(backup)["BACKUP_PATH"])
        print("SYNTHETIC_ENCRYPTED_BACKUP=PASS", flush=True)
        gate.PASSPHRASE = passphrase
        report = gate.restore(before, bundle, work)
        print(json.dumps({"source_sha": gate.ROLLBACK_SHA, "images": before,
                          "synthetic": True, **report, "result": "PASS"}, sort_keys=True), flush=True)
    finally:
        if attempted:
            gate.run([*compose, "down", "-v"], env=env, log=work / "synthetic-cleanup.log", timeout=180)
            gate.no_resources(project)
            cleaned = True
        if not attempted or cleaned:
            env_file.unlink(missing_ok=True)
            passphrase.unlink(missing_ok=True)
        print(f"SYNTHETIC_SOURCE_CLEANED={not attempted or cleaned}", flush=True)


if __name__ == "__main__":
    main()
