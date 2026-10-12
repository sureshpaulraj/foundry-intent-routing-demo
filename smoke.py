from app import app

QUERIES = (
    ("What is the status of case DEMO-104?", "non_llm"),
    ("Summarize these fictional customer feedback notes.", "llm"),
)

with app.test_client() as client:
    for query, expected_route in QUERIES:
        response = client.post("/api/route", json={"query": query})
        payload = response.get_json()
        if response.status_code != 200 or payload.get("route") != expected_route:
            raise SystemExit(f"Smoke test failed for {expected_route}: {response.status_code} {payload}")
        print(f"{expected_route}: {payload['answer']}")
