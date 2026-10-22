import json
import logging
import os
import re

import httpx
from groq import Groq

from app import scoring

log = logging.getLogger("sentinel")
MODEL = os.getenv("LLM_MODEL", "qwen/qwen3.8-27b")
# "none" = instant mode (no reasoning tokens). Set LLM_REASONING_EFFORT="" to omit the parameter.
REASONING_EFFORT = os.getenv("LLM_REASONING_EFFORT", "none")

SYSTEM = (
    "You write brief case notes for fraud analysts. Use ONLY the facts in the JSON provided. "
    "Do not use any number that is not in the JSON, and write numbers exactly as given. "
    "Mention features only if listed. Do not speculate about causes, intent or the cardholder, "
    "and do not recommend a decision. Maximum 3 sentences."
)
NUM = re.compile(r"-?\d+(?:,\d{3})*(?:\.\d+)?")
THINK = re.compile(r"<think>.*?</think>", re.DOTALL)

_client = None


def _get_client() -> Groq:
    global _client
    if _client is None:
        # Bind to IPv4: on networks with broken IPv6 routes httpx fails with WinError 10051
        # instead of falling back. Reads GROQ_API_KEY from the environment.
        _client = Groq(http_client=httpx.Client(
            transport=httpx.HTTPTransport(local_address="0.0.0.0"), timeout=30.0))
    return _client


def build_facts(tx) -> dict:
    return {
        "amount": round(tx.amount, 2), "score": round(tx.score, 2),
        "hour_of_day": tx.hour_of_day, "threshold": round(scoring.THRESHOLD, 2),
        "top_features": tx.explanation or [],
    }


def is_grounded(summary: str, facts: dict) -> bool:
    allowed = [facts["amount"], facts["score"], facts["score"] * 100,
               facts["hour_of_day"], facts["threshold"]]
    for e in facts["top_features"]:
        allowed += [abs(e["value"]), abs(e["contribution"])]
    text = re.sub(r"\bV\d+\b", "", summary)  # feature names contain digits
    for tok in NUM.findall(text):
        x = abs(float(tok.replace(",", "")))
        if not any(abs(x - a) <= max(0.01, 0.01 * abs(a)) for a in allowed):
            return False
    named = set(re.findall(r"\bV\d+\b", summary))
    return named <= {e["feature"] for e in facts["top_features"]}


def generate_once(facts: dict) -> str:
    kwargs = {}
    if REASONING_EFFORT:
        kwargs["reasoning_effort"] = REASONING_EFFORT
    resp = _get_client().chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": json.dumps(facts)},
        ],
        temperature=0,
        max_tokens=300,
        **kwargs,
    )
    text = resp.choices[0].message.content or ""
    return THINK.sub("", text).strip()  # defensive: drop any leaked reasoning block


def template(facts: dict) -> str:
    feats = ", ".join(f["feature"] for f in facts["top_features"]) or "none available"
    return (f"Transaction of {facts['amount']:.2f} flagged with risk score {facts['score']:.2f} "
            f"(threshold {facts['threshold']:.2f}). Top contributing features: {feats}.")


def summarize(tx, retries: int = 2):
    facts = build_facts(tx)
    for _ in range(retries + 1):
        try:
            text = generate_once(facts)
        except Exception as e:  # noqa: BLE001 - any LLM/network failure must fall back to the template
            log.warning("llm_call_failed error=%s", type(e).__name__)
            break
        if text and is_grounded(text, facts):
            return text, "llm"
    return template(facts), "template"