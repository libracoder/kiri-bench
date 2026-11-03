import argparse
import json
import tempfile
import unittest
from pathlib import Path

import kiri_bench


class StatisticsTests(unittest.TestCase):
    def test_statistics(self):
        result = kiri_bench.stats([4.0, 1.0, 2.0, 3.0])
        self.assertEqual(result["count"], 4)
        self.assertEqual(result["median"], 2.5)
        self.assertEqual(result["mean"], 2.5)
        self.assertEqual(result["min"], 1.0)
        self.assertEqual(result["max"], 4.0)
        self.assertEqual(result["p95"], 4.0)

    def test_empty_statistics(self):
        self.assertEqual(kiri_bench.stats([]), {})


class ContextTests(unittest.TestCase):
    def args(self, directory):
        return argparse.Namespace(
            engine="kiri", command=None, out=str(directory), label="test",
            socket=None,
        )

    def test_measurement_and_summary_are_json_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            ctx = kiri_bench.RunContext(self.args(directory))
            ctx.measure("test", lambda _: object(), 2)
            summary = ctx.summary()
            json.dumps(summary)
            self.assertEqual(summary["measurements"][0]["status"], "pass")
            self.assertEqual(summary["measurements"][0]["runs"], 2)
            self.assertNotIn("func", summary["options"])

    def test_partial_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            ctx = kiri_bench.RunContext(self.args(directory))
            calls = iter([None, RuntimeError("no")])
            def sample(_):
                value = next(calls)
                if value:
                    raise value
            ctx.measure("test", sample, 2)
            self.assertEqual(ctx.measurements[0]["status"], "partial")
            self.assertEqual(ctx.measurements[0]["failures"], 1)

    def test_cleanup_only_manifest_resources(self):
        with tempfile.TemporaryDirectory() as directory:
            ctx = kiri_bench.RunContext(self.args(directory))
            calls = []
            ctx.call = lambda args, **kwargs: calls.append(args)
            ctx.add_resource("container", "own-container")
            ctx.add_resource("volume", "own-volume")
            ctx.add_resource("network", "own-network")
            ctx.add_resource("image", "own-image")
            ctx.cleanup()
            self.assertEqual(calls, [
                ["rmi", "-f", "own-image"],
                ["network", "rm", "own-network"],
                ["volume", "rm", "own-volume"],
                ["rm", "-f", "own-container"],
            ])
            manifest = json.loads((Path(directory) / "manifest.json").read_text())
            self.assertEqual(manifest["resources"], [])


class ReportTests(unittest.TestCase):
    def test_report_contains_measurements_and_skips(self):
        with tempfile.TemporaryDirectory() as directory:
            summary = {
                "engine": "kiri", "command": ["kiri"], "started": "now",
                "environment": {"system": "Linux", "release": "test", "machine": "x86_64", "host_label": "test"},
                "measurements": [{"name": "run", "status": "pass", "runs": 1, "seconds": {"median": 0.1}, "samples": []}],
                "skipped": [{"name": "api", "reason": "no socket"}],
            }
            kiri_bench.write_report(summary, directory)
            report = (Path(directory) / "report.md").read_text()
            self.assertIn("| run | pass | 1 |", report)
            self.assertIn("api: no socket", report)


if __name__ == "__main__":
    unittest.main()
