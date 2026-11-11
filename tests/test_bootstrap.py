import json
from pathlib import Path
import tempfile
import unittest
from unified.bootstrap import bootstrap


class BootstrapTests(unittest.TestCase):
    def test_all_listed_versions_are_retained_without_promoting_legacy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            doc = {"source": "admrul", "stable_id": "X", "serial": "123",
                   "title": "어떤 기준", "published_at": "2026-01-01"}
            files = {}
            contents = {
                "v2": {"events": {"a": doc}, "snapshots": {}, "pending": []},
                "v4": {"catalog": {"a": doc}, "verified_snapshots": {}},
                "next": {"documents": {"a": doc}, "versions": {}},
            }
            for name, data in contents.items():
                target = root / (name+".json")
                target.write_text(json.dumps(data), "utf8")
                files[name] = target
            result = bootstrap(files, root / "data")
            self.assertEqual(result["unique_official_versions"], 1)
            self.assertEqual(result["shards"], 1)
            self.assertEqual(result["changed_shards"], 1)
            self.assertEqual(bootstrap(files, root / "data")["changed_shards"], 0)
