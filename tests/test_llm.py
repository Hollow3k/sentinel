from app import llm
FACTS = {"amount": 120.5, "score": 0.97, "hour_of_day": 3, "threshold": 0.94,
         "top_features": [{"feature": "V14", "contribution": 2.1, "value": -8.0}]}

GOOD = ("Transaction of 120.5 scored 0.97 against a threshold of 0.94 at hour 3. "
        "V14 had value -8.0 and contributed 2.1.")


# ---- is_grounded -------------------------------------------------------------

def test_grounded_summary_passes():
    assert llm.is_grounded(GOOD, FACTS)


def test_invented_number_fails():
    assert not llm.is_grounded(GOOD + " It was the 7th such case.", FACTS)
    assert not llm.is_grounded("The amount was 999.0 and the score 0.97.", FACTS)


def test_invented_feature_name_fails():
    assert not llm.is_grounded("V14 and V3 drove the score of 0.97.", FACTS)


def test_digits_in_feature_names_are_not_numbers():
    # "V14" contains 14, which is not in the facts; it must be treated as a name, not a number.
    assert llm.is_grounded("Feature V14 was the main driver.", FACTS)


def test_percentage_form_of_score_is_allowed():
    assert llm.is_grounded("The model gave a 97 percent risk score.", FACTS)


def test_no_features_listed():
    facts = {**FACTS, "top_features": []}
    assert llm.is_grounded("Amount 120.5 with score 0.97.", facts)
    assert not llm.is_grounded("V14 was high.", facts)


def test_template_is_grounded():
    # The fallback text must always pass the same check the LLM output is held to.
    assert llm.is_grounded(llm.template(FACTS), FACTS)


# ---- /flags/{id}/summary -----------------------------------------------------

def test_grounded_llm_text_is_used(client, flagged_tx, monkeypatch):
    # The template is grounded by construction, so it stands in for a well-behaved LLM answer.
    monkeypatch.setattr(llm, "generate_once", llm.template)
    r = client.post(f"/flags/{flagged_tx['id']}/summary")
    assert r.status_code == 200
    assert r.json()["source"] == "llm"
    assert r.json()["summary"]


def test_ungrounded_llm_text_falls_back_to_template(client, flagged_tx, monkeypatch):
    calls = []

    def fake(facts):
        calls.append(1)
        return "The amount was 99999 and the cardholder looks suspicious."
    monkeypatch.setattr(llm, "generate_once", fake)
    r = client.post(f"/flags/{flagged_tx['id']}/summary")
    assert r.json()["source"] == "template"
    assert len(calls) == 3  # first attempt + 2 retries, all ungrounded


def test_llm_exception_falls_back_to_template(client, flagged_tx, monkeypatch):
    def fake(facts):
        raise RuntimeError("network down")
    monkeypatch.setattr(llm, "generate_once", fake)
    r = client.post(f"/flags/{flagged_tx['id']}/summary")
    assert r.status_code == 200
    assert r.json()["source"] == "template"


def test_summary_is_saved_on_the_transaction(client, flagged_tx, monkeypatch):
    monkeypatch.setattr(llm, "generate_once", lambda facts: llm.template(facts))
    text = client.post(f"/flags/{flagged_tx['id']}/summary").json()["summary"]
    flags = client.get("/flags").json()
    assert flags[0]["summary"] == text


def test_summary_for_unknown_id_is_404(client):
    assert client.post("/flags/9999/summary").status_code == 404


# ---- generate_once -----------------------------------------------------------

class FakeClient:
    """Mimics client.chat.completions.create(...) and records what it was called with."""
    def __init__(self, content):
        self.calls = []
        outer = self

        class Completions:
            def create(self, **kwargs):
                outer.calls.append(kwargs)
                msg = type("M", (), {"content": content})
                return type("R", (), {"choices": [type("C", (), {"message": msg})]})
        self.chat = type("Chat", (), {"completions": Completions()})


def test_generate_once_strips_think_block(monkeypatch):
    fake = FakeClient("<think>secret reasoning 42</think>Score was 0.97.")
    monkeypatch.setattr(llm, "_get_client", lambda: fake)
    assert llm.generate_once(FACTS) == "Score was 0.97."
    call = fake.calls[0]
    assert call["temperature"] == 0
    assert call["messages"][0]["role"] == "system"


def test_generate_once_omits_reasoning_effort_when_empty(monkeypatch):
    fake = FakeClient("ok")
    monkeypatch.setattr(llm, "_get_client", lambda: fake)
    monkeypatch.setattr(llm, "REASONING_EFFORT", "")
    llm.generate_once(FACTS)
    assert "reasoning_effort" not in fake.calls[0]
