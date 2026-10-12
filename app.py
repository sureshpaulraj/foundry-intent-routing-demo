import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from azure.core.exceptions import ClientAuthenticationError
from azure.identity import DefaultAzureCredential
from flask import Flask, jsonify, request, send_from_directory

BASE = Path(__file__).parent
EXAMPLES = json.loads((BASE / "synthetic_examples.json").read_text(encoding="utf-8"))
EXACT_ANSWERS = {row["query"].casefold(): row for row in EXAMPLES if row["route"] == "non_llm"}
ENDPOINT = os.environ.get("FOUNDRY_ENDPOINT", "").rstrip("/")
DECISION_DEPLOYMENT = os.environ.get("DECISION_DEPLOYMENT", "intent-decision")
GENERATION_DEPLOYMENT = os.environ.get("GENERATION_DEPLOYMENT", "gpt-4-1-mini")
credential = DefaultAzureCredential()
app = Flask(__name__)
app.json.ensure_ascii = False

CATEGORIES = {
    "semantic_faq": ("llm", "Interpret or synthesize an answer from natural-language FAQ context."),
    "summarize": ("llm", "Summarize multiple unstructured passages."),
    "rewrite": ("llm", "Rewrite, translate, or adapt prose to an audience."),
    "reason": ("llm", "Compare concepts or explain an ambiguous scenario."),
    "exact_lookup": ("non_llm", "Retrieve an exact ID or a stored answer from a source of record."),
    "calculation": ("non_llm", "Compute a precise numeric or date result."),
    "validation": ("non_llm", "Apply an explicit validation or redaction rule."),
    "transaction": ("non_llm", "Perform or check an authorized system action."),
    "clarify": ("clarify", "The request lacks enough information to choose a safe handler."),
}
CRITERIA = {label: meaning for label, (_, meaning) in CATEGORIES.items()}


class UpstreamError(RuntimeError):
    pass


def call_foundry(path, body):
    if not ENDPOINT:
        raise UpstreamError("FOUNDRY_ENDPOINT is not configured.")
    try:
        token = credential.get_token("https://cognitiveservices.azure.com/.default").token
    except ClientAuthenticationError as exc:
        raise UpstreamError("Managed identity could not authenticate to Foundry.") from exc
    payload = json.dumps(body).encode("utf-8")
    upstream = urllib.request.Request(
        ENDPOINT + path,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(upstream, timeout=40) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise UpstreamError(f"Foundry returned HTTP {exc.code}.") from exc
    except urllib.error.URLError as exc:
        raise UpstreamError("Could not connect to Foundry.") from exc


def parse_decision(payload):
    answers = payload.get("answers")
    answer = answers.get("intent") if isinstance(answers, dict) else None
    if not isinstance(answer, dict) or answer.get("type") != "choice":
        raise UpstreamError("Foundry returned an invalid intent decision.")
    category = answer.get("choice")
    if category not in CATEGORIES:
        raise UpstreamError("Foundry returned an unsupported intent category.")
    probabilities = answer.get("probabilities")
    if not isinstance(probabilities, dict):
        raise UpstreamError("Foundry did not return choice probabilities.")
    confidence = answer.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        raise UpstreamError("Foundry returned an invalid choice probability.")
    return category, confidence


def classify(text):
    payload = call_foundry(
        "/providers/microsoft/v1/systemone",
        {
            "model": DECISION_DEPLOYMENT,
            "state": text,
            "questions": {
                "intent": {
                    "type": "choice",
                    "instructions": (
                        "Classify the user's primary intent for routing an FAQ assistant. "
                        "Choose clarify if the request is too vague. An exact lookup, calculation, "
                        "validation, or action belongs on a deterministic path, even when phrased politely. "
                        "Never infer facts or act on a request."
                    ),
                    "criteria": CRITERIA,
                }
            },
        },
    )
    return parse_decision(payload)


def generate_answer(text):
    context = "\n".join(
        f"Q: {row['query']}\nA: {row['response']}"
        for row in EXAMPLES
        if row["route"] == "llm"
    )
    payload = call_foundry(
        f"/openai/deployments/{GENERATION_DEPLOYMENT}/chat/completions?api-version=2024-10-21",
        {
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are demonstrating an LLM route for a fictional FAQ assistant. "
                        "Answer using only the synthetic examples below. Do not imply access to live "
                        "systems, private documents, or actual company policies. If examples do not "
                        "support an answer, say so. Keep it under 100 words.\n\n" + context
                    ),
                },
                {"role": "user", "content": text},
            ],
            "max_tokens": 180,
            "temperature": 0.2,
        },
    )
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise UpstreamError("The generative model returned no answer.")
    content = choices[0].get("message", {}).get("content")
    if not isinstance(content, str) or not content.strip():
        raise UpstreamError("The generative model returned an empty answer.")
    return content.strip()


@app.get("/")
def index():
    return send_from_directory(BASE, "index.html")


@app.get("/api/examples")
def examples():
    return jsonify(EXAMPLES)


@app.post("/api/route")
def route():
    payload = request.get_json(silent=True)
    text = payload.get("query") if isinstance(payload, dict) else None
    if not isinstance(text, str) or not text.strip() or len(text) > 500:
        return jsonify(error="Provide a query of 1 to 500 characters."), 400
    text = text.strip()
    try:
        category, confidence = classify(text)
        route_name, reason = CATEGORIES[category]
        if confidence < 0.65 or route_name == "clarify":
            return jsonify(
                route="clarify", category=category, confidence=confidence,
                reason="The decision was uncertain; please make your request more specific.",
                answer="Please provide a specific question or an exact identifier.",
                model=DECISION_DEPLOYMENT,
            )
        if route_name == "llm":
            answer = generate_answer(text)
            handler = GENERATION_DEPLOYMENT
        else:
            record = EXACT_ANSWERS.get(text.casefold())
            answer = record["response"] if record else (
                "No exact synthetic record matched. Connect a source-of-record API to answer this request."
            )
            handler = "Synthetic exact-match dataset (no LLM)"
        return jsonify(
            route=route_name, category=category, confidence=confidence,
            reason=reason, answer=answer, handler=handler, model=DECISION_DEPLOYMENT,
        )
    except UpstreamError as exc:
        app.logger.error("Foundry request failed: %s", exc)
        return jsonify(error=str(exc)), 502


if __name__ == "__main__":
    app.run(port=8000)
