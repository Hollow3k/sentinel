import os
import uuid

import httpx
import pandas as pd
from dotenv import load_dotenv
from sklearn.model_selection import train_test_split

load_dotenv()
BASE = os.getenv("BASE_URL", "http://localhost:8000")
KEY = os.getenv("ADMIN_API_KEY", "admin-key")

df = pd.read_csv("data/creditcard.csv")
X, y = df.drop(columns=["Class"]), df["Class"]
# must mirror the splits in ml/train.py so rows come from the held-out test set
_, X_tmp, _, y_tmp = train_test_split(X, y, test_size=0.4, stratify=y, random_state=42)
_, X_te, _, y_te = train_test_split(X_tmp, y_tmp, test_size=0.5, stratify=y_tmp, random_state=42)

rows = pd.concat([X_te[y_te == 1].sample(40, random_state=1),
                  X_te[y_te == 0].sample(260, random_state=1)]).sample(frac=1, random_state=1)

with httpx.Client(base_url=BASE, headers={"X-API-Key": KEY}, timeout=30) as c:
    for _, r in rows.iterrows():
        c.post("/transactions",
               json={"idempotency_key": uuid.uuid4().hex, "features": r.to_dict()}).raise_for_status()
print("seeded", len(rows), "transactions")