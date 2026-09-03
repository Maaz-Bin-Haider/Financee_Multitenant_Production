"""Narrow static retirement must never clear serial assets or follow links."""

from pathlib import Path
import tempfile
import unittest

from deploy.retire_quantity_static import RETIRED_ASSETS, retire_assets


class StaticRetirementTests(unittest.TestCase):
    def test_only_exact_retired_assets_and_hashes_are_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            retired = []
            for extension, names in RETIRED_ASSETS.items():
                directory = root / extension
                directory.mkdir()
                for name in names:
                    for hash_part in ("", ".012345abcdef"):
                        for compression in ("", ".gz", ".br"):
                            path = directory / f"{name}{hash_part}.{extension}{compression}"
                            path.write_text("retired", encoding="utf-8")
                            retired.append(path)
            preserved = (
                "js/sale.js", "js/sale.012345abcdef.js", "staticfiles.json",
                "js/quantity_sales_custom.js", "js/quantity_sales.unknown.js",
                "css/quantity_reports_notes.css", "js/quantity_sales.js.backup",
            )
            for relative in preserved:
                (root / relative).write_text("preserved", encoding="utf-8")
            self.assertEqual(retire_assets(root), len(retired))
            self.assertTrue(all(not path.exists() for path in retired))
            self.assertTrue(all((root / path).read_text() == "preserved" for path in preserved))
            self.assertEqual(retire_assets(root), 0)

    def test_symlink_directory_fails_before_removing_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "css").mkdir()
            asset = root / "css/quantity_reports.css"
            asset.write_text("preserve", encoding="utf-8")
            (root / "js").symlink_to(root / "css", target_is_directory=True)
            with self.assertRaises(RuntimeError):
                retire_assets(root)
            self.assertEqual(asset.read_text(), "preserve")

    def test_symlink_file_and_root_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "js").mkdir()
            target = root / "untouched"
            target.write_text("preserve", encoding="utf-8")
            (root / "js/quantity_sales.js").symlink_to(target)
            with self.assertRaises(RuntimeError):
                retire_assets(root)
            link = root / "linked_root"
            link.symlink_to(root, target_is_directory=True)
            with self.assertRaises(RuntimeError):
                retire_assets(link)
            self.assertEqual(target.read_text(), "preserve")


if __name__ == "__main__":
    unittest.main()
