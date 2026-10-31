import json
import unittest

from agent_visuals import estimate_transfer, flow_excalidraw, flow_html, timeline_html, timing_stages
from foundry_agent import AgentTimings


class AgentVisualTests(unittest.TestCase):
    def test_transfer_counts_request_and_response_once_and_both_peering_endpoints(self):
        west = estimate_transfer("westus3", 1e9, 1e9)
        self.assertAlmostEqual(west["sea_peering_usd"], 0.18)
        self.assertAlmostEqual(west["westus3_peering_usd"], 0.07)
        self.assertAlmostEqual(west["private_link_usd"], 0.02)
        self.assertAlmostEqual(west["total_usd"], 0.27)
        sea = estimate_transfer("sea", 1e9, 1e9)
        self.assertEqual(sea["sea_peering_usd"], 0)
        self.assertEqual(sea["westus3_peering_usd"], 0)
        self.assertAlmostEqual(sea["total_usd"], 0.02)
        self.assertEqual(estimate_transfer("westus3", 1000, 1000, 0)["total_usd"], 0)

    def test_cost_rejects_invalid_and_out_of_tier_volume(self):
        for request, response, calls in ((-1, 0, 1), (float("nan"), 0, 1), (0, float("inf"), 1), (0, 0, -1), (0, 0, 0.5), (1e16, 0, 1)):
            with self.subTest(request=request), self.assertRaises(ValueError):
                estimate_transfer("sea", request, response, calls)
        with self.assertRaises(ValueError):
            estimate_transfer("eastus", 1, 1)

    def test_additive_timeline_and_overlapping_reference(self):
        stages = timing_stages(AgentTimings(3000, 500, 2000), 2000, 5500)
        self.assertEqual([duration for _, duration in stages], [2000, 500, 2500, 500])
        self.assertEqual(sum(duration for _, duration in stages), 5500)
        html = timeline_html(AgentTimings(3000, 500, 2000), 2000, 5500)
        self.assertIn("NOT added", html)
        self.assertIn("5.500 s", html)
        self.assertIn("data-theme", html)
        self.assertIn("var(--cp-bg)", html)

    def test_unknown_ttft_remains_unknown_and_invalid_clocks_are_rejected(self):
        stages = timing_stages(AgentTimings(3000, None, None), 2000, 5000)
        self.assertEqual(len(stages), 3)
        self.assertIn("unavailable", stages[1][0])
        for timing, setup, total in (
            (AgentTimings(3000, 3100, None), 100, 3200),
            (AgentTimings(3000, 500, None), 1000, 100),
            (AgentTimings(float("nan"), 500, None), 1000, 5000),
        ):
            with self.subTest(timing=timing), self.assertRaises(ValueError):
                timing_stages(timing, setup, total)

    def test_diagram_distinguishes_endpoint_path_from_unknown_inference_location(self):
        row = {
            "agent_region": "West US 3", "responses_stream_ms": 3000,
            "responses_first_token_ms": 500, "app_response_ms": 5500,
        }
        html = flow_html("global", [row], {})
        self.assertIn("Direct global VNet peering", html)
        self.assertIn("Same VNet / Private Link", html)
        self.assertIn("Serving region not exposed", html)
        self.assertIn("height=\"200\"", html)
        self.assertIn("outside the VNet boundary", html)
        self.assertIn("API 3.00 s | first text 0.50 s", html)
        self.assertIn("API time: not measured", html)
        self.assertIn("No hub transit", html)
        self.assertIn("not timed", html)
        self.assertNotIn("0.00 s", html)

    def test_blocked_state_is_escaped_and_editable_source_has_text_dimensions(self):
        html = flow_html("standard", [], {}, '<script>alert("unsafe")</script>')
        self.assertIn("UNAVAILABLE", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn('<script>alert("unsafe")', html)
        source = json.loads(flow_excalidraw("standard", [], "Unavailable"))
        self.assertEqual(source["type"], "excalidraw")
        texts = [element for element in source["elements"] if element["type"] == "text"]
        self.assertTrue(all(text["width"] > 0 and text["height"] > 0 for text in texts))
        self.assertTrue(all(text["strokeColor"] == "#000000" for text in texts))
        with self.assertRaises(ValueError):
            flow_html("regions", [], {})


if __name__ == "__main__":
    unittest.main()
