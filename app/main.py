import logging
import json
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import llm, scoring
from app.auth import require_role
from app.db import Base, Review, SessionLocal, Transaction, engine
from app.schemas import ReviewIn, TxIn

logging.basicConfig(level=logging.INFO, format="time=%(asctime)s level=%(levelname)s %(message)s")
log = logging.getLogger("sentinel")
DEMO_ROWS = json.loads((Path(__file__).parent / "demo_rows.json").read_text())


@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(engine)
    scoring.load_model()
    log.info("startup model_loaded=%s", scoring._model is not None)
    yield


app = FastAPI(title="Sentinel", lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    # FastAPI's default handler echoes the rejected input back. For NaN/inf that input cannot be
    # serialised as JSON, which turned a 422 into a 500. Return only where/what/why instead.
    errors = [{"loc": e["loc"], "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": errors})
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"],
                   allow_methods=["*"], allow_headers=["*"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def tx_out(t, reviewed=False):
    return {"id": t.id, "idempotency_key": t.idempotency_key, "amount": t.amount,
            "time_seconds": t.time_seconds, "hour_of_day": t.hour_of_day,
            "score": round(t.score, 4), "source": t.source, "flagged": t.flagged,
            "explanation": t.explanation, "summary": t.summary, "reviewed": reviewed,
            "created_at": t.created_at.isoformat()}


@app.get("/health")
def health():
    return {"status": "ok", "model_loaded": scoring._model is not None}


@app.post("/transactions")
def create_tx(body: TxIn, response: Response, db: Session = Depends(get_db),
              _=Depends(require_role("admin"))):
    def existing():
        return db.query(Transaction).filter_by(idempotency_key=body.idempotency_key).first()

    ex = existing()
    if ex:
        if ex.features != body.features:
            raise HTTPException(409, "idempotency key reused with a different payload")
        response.status_code = 200
        return tx_out(ex)

    r = scoring.score(body.features)
    t = Transaction(
        idempotency_key=body.idempotency_key, features=body.features,
        time_seconds=body.features["Time"], amount=body.features["Amount"],
        hour_of_day=int(body.features["Time"] // 3600) % 24,
        bucket=min(int(r["score"] * 10), 9), score=r["score"], source=r["source"],
        flagged=r["flagged"], explanation=r["explanation"],
    )
    db.add(t)
    try:
        db.commit()
    except IntegrityError:  # a concurrent duplicate won the race
        db.rollback()
        winner = existing()
        if winner is None:
            log.exception("idempotency_race_lookup_failed key=%s", body.idempotency_key)
            raise HTTPException(503, "could not resolve idempotency conflict")
        if winner.features != body.features:
            raise HTTPException(409, "idempotency key reused with a different payload")
        response.status_code = 200
        return tx_out(winner)
    db.refresh(t)
    response.status_code = 201
    log.info("tx_scored id=%s source=%s flagged=%s score=%.4f", t.id, t.source, t.flagged, t.score)
    return tx_out(t)


@app.post("/demo/seed")
def seed_demo(db: Session = Depends(get_db)):
    created = 0
    for index in range(10):
        label = "fraud" if index % 3 == 0 else "legit"
        features = DEMO_ROWS[label]
        result = scoring.score(features)
        transaction = Transaction(
            idempotency_key=f"demo-{uuid.uuid4().hex}",
            features=features,
            time_seconds=features["Time"],
            amount=features["Amount"],
            hour_of_day=int(features["Time"] // 3600) % 24,
            bucket=min(int(result["score"] * 10), 9),
            score=result["score"],
            source=result["source"],
            flagged=result["flagged"],
            explanation=result["explanation"],
        )
        db.add(transaction)
        created += 1
    db.commit()
    log.info("demo_seeded count=%s", created)
    return {"created": created}


@app.get("/flags")
def list_flags(reviewed: bool | None = None, limit: int = Query(100, ge=1, le=500),
               db: Session = Depends(get_db)):
    reviewed_ids = [r[0] for r in db.query(Review.transaction_id).distinct()]
    q = db.query(Transaction).filter(Transaction.flagged.is_(True))
    if reviewed is True:
        q = q.filter(Transaction.id.in_(reviewed_ids))
    elif reviewed is False:
        q = q.filter(~Transaction.id.in_(reviewed_ids))
    rows = q.order_by(Transaction.score.desc()).limit(limit).all()
    return [tx_out(t, t.id in reviewed_ids) for t in rows]


def _flagged_or_404(db, tx_id):
    t = db.get(Transaction, tx_id)
    if t is None or not t.flagged:
        raise HTTPException(404, "flagged transaction not found")
    return t


@app.post("/flags/{tx_id}/review")
def review_flag(tx_id: int, body: ReviewIn, db: Session = Depends(get_db),
                role="public"):
    _flagged_or_404(db, tx_id)
    db.add(Review(transaction_id=tx_id, decision=body.decision, note=body.note, reviewer_role=role))
    db.commit()
    log.info("review tx=%s decision=%s role=%s", tx_id, body.decision, role)
    return {"transaction_id": tx_id, "decision": body.decision}


@app.post("/flags/{tx_id}/summary")
def make_summary(tx_id: int, db: Session = Depends(get_db)):
    t = _flagged_or_404(db, tx_id)
    summary, source = llm.summarize(t)
    t.summary = summary
    db.commit()
    return {"summary": summary, "source": source}


HOURLY = text("""
WITH hourly AS (
  SELECT hour_of_day, COUNT(*) AS n,
         SUM(CASE WHEN flagged THEN 1 ELSE 0 END) AS flagged_n
  FROM transactions GROUP BY hour_of_day)
SELECT hour_of_day, n, flagged_n,
       ROUND(1.0 * flagged_n / n, 4) AS flag_rate,
       SUM(flagged_n) OVER (ORDER BY hour_of_day) AS cumulative_flagged
FROM hourly ORDER BY hour_of_day""")
BUCKETS = text("SELECT bucket, COUNT(*) AS n FROM transactions GROUP BY bucket ORDER BY bucket")
OUTCOMES = text("""
SELECT decision, COUNT(*) AS n,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct
FROM reviews GROUP BY decision""")


def _rows(db, q):
    return [dict(r._mapping) for r in db.execute(q)]


@app.get("/stats")
def stats(db: Session = Depends(get_db)):
    return {"hourly": _rows(db, HOURLY), "score_buckets": _rows(db, BUCKETS),
            "reviews": _rows(db, OUTCOMES)}


UI = Path(__file__).resolve().parent.parent / "dashboard" / "dist"
if UI.exists():  # serves the built dashboard; must stay last so API routes win
    app.mount("/", StaticFiles(directory=UI, html=True), name="ui")