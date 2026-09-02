#!/usr/bin/env python3
"""Static fail-closed contracts for Phase 29 staging/security acceptance."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text()


settings = read("financee/settings.py")
middleware = read("tenancy/middleware.py")
security = read("financee/security.py")
utils = read("tenancy/utils.py")
attachments = read("attachments/views.py")
nginx = read("deploy/nginx/financee_common.conf")
company = read("tenancy/models.py")
admin = read("tenancy/admin.py")
workflow = read(".github/workflows/ci.yml")
preflight = read("tenancy/management/commands/release_preflight.py")
lock = read("requirements-lock.txt").splitlines()

checks = {
    "production secure cookies are fail-closed":
        "SESSION_COOKIE_SECURE = SECURE_COOKIES" in settings
        and "CSRF_COOKIE_SECURE = SECURE_COOKIES" in settings
        and "SESSION_COOKIE_HTTPONLY = True" in settings,
    "proxy HTTPS contract is configured":
        'SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")'
        in settings,
    "security headers are emitted":
        'X-Content-Type-Options "nosniff"' in nginx
        and 'X-Frame-Options "DENY"' in nginx
        and "Referrer-Policy" in nginx,
    "private media is denied by nginx":
        "location ^~ /media/private/" in nginx and "return 404;" in nginx,
    "attachment access is authenticated and permission checked":
        attachments.count("@login_required") >= 2
        and "user_can_view_document" in attachments
        and "attachments_feature_enabled" in attachments,
    "attachment traversal is contained":
        "root not in absolute.parents" in attachments
        and ".resolve()" in attachments,
    "schema identifiers are validated and quoted":
        "SCHEMA_NAME_RE" in utils
        and "validate_schema_name" in utils
        and '_quote_ident' in utils,
    "request search path always resets":
        "reset_search_path()" in middleware and "process_exception" in middleware,
    "tenant guards enforce membership and permissions":
        "tenant_required_response" in middleware
        and "has_required_permissions" in middleware,
    "error responses are scrubbed":
        "_scrub_error_response" in middleware
        and "An unexpected error occurred." in security,
    "rate limits include tenant identity":
        'return f"rl:{key_prefix}:{tenant}:{identity}:{bucket}"' in security,
    "company registry is serial only":
        "self.inventory_mode != INVENTORY_MODE_SERIAL" in company
        and "condition=models.Q(inventory_mode=INVENTORY_MODE_SERIAL)" in company,
    "company admin hides inventory family":
        '"inventory_mode",' in admin.split("exclude = (", 1)[1].split(")", 1)[0]
        and '"inventory_mode"' not in admin.split("list_display = (", 1)[1].split(")", 1)[0],
    "release verifies every tenant and safe report":
        "for company in companies" in preflight
        and "get_trial_balance_json" in preflight,
    "production deploy remains approval gated":
        "environment: production" in workflow,
    "recovery gate blocks publication":
        "recovery-gate" in workflow and "needs:" in workflow,
    "staging evidence and protected approval block publication":
        "staging-security-gate" in workflow
        and "environment: staging-release-approval" in workflow
        and "staging-release-approval]" in workflow,
    "runtime dependencies are exactly pinned":
        bool(lock) and all("==" in line for line in lock if line.strip()),
}

failed = [name for name, ok in checks.items() if not ok]
for name, ok in checks.items():
    print(f"{'PASS' if ok else 'FAIL'}: {name}")
print(f"{len(checks) - len(failed)}/{len(checks)} Phase 29 security contracts passed")
raise SystemExit(1 if failed else 0)
