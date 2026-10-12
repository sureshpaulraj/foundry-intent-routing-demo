import unittest
from unittest.mock import patch

import app as demo


class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.client = demo.app.test_client()

    def test_invalid_query(self):
        response = self.client.post("/api/route", json={"query": ""})
        self.assertEqual(response.status_code, 400)

    def test_non_llm_exact_answer_never_generates(self):
        with patch.object(demo, "classify", return_value=("exact_lookup", 0.91)), patch.object(
            demo, "generate_answer"
        ) as generate:
            response = self.client.post("/api/route", json={"query": "What is the status of case DEMO-104?"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["route"], "non_llm")
        self.assertEqual(response.json["answer"], "Synthetic case DEMO-104 is Open.")
        generate.assert_not_called()

    def test_non_llm_unknown_record_is_not_invented(self):
        with patch.object(demo, "classify", return_value=("exact_lookup", 0.91)):
            response = self.client.post("/api/route", json={"query": "What is the status of case DEMO-999?"})
        self.assertIn("No exact synthetic record matched", response.json["answer"])

    def test_llm_uses_generation(self):
        with patch.object(demo, "classify", return_value=("summarize", 0.9)), patch.object(
            demo, "generate_answer", return_value="Fictional summary."
        ) as generate:
            response = self.client.post("/api/route", json={"query": "Summarize these notes"})
        self.assertEqual(response.json["route"], "llm")
        self.assertEqual(response.json["answer"], "Fictional summary.")
        generate.assert_called_once()

    def test_low_confidence_abstains(self):
        with patch.object(demo, "classify", return_value=("summarize", 0.5)), patch.object(
            demo, "generate_answer"
        ) as generate:
            response = self.client.post("/api/route", json={"query": "something"})
        self.assertEqual(response.json["route"], "clarify")
        generate.assert_not_called()

    def test_invalid_model_decision_surfaces_error(self):
        with patch.object(demo, "classify", side_effect=demo.UpstreamError("Invalid decision.")):
            response = self.client.post("/api/route", json={"query": "something"})
        self.assertEqual(response.status_code, 502)
        self.assertIn("Invalid decision", response.json["error"])

    def test_choice_probability_shape(self):
        decision = {"answers": {"intent": {"type": "choice", "choice": "exact_lookup", "confidence": 0.92, "probabilities": {"exact_lookup": 0.93}}}}
        self.assertEqual(demo.parse_decision(decision), ("exact_lookup", 0.92))


if __name__ == "__main__":
    unittest.main()
