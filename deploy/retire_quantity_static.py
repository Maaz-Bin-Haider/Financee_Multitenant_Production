"""Remove only retired generated assets from the persistent static volume.

Old images repopulate their own baked assets during rollback. Never clear the
whole volume: serial pages already open in browsers may still use older hashes.
"""

from pathlib import Path
import re


RETIRED_ASSETS = {
    "css": ("quantity_reports", "quantity_workflow"),
    "js": (
        "quantity_counts", "quantity_opening_stock", "quantity_purchase_returns",
        "quantity_purchases", "quantity_reports", "quantity_sale_returns",
        "quantity_sales", "quantity_transfers", "quantity_warehouses",
        "quantity_workflow",
    ),
}


def retire_assets(root):
    root = Path(root)
    if root.is_symlink():
        raise RuntimeError("Refusing a symlink static root.")
    targets = []
    for extension, names in RETIRED_ASSETS.items():
        directory = root / extension
        if directory.is_symlink():
            raise RuntimeError("Refusing a symlink static subdirectory.")
        if not directory.exists():
            continue
        pattern = re.compile(
            rf"(?:{'|'.join(re.escape(name) for name in names)})"
            rf"(?:\.[0-9a-f]{{12}})?\.{extension}(?:\.(?:gz|br))?"
        )
        for candidate in directory.iterdir():
            if not pattern.fullmatch(candidate.name):
                continue
            if candidate.is_symlink() or not candidate.is_file():
                raise RuntimeError("Refusing a non-regular retired static asset.")
            targets.append(candidate)
    for target in targets:
        target.unlink()
    return len(targets)


if __name__ == "__main__":
    removed = retire_assets("/app/staticfiles")
    print(f"[entrypoint] retired generated static assets removed: {removed}")
