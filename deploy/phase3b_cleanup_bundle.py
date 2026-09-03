#!/usr/bin/env python3
"""Build a self-contained reviewed-source stdin transport; never execute it here."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
FILES = {
    "recovery": "deploy/phase3_recovery_remote.py",
    "executor": "deploy/phase3b_cleanup_remote.py",
    "core": "tenancy/management/commands/serial_only_phase3_cleanup.py",
}


def build(source_sha):
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise ValueError("Exact source commit SHA required")
    payload = {name: (ROOT / path).read_text() for name, path in FILES.items()}
    envelope = {"source_sha": source_sha, "sources": payload,
                "hashes": {name: hashlib.sha256(text.encode()).hexdigest() for name, text in payload.items()}}
    encoded = base64.b64encode(json.dumps(envelope, sort_keys=True).encode()).decode()
    return f'''import base64,hashlib,json,sys,types
data=json.loads(base64.b64decode({encoded!r}))
try:
    for name,source in data["sources"].items():
        if hashlib.sha256(source.encode()).hexdigest()!=data["hashes"][name]:
            raise RuntimeError("Bundle checksum mismatch")
    recovery=types.ModuleType("phase3_recovery_remote")
    sys.modules[recovery.__name__]=recovery
    exec(compile(data["sources"]["recovery"],"reviewed_recovery","exec"),recovery.__dict__)
    executor=types.ModuleType("phase3b_cleanup_remote")
    exec(compile(data["sources"]["executor"],"reviewed_executor","exec"),executor.__dict__)
    if data["hashes"]["core"]!=executor.CORE_SHA256:
        raise RuntimeError("Unreviewed core")
    if sys.argv[1:]==["--validate-bundle"]:
        print(json.dumps({{"source_sha":data["source_sha"],"hashes":data["hashes"],"mode":"validation-only"}},sort_keys=True))
    else:
        if len(sys.argv)!=10 or sys.argv[3]!=data["source_sha"]:
            raise RuntimeError("Invocation/source SHA mismatch")
        print("PHASE3B_BUNDLE_SOURCE_SHA="+data["source_sha"],flush=True)
        print("PHASE3B_BUNDLE_HASHES="+json.dumps(data["hashes"],sort_keys=True),flush=True)
        executor.main(data["sources"]["core"])
except Exception:
    print("PHASE3B_RESULT=FAIL; inspect protected host evidence; never retry a write automatically",file=sys.stderr)
    raise SystemExit(1)
'''


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    # Exclusive creation prevents overwriting an unrelated path or symlink.
    with args.output.open("x") as stream:
        stream.write(build(args.source_sha))
