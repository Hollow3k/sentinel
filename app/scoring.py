import json
import logging
from pathlib import Path

import pandas as pd
import shap
from xgboost import XGBClassifier

log = logging.getLogger("sentinel")
MODEL_DIR = Path(__file__).resolve().parent.parent / "models"

FEATURES = json.loads((MODEL_DIR / "features.json").read_text())
THRESHOLD = json.loads((MODEL_DIR / "metrics.json").read_text())["threshold"]

_model = None
_explainer = None


def load_model():
    global _model, _explainer
    try:
        m = XGBClassifier()
        m.load_model(str(MODEL_DIR / "model.json"))
        _model, _explainer = m, shap.TreeExplainer(m)
    except Exception:
        log.exception("model_load_failed")
        _model = _explainer = None


def rules_score(features: dict) -> float:
    # deliberately crude safety net, used only when the model is unavailable
    return 1.0 if features.get("Amount", 0) > 2000 else 0.0


def score(features: dict) -> dict:
    if _model is not None:
        try:
            df = pd.DataFrame([features])[FEATURES]
            p = float(_model.predict_proba(df)[0, 1])
            sv = _explainer.shap_values(df)[0]
            top = sorted(zip(FEATURES, sv), key=lambda x: abs(x[1]), reverse=True)[:3]
            expl = [{"feature": f, "contribution": round(float(v), 3),
                     "value": round(float(features[f]), 3)} for f, v in top]
            return {"score": p, "source": "model", "explanation": expl, "flagged": p >= THRESHOLD}
        except Exception:
            log.exception("model_score_failed")
    s = rules_score(features)
    return {"score": s, "source": "fallback_rules", "explanation": [], "flagged": s >= 1.0}