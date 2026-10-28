"""Evaluate grounded summary behavior with mocked responses; no API key is required."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import llm

facts = {
    "amount": 120.5,
    "score": 0.97,
    "hour_of_day": 3,
    "threshold": 0.94,
    "top_features": [{"feature": "V14", "contribution": 2.1, "value": -8.0}],
}
cases = [
    "Transaction amount 120.5 has score 0.97. V14 contributed 2.1.",
    "Transaction amount 9999 has score 0.97. V14 contributed 2.1.",
    "V14 and V3 appear in this case.",
]
results = [{"summary": text, "grounded": llm.is_grounded(text, facts)} for text in cases]
print(json.dumps({
    "cases": len(results),
    "grounded": sum(result["grounded"] for result in results),
    "grounded_rate": round(sum(result["grounded"] for result in results) / len(results), 3),
    "results": results,
}, indent=2))
