"""FastAPI service: frozen JSON contracts the React UI builds against.

  GET /                 -> legacy supervisor dashboard (server-rendered, offline-safe)
  GET /app              -> React SPA (frontend/dist, bundled, no CDN)
  GET /api/entities
  GET /api/entities/{entity_id}   (scores + signals + flags + evidence + SHAP drivers + feedback)
  GET /api/flags?entity=          (all flags or per-entity)
  GET /api/audit                  (ledger chain + verification)
  GET /api/validate               (precision/recall + top-N overlap)
  GET /api/trends                 (EIS/CAS per entity across submission windows)
  GET /api/feedback               (supervisor confirm/dismiss history from ledger)
  POST /api/feedback              (confirm/dismiss a flag -> ledger event)
  POST /api/ingest                (CSV upload stub -> ledger event)
"""
from __future__ import annotations

import json
import os

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "results.json")
TRENDS = os.path.join(HERE, "trends.json")
LEDGER = os.path.join(HERE, "ledger.jsonl")
DIST = os.path.join(HERE, "frontend", "dist")

app = FastAPI(title="SAT-SA prototype API", version="0.3.0")


class Feedback(BaseModel):
    entity_id: str
    rule_id: str
    decision: str  # confirm | dismiss
    note: str = ""


def _results() -> dict:
    with open(RESULTS) as f:
        return json.load(f)


def _feedback_events() -> list:
    from satsa.ledger import Ledger
    return [r for r in Ledger(LEDGER).read_all()
            if r["event"] == "supervisor_feedback"]


@app.get("/", response_class=HTMLResponse)
def index():
    path = os.path.join(HERE, "dashboard.html")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read()
    return "<h1>Run <code>python run.py</code> first to generate results.</h1>"


@app.get("/api/entities")
def entities():
    r = _results()
    return {"entities": [{"entity_id": e, **{k: r["scores"][e][k] for k in
                                             ("EIS", "CAS", "priority", "band")},
                          "n_flags": len(r["flags"].get(e, []))}
                         for e in sorted(r["scores"])]}


@app.get("/api/entities/{entity_id}")
def entity_detail(entity_id: str):
    r = _results()
    if entity_id not in r["scores"]:
        return JSONResponse({"error": "unknown entity"}, status_code=404)
    drivers = {aid: d for aid, d in r.get("explanations", {}).get("drivers", {}).items()
               if d["entity_id"] == entity_id}
    fb = [e for e in _feedback_events()
          if e["payload"].get("entity_id") == entity_id]
    return {"entity_id": entity_id, "scores": r["scores"][entity_id],
            "signals": r["signals"].get(entity_id, {}),
            "flags": r["flags"].get(entity_id, []),
            "shap_drivers": drivers,
            "explainer": r.get("explanations", {}).get("model", {}),
            "feedback": fb,
            "ground_truth": r["ground_truth"].get(entity_id, {})}


@app.get("/api/flags")
def flags(entity: str | None = Query(default=None)):
    r = _results()
    if entity:
        return {"entity_id": entity, "flags": r["flags"].get(entity, [])}
    all_flags = [f for fl in r["flags"].values() for f in fl]
    return {"count": len(all_flags), "flags": all_flags}


@app.get("/api/audit")
def audit():
    from satsa.ledger import Ledger
    led = Ledger(LEDGER)
    ok, msg = led.verify()
    return {"verified": ok, "message": msg, "events": led.read_all()}


@app.get("/api/validate")
def validate_ep():
    return _results()["metrics"]


@app.get("/api/trends")
def trends_ep():
    if not os.path.exists(TRENDS):
        return JSONResponse({"error": "trends not built — run python run.py"},
                            status_code=404)
    with open(TRENDS) as f:
        return json.load(f)


@app.get("/api/feedback")
def feedback_list():
    return {"feedback": _feedback_events()}


@app.post("/api/feedback")
def feedback_submit(fb: Feedback):
    if fb.decision not in ("confirm", "dismiss"):
        return JSONResponse({"error": "decision must be confirm|dismiss"},
                            status_code=400)
    from satsa.ledger import Ledger
    rec = Ledger(LEDGER).append("supervisor_feedback", fb.model_dump())
    return {"status": "recorded", "ledger": rec}


@app.post("/api/ingest")
def ingest_note():
    # v0 stub: real CSV ingest lives in satsa.store.load_csv_dir + run.py.
    from satsa.ledger import Ledger
    led = Ledger(LEDGER)
    rec = led.append("ingest_stub", {"note": "upload endpoint reserved for CSV/JSON"})
    return {"status": "reserved", "ledger": rec}


if os.path.isdir(DIST):
    app.mount("/app", StaticFiles(directory=DIST, html=True), name="react")

    @app.get("/app", include_in_schema=False)
    def app_noslash():
        return RedirectResponse(url="/app/")
