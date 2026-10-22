import json, pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import (average_precision_score, precision_recall_curve,
                             precision_score, recall_score, confusion_matrix)
from xgboost import XGBClassifier

df = pd.read_csv("data/creditcard.csv")
X, y = df.drop(columns=["Class"]), df["Class"]

# 60/20/20 stratified split: train / validation (pick threshold) / test (final report)
X_tr, X_tmp, y_tr, y_tmp = train_test_split(X, y, test_size=0.4, stratify=y, random_state=42)
X_val, X_te, y_val, y_te = train_test_split(X_tmp, y_tmp, test_size=0.5, stratify=y_tmp, random_state=42)

spw = (y_tr == 0).sum() / (y_tr == 1).sum()   # handles the imbalance
model = XGBClassifier(n_estimators=300, max_depth=4, learning_rate=0.1,
                      scale_pos_weight=spw, eval_metric="aucpr",
                      random_state=42, n_jobs=-1)
model.fit(X_tr, y_tr)

# choose threshold on VALIDATION data (best F1), never on test data
p_val = model.predict_proba(X_val)[:, 1]
prec, rec, thr = precision_recall_curve(y_val, p_val)
f1 = 2 * prec[:-1] * rec[:-1] / (prec[:-1] + rec[:-1] + 1e-9)
threshold = float(thr[f1.argmax()])

# final report on untouched TEST data
p_te = model.predict_proba(X_te)[:, 1]
pred = (p_te >= threshold).astype(int)
metrics = {
    "pr_auc": float(average_precision_score(y_te, p_te)),
    "threshold": threshold,
    "precision": float(precision_score(y_te, pred)),
    "recall": float(recall_score(y_te, pred)),
    "confusion_matrix": confusion_matrix(y_te, pred).tolist(),
    "fraud_rate_test": float(y_te.mean()),
}
print(json.dumps(metrics, indent=2))
json.dump(metrics, open("models/metrics.json", "w"), indent=2)
model.save_model("models/model.json")
json.dump(list(X.columns), open("models/features.json", "w"))