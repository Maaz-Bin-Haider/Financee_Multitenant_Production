#!/usr/bin/env python3
"""Select expired Financee DB backup releases without touching other tags."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone


TAG_RE = re.compile(r"^db-backup-(\d{8}T\d{6}Z)$")


def parse_managed(releases):
    managed = []
    for release in releases:
        tag = release.get("tag_name", "")
        match = TAG_RE.fullmatch(tag)
        if not match or release.get("draft"):
            continue
        try:
            created = datetime.strptime(
                match.group(1), "%Y%m%dT%H%M%SZ"
            ).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        managed.append((created, tag))
    return sorted(managed, reverse=True)


def expired_tags(releases, keep_daily=30, keep_monthly=12, protect=()):
    managed = parse_managed(releases)
    protected = set(protect)
    retained = {tag for _, tag in managed[:keep_daily]}

    # Keep the first (oldest) successful managed release in each of the newest
    # N represented UTC calendar months.
    by_month = {}
    for created, tag in sorted(managed):
        by_month.setdefault((created.year, created.month), tag)
    newest_months = sorted(by_month, reverse=True)[:keep_monthly]
    retained.update(by_month[month] for month in newest_months)
    retained.update(protected)
    return [tag for _, tag in managed if tag not in retained]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep-daily", type=int, default=30)
    parser.add_argument("--keep-monthly", type=int, default=12)
    parser.add_argument("--protect", action="append", default=[])
    args = parser.parse_args()
    if args.keep_daily < 1 or args.keep_monthly < 0:
        parser.error("retention values are invalid")
    releases = json.load(sys.stdin)
    if not isinstance(releases, list):
        raise SystemExit("GitHub releases payload must be a list")
    for tag in expired_tags(
        releases, args.keep_daily, args.keep_monthly, args.protect
    ):
        print(tag)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
