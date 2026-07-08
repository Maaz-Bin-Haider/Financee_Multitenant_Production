"""
tenancy.context_processors
==========================
Expose the subscription warning banner and the per-company feature flags to
every tenant template.

``TenantSchemaMiddleware`` stamps ``request.subscription_state`` for
authenticated tenant users whose company is not blocked. Only the
``expiring`` (renewal due soon) and ``grace`` (expired, blocked soon)
states surface a banner; blocked states never reach a normal template
because the middleware short-circuits them to the suspension page.
"""
import json
from datetime import date, timedelta

from .features import features_map
from .models import SUBSCRIPTION_EXPIRING, SUBSCRIPTION_GRACE


def company_features(request):
    """
    ``features`` — nested {group: {enabled, subs: {sub: bool}}} for template
    conditions, and ``features_json`` — the same map serialized for
    ``window.FinanceeFeatures`` (base.html), which JS-built toolbars use to
    hide CSV/Excel export buttons. Off-tenant requests get all-enabled maps so
    shared pages render unchanged.
    """
    company = getattr(request, "tenant_company", None)
    feats = features_map(company)
    return {"features": feats, "features_json": json.dumps(feats)}


def subscription_notice(request):
    state = getattr(request, "subscription_state", None)
    if state not in (SUBSCRIPTION_EXPIRING, SUBSCRIPTION_GRACE):
        return {}

    company = getattr(request, "tenant_company", None)
    if company is None or company.paid_until is None:
        return {}

    today = date.today()
    if state == SUBSCRIPTION_GRACE:
        # Access stops the day AFTER grace_until.
        blocked_on = company.grace_until + timedelta(days=1)
        days_left = (company.grace_until - today).days + 1
    else:
        blocked_on = None
        days_left = (company.paid_until - today).days

    return {
        "subscription_notice": {
            "state": state,
            "paid_until": company.paid_until,
            "blocked_on": blocked_on,
            "days_left": max(days_left, 0),
        }
    }
