#!/usr/bin/env python3
"""Static release-contract checks for Phase 27."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
workflow = (ROOT / ".github/workflows/ci.yml").read_text()
deploy = (ROOT / "deploy/deploy_pull.sh").read_text()
command = (ROOT / "tenancy/management/commands/release_preflight.py").read_text()

checks = {
    "serial CI stage": "serial-gate:" in workflow,
    "quantity CI stage": "quantity-gate:" in workflow,
    "isolation CI stage": "isolation-gate:" in workflow,
    "ARM64 execution stage": "arm64-smoke:" in workflow,
    "publish depends on mandatory gates":
        "needs: [checks, serial-gate, quantity-gate, isolation-gate, arm64-smoke, full-regression]"
        in workflow,
    "production approval retained": "environment: production" in workflow,
    "SHA-pinned deployment retained": "github.sha" in workflow,
    "preflight lists family and version": "release_preflight" in deploy,
    "post-deploy family probes": deploy.count("release_preflight") >= 2,
    "failed health rollback retained":
        "Rolling web back to previous image" in deploy and 'PREV_IMAGE' in deploy,
    "preflight emits fingerprint": '"fingerprint"' in command,
}

for name, ok in checks.items():
    print(f"{'PASS' if ok else 'FAIL'}: {name}")
print(f"{sum(checks.values())}/{len(checks)} Phase 27 release gates passed")
raise SystemExit(0 if all(checks.values()) else 1)
