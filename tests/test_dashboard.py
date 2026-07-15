"""Tests for dashboard.py — build_context contract and the stub renderer."""

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import _bootstrap  # noqa: F401  (sys.path shim, must run before resilience_radar imports)

from resilience_radar import dashboard, graph, kpi, mitigate, radar, simulate


class TestBuildContext(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.network = graph.load_network("data/network.json")
        cls.risks = radar.build_risk_register(radar.load_events("data/events.json"), cls.network)
        cls.sim_results = simulate.run_all_presets(cls.network)
        cls.mitigations = {
            sid: mitigate.rank_mitigations(cls.network, simulate.PRESET_SCENARIOS[sid], result)
            for sid, result in cls.sim_results.items()
        }
        cls.kpis = kpi.compute_kpis(cls.network, cls.risks, cls.sim_results)
        cls.context = dashboard.build_context(
            cls.network, cls.risks, cls.kpis, cls.sim_results, cls.mitigations,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    def test_context_has_expected_top_level_keys(self) -> None:
        expected = {"generated_at", "company", "kpis", "network", "risk_register", "scenarios", "mitigations"}
        self.assertEqual(set(self.context), expected)

    def test_context_is_json_serializable(self) -> None:
        # Round-trips cleanly with no dataclass/Enum/date leakage.
        encoded = json.dumps(self.context)
        decoded = json.loads(encoded)
        self.assertEqual(decoded["company"], "Meridian Goods")

    def test_network_context_has_coords_and_criticality(self) -> None:
        nodes = self.context["network"]["nodes"]
        self.assertGreater(len(nodes), 0)
        for node in nodes:
            self.assertIn("x", node)
            self.assertIn("y", node)
            self.assertIn("criticality", node)

    def test_all_three_scenarios_present(self) -> None:
        self.assertEqual(set(self.context["scenarios"]), {"supplier-failure", "port-closure", "demand-spike"})

    def test_scenario_has_baseline_and_scenario_weeks(self) -> None:
        supplier_failure = self.context["scenarios"]["supplier-failure"]
        self.assertEqual(len(supplier_failure["baseline_weeks"]), simulate.HORIZON_WEEKS)
        self.assertEqual(len(supplier_failure["scenario_weeks"]), simulate.HORIZON_WEEKS)

    def test_mitigations_present_per_scenario(self) -> None:
        self.assertEqual(set(self.context["mitigations"]), {"supplier-failure", "port-closure", "demand-spike"})
        self.assertEqual(len(self.context["mitigations"]["port-closure"]), len(mitigate.PLAYBOOK))


class TestRenderDashboard(unittest.TestCase):
    def test_writes_html_file_embedding_context_json(self) -> None:
        context = {"company": "Test Co", "kpis": {"a": 1}, "nested": {"b": [1, 2, 3]}}
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "sub" / "dashboard.html"
            dashboard.render_dashboard(context, out_path)

            self.assertTrue(out_path.exists())
            html_text = out_path.read_text()
            self.assertIn("<html", html_text)
            self.assertIn("Test Co", html_text)
            self.assertIn('"b": [', html_text)

    def test_creates_parent_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "a" / "b" / "c" / "dashboard.html"
            dashboard.render_dashboard({"x": 1}, out_path)
            self.assertTrue(out_path.exists())

    def test_escapes_script_close_in_embedded_json(self) -> None:
        # An embedded string must never be able to close the <script> early.
        context = {"company": "</script><b>x</b>"}
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "dashboard.html"
            dashboard.render_dashboard(context, out_path)
            html_text = out_path.read_text(encoding="utf-8")
            self.assertNotIn("</script><b>x</b>", html_text)
            self.assertIn("<\\/script>", html_text)


class TestRenderRealDashboard(unittest.TestCase):
    """Structural assertions against the real control-tower render."""

    @classmethod
    def setUpClass(cls) -> None:
        network = graph.load_network("data/network.json")
        risks = radar.build_risk_register(radar.load_events("data/events.json"), network)
        sim_results = simulate.run_all_presets(network)
        mitigations = {
            sid: mitigate.rank_mitigations(network, simulate.PRESET_SCENARIOS[sid], result)
            for sid, result in sim_results.items()
        }
        kpis = kpi.compute_kpis(network, risks, sim_results)
        context = dashboard.build_context(
            network, risks, kpis, sim_results, mitigations,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
        cls._tmp = tempfile.TemporaryDirectory()
        out_path = Path(cls._tmp.name) / "dashboard.html"
        dashboard.render_dashboard(context, out_path)
        cls.html = out_path.read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_is_self_contained(self) -> None:
        # Zero external requests: no http(s) asset references, no CDN.
        self.assertNotIn("http://", self.html)
        self.assertNotIn("https://", self.html)
        self.assertNotIn("src=", self.html)  # no external scripts/images

    def test_has_six_kpi_tiles(self) -> None:
        # KPI tiles are client-rendered from a fixed 6-key order array.
        self.assertIn("#kpis", self.html)
        for key in ("service_level", "revenue_at_risk", "rsi",
                    "open_risks", "min_tts", "single_source_nodes"):
            self.assertIn(key, self.html)

    def test_has_svg_network_map(self) -> None:
        self.assertIn('<svg id="netmap"', self.html)
        self.assertIn("Shenzhen Component Works", self.html)  # a node embedded in DATA

    def test_has_scenario_tabs_and_lab(self) -> None:
        self.assertIn('id="scentabs"', self.html)
        self.assertIn('id="scenchart"', self.html)
        self.assertIn("supplier-failure", self.html)

    def test_embedded_data_parses_as_json(self) -> None:
        import re
        m = re.search(r"const DATA = (\{.*?\});\n", self.html, re.S)
        self.assertIsNotNone(m)
        decoded = json.loads(m.group(1).replace("<\\/", "</"))
        self.assertEqual(decoded["company"], "Meridian Goods")
        self.assertEqual(len(decoded["kpis"]) >= 6, True)

    def test_dual_theme_tokens_present(self) -> None:
        self.assertIn('data-theme="light"', self.html)
        self.assertIn("prefers-color-scheme", self.html)
        self.assertIn("localStorage", self.html)


if __name__ == "__main__":
    unittest.main()
