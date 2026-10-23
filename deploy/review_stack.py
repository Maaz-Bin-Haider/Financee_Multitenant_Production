#!/usr/bin/env python3
"""Manage only a locally owned, isolated Financee review stack.

python3 deploy/review_stack.py start --project financee_review_darkmode
python3 deploy/review_stack.py status --project financee_review_darkmode
python3 deploy/review_stack.py stop --project financee_review_darkmode
python3 deploy/review_stack.py remove --project financee_review_regression --confirm financee_review_regression

Remove deletes this project's disposable data only, after exact confirmation.
State and generated local credentials live outside the repository/build context.
"""
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import socket
import subprocess
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "deploy/docker-compose.review.yml"
PROJECT_RE = re.compile(r"financee_review_(darkmode|email|spotlight|activity|regression)(_[a-z0-9]{1,16})?\Z")


def validate_project(project):
    if not PROJECT_RE.fullmatch(project):
        raise ValueError("Only named financee_review_* feature/regression projects are allowed.")
    return project


def validate_port(port):
    if not 1024 <= port <= 65535:
        raise ValueError("Choose an unprivileged localhost port (1024-65535).")
    return port


def state_directory(project):
    validate_project(project)
    return Path(tempfile.gettempdir()) / f"financee-review-{os.getuid()}" / project


def write_private(path, content):
    # Refuse links rather than following a pre-existing path out of our state.
    if path.is_symlink():
        raise ValueError(f"Refusing symlink: {path}")
    path.write_text(content, encoding="utf-8")
    path.chmod(0o600)


def local_docker():
    host = os.environ.get("DOCKER_HOST", "")
    if host and not host.startswith("unix://"):
        raise ValueError("Review stacks require a local Unix Docker socket.")
    result = subprocess.check_output(
        ["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"], text=True
    ).strip()
    if not result.startswith("unix://"):
        raise ValueError("Refusing a non-local Docker context.")


def command(config, *args):
    return ["docker", "compose", "--project-name", config["project"],
            "--env-file", str(state_directory(config["project"]) / "review.env"),
            "-f", str(COMPOSE), *args]


def run(config, *args):
    # An inherited shell's production DB/Compose settings must not win.
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(("COMPOSE_", "DB_", "REVIEW_", "WEB_"))}
    env.update(config["env"])
    env["REVIEW_ENV_FILE"] = str(state_directory(config["project"]) / "review.env")
    subprocess.run(command(config, *args), env=env, cwd=ROOT, check=True)


def read_config(project):
    path = state_directory(project) / "state.json"
    if path.is_symlink():
        raise ValueError("Refusing linked review state.")
    config = json.loads(path.read_text())
    if config["project"] != project or config["root"] != str(ROOT):
        raise ValueError("Review state does not belong to this checkout/project.")
    return config


def initialize(project, port):
    directory = state_directory(project)
    for path in (directory.parent, directory):
        if path.is_symlink():
            raise ValueError("Refusing linked review state directory.")
        path.mkdir(mode=0o700, exist_ok=True)
        path.chmod(0o700)
    if (directory / "state.json").exists():
        return read_config(project)
    # Do not attach to resources that predate this helper's ownership record.
    existing = subprocess.check_output(
        ["docker", "ps", "-aq", "--filter", f"label=com.docker.compose.project={project}"], text=True
    ).strip()
    volumes = subprocess.check_output(
        ["docker", "volume", "ls", "-q", "--filter", f"label=com.docker.compose.project={project}"], text=True
    ).strip()
    if existing or volumes:
        raise ValueError("Project resources already exist without owned review state.")
    validate_port(port)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", port))
    env = {
        "SECRET_KEY": secrets.token_urlsafe(48), "DEBUG": "False",
        "ALLOWED_HOSTS": "localhost,127.0.0.1", "SECURE_COOKIES": "False",
        "CSRF_TRUSTED_ORIGINS": f"http://127.0.0.1:{port},http://localhost:{port}",
        "DB_NAME": "financee_review", "DB_USER": "review", "DB_HOST": "db", "DB_PORT": "5432",
        "DB_PASSWORD": secrets.token_urlsafe(24), "REVIEW_PORT": str(port),
        "FINANCEE_REVIEW_PROJECT": project, "REVIEW_LOGIN_PASSWORD": secrets.token_urlsafe(18),
        "REVIEW_DB_PASSWORD": "", "REVIEW_IMAGE": "pending",
    }
    env["REVIEW_DB_PASSWORD"] = env["DB_PASSWORD"]
    config = {"project": project, "root": str(ROOT), "env": env}
    save(config)
    return config


def save(config):
    directory = state_directory(config["project"])
    write_private(directory / "review.env", "".join(f"{key}={value}\n" for key, value in config["env"].items()))
    write_private(directory / "state.json", json.dumps(config, indent=2) + "\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["start", "status", "stop", "remove", "test"])
    parser.add_argument("--project", required=True)
    parser.add_argument("--port", type=int, default=8180)
    parser.add_argument("--confirm")
    args = parser.parse_args(argv)
    validate_project(args.project)
    if args.action == "remove" and args.confirm != args.project:
        raise ValueError("Removal requires --confirm with the exact review project name.")
    if args.action == "test" and not args.project.startswith("financee_review_regression"):
        raise ValueError("Mutating suites run only in a separate regression project.")
    local_docker()
    if args.action == "start":
        dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True)
        if dirty.strip():
            raise ValueError("Commit the source before building a review image.")
        config = initialize(args.project, args.port)
        sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        config["commit"] = sha
        config["env"]["REVIEW_IMAGE"] = f"financee-review:{args.project}-{sha[:12]}"
        save(config)
        run(config, "build", "web")
        run(config, "up", "-d", "--wait", "--wait-timeout", "240")
        url = f"http://127.0.0.1:{config['env']['REVIEW_PORT']}"
        with urllib.request.urlopen(url + "/authentication/login/", timeout=15) as response:
            if response.status != 200:
                raise ValueError("The host's localhost review URL is not ready.")
        run(config, "exec", "-T", "web", "python", "tests/review_seed.py")
        write_private(state_directory(args.project) / "handoff.txt",
                      f"Commit: {sha}\nURL: http://127.0.0.1:{config['env']['REVIEW_PORT']}\n"
                      f"Password for all synthetic accounts: {config['env']['REVIEW_LOGIN_PASSWORD']}\n"
                      "Accounts: review_operator, alpha_manager, alpha_staff, alpha_reader, "
                      "beta_manager, beta_staff, suspended_user\n")
        print(f"Review ready. Local credentials: {state_directory(args.project) / 'handoff.txt'}")
    else:
        config = read_config(args.project)
        if args.action == "status":
            run(config, "ps")
        elif args.action == "stop":
            run(config, "stop")
        elif args.action == "remove":
            run(config, "down", "--volumes", "--remove-orphans")
        else:
            run(config, "exec", "-T", "-e", "PYTHONPATH=/app", "web", "python", "tests/suite/run_all.py")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit(str(exc))
