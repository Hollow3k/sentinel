# app/schemas.py
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator

from app.scoring import FEATURES

Num = Annotated[float, Field(allow_inf_nan=False)]


class TxIn(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    features: dict[str, Num]

    @field_validator("features")
    @classmethod
    def check_features(cls, v):
        missing, extra = set(FEATURES) - set(v), set(v) - set(FEATURES)
        if missing or extra:
            raise ValueError(f"missing={sorted(missing)} unexpected={sorted(extra)}")
        if not 0 <= v["Amount"] <= 1_000_000:
            raise ValueError("Amount out of range")
        if v["Time"] < 0:
            raise ValueError("Time must be >= 0")
        return v


class ReviewIn(BaseModel):
    decision: Literal["confirm_fraud", "dismiss"]
    note: str | None = Field(default=None, max_length=500)