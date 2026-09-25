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

from fastapi import FastAPI, File, Query, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "results.json")
TRENDS = os.path.join(HERE, "trends.json")
LEDGER = os.path.join(HERE, "ledger.jsonl")
DB_PATH = os.path.join(HERE, "satsa.duckdb")
DIST = os.path.join(HERE, "frontend", "dist")


def _expected_map() -> dict:
    import yaml
    p = os.path.join(HERE, "attck", "expected_map.yaml")
    if os.path.exists(p):
        with open(p) as f:
            return yaml.safe_load(f)
    return {}

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
    r = _results()
    m = r.get("metrics") or {"note": "no ground truth for this assessment — "
                                     "upload findings.csv to validate against "
                                     "manual review"}
    if isinstance(m, dict) and "precision" not in m:
        return {**m, "sector_findings": r.get("sector_findings", [])}
    return {**m, "sector_findings": r.get("sector_findings", [])}


@app.get("/api/sector")
def sector_ep():
    r = _results()
    return {"count": len(r.get("sector_findings", [])),
            "findings": r.get("sector_findings", [])}


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


@app.post("/api/ingest", status_code=202)
async def ingest(
    alerts: UploadFile = File(...),
    cases: UploadFile = File(...),
    assets: UploadFile = File(...),
    handoffs: UploadFile | None = File(default=None),
    escalations: UploadFile | None = File(default=None),
    exercises: UploadFile | None = File(default=None),
    findings: UploadFile | None = File(default=None),
):
    """Inspector submission upload: files are staged, then a background job
    parses -> validates -> hash-seals -> pipelines -> writes results.
    Poll GET /api/jobs/{job_id} for honest stage-by-stage progress.
    See schemas/SCHEMA.md for the contract."""
    payloads = {}
    for key, f in (("alerts", alerts), ("cases", cases), ("assets", assets),
                   ("handoffs", handoffs), ("escalations", escalations),
                   ("exercises", exercises), ("findings", findings)):
        if f is not None:
            payloads[key] = (f.filename, await f.read())
    job = _new_job()
    _POOL.submit(_run_ingest_job, job["job_id"], payloads)
    return {"job_id": job["job_id"], "status_url": f"/api/jobs/{job['job_id']}"}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
    if job is None:
        return JSONResponse({"error": "unknown job"}, status_code=404)
    return job

# ---- background ingest jobs: honest stage-by-stage progress ----
import threading as _th
import time as _time
import uuid as _uuid
from concurrent.futures import ThreadPoolExecutor as _Pool

_JOBS: dict = {}
_JOBS_LOCK = _th.Lock()
_POOL = _Pool(max_workers=1)  # one assessment at a time: ledger stays ordered


def _new_job() -> dict:
    job = {"job_id": _uuid.uuid4().hex[:12], "state": "queued", "pct": 0,
           "stage": "queued", "detail": "waiting for worker",
           "log": [], "result": None, "error": None}
    with _JOBS_LOCK:
        _JOBS[job["job_id"]] = job
    return job


def _emit(job: dict, stage: str, pct: float, detail: str = ""):
    with _JOBS_LOCK:
        job["stage"] = stage
        job["pct"] = round(pct, 1)
        job["detail"] = detail
        job["log"].append({"t": _time.strftime("%H:%M:%S"), "stage": stage,
                           "pct": round(pct, 1), "detail": detail})
        job["log"] = job["log"][-60:]


def _run_ingest_job(job_id: str, payloads: dict):
    """Worker: parse -> validate -> hash-seal -> pipeline -> write files."""
    import io
    import pandas as pd
    from satsa.ledger import Ledger
    from satsa.store import init_and_ingest
    from satsa.config import load as load_config
    from satsa.realdata import load_manual_findings
    from satsa.pipeline import run_assessment

    with _JOBS_LOCK:
        job = _JOBS[job_id]
        job["state"] = "running"
    try:
        total_bytes = sum(len(b) for _, b in payloads.values())
        _emit(job, "parse", 2,
              f"parsing {len(payloads)} files ({total_bytes / 1048576:.1f} MB)")

        def _csv(key, required):
            if key not in payloads:
                return None
            name, blob = payloads[key]
            df = pd.read_csv(io.BytesIO(blob))
            if required:
                missing = [c for c in required if c not in df.columns]
                if missing:
                    raise ValueError(f"{name}: missing columns {missing}")
            return df

        a = _csv("alerts", ["alert_id", "entity_id", "severity", "asset_id",
                            "technique_id", "created_at", "closed_at"])
        c = _csv("cases", ["case_id", "entity_id", "alert_id", "note"])
        t = _csv("assets", ["asset_id", "entity_id", "criticality", "role"])
        h = _csv("handoffs", None)
        e = _csv("escalations", None)
        x = _csv("exercises", None)
        _emit(job, "parse", 8, f"parsed {len(a):,} alerts, {len(c):,} cases, "
                               f"{len(t):,} assets")

        # optional-column defaults (logged, auditable)
        defaulted = []
        for col in ("orig_severity", "analyst", "reported_minutes", "status"):
            if col not in a.columns:
                defaulted.append(col)
                a[col] = a["severity"] if col == "orig_severity" else (
                    a["handling_minutes"] if col == "reported_minutes"
                    else ("unknown" if col == "analyst" else "closed"))
        if "sla_hours" not in a.columns:
            defaulted.append("sla_hours=24")
            a["sla_hours"] = 24
        if "handling_minutes" not in a.columns:
            a["handling_minutes"] = (
                pd.to_datetime(a["closed_at"], format="mixed")
                - pd.to_datetime(a["created_at"], format="mixed")).dt.total_seconds() / 60.0
        a["escalated"] = a["escalated"].astype(bool) if "escalated" in a.columns else False
        if "status" not in t.columns:
            t["status"] = "active"
        a = a.drop(columns=[cc for cc in ("criticality", "role") if cc in a.columns])
        a = a.merge(t[["asset_id", "entity_id", "criticality", "role"]].drop_duplicates(),
                    on=["asset_id", "entity_id"], how="left")
        _emit(job, "validate", 12,
              f"schema OK" + (f"; defaulted: {', '.join(defaulted)}" if defaulted
                              else "; no defaults needed"))

        ex_list = x.to_dict("records") if x is not None else []
        gt = None
        if "findings" in payloads:
            import tempfile
            with tempfile.NamedTemporaryFile("w", suffix=".csv",
                                             delete=False) as tf:
                tf.write(payloads["findings"][1].decode())
                gt = load_manual_findings(tf.name)

        cfg, cfg_hash = load_config()
        led = Ledger(LEDGER)
        ing_hash = init_and_ingest(DB_PATH, a, c, t, h, e)
        led.append("ingestion", {"rows": {k: len(v) for k, v in
                                          (("alerts", a), ("cases", c),
                                           ("assets", t))},
                                 "sha256": ing_hash, "source": "inspector-upload",
                                 "files": [payloads[k][0] for k in
                                           ("alerts", "cases", "assets")]})
        led.append("rule_pack", {"sha256": cfg_hash})
        _emit(job, "seal", 18, f"hash-sealed {ing_hash[:12]}… "
                               f"({len(a):,} alerts, {len(c):,} cases)")

        def _fwd(stage, pct, detail):
            _emit(job, stage, 18 + 0.74 * pct, detail)

        res = run_assessment(a, c, t, h, e, cfg, _expected_map(), None, None,
                             ex_list, gt, ledger=led, source="upload",
                             progress=_fwd)

        _emit(job, "write", 94, "writing results, trends, dashboard")
        with open(RESULTS, "w") as f:
            json.dump({"scores": res["scores"], "signals": res["signals"],
                       "flags": res["flags"], "metrics": res["metrics"],
                       "ground_truth": gt or {},
                       "explanations": res["explanations"],
                       "sector_findings": res["sector"],
                       "model_version": "upload"}, f, indent=1, default=str)
        with open(TRENDS, "w") as f:
            json.dump({"windows": ["uploaded"],
                       "series": {ee: {"EIS": [s["EIS"]], "CAS": [s["CAS"]]}
                                  for ee, s in res["scores"].items()}}, f, indent=1)
        from dashboard import build_dashboard_html
        with open(os.path.join(HERE, "dashboard.html"), "w", encoding="utf-8") as f:
            f.write(build_dashboard_html(res["scores"], res["flags"], res["signals"],
                                         res["metrics"], led.read_all(),
                                         json.load(open(TRENDS)),
                                         res["explanations"], res["sector"]))
        ranked = sorted(res["scores"],
                        key=lambda x: res["scores"][x]["priority"], reverse=True)
        with _JOBS_LOCK:
            job["result"] = {"status": "assessed", "entities": len(res["scores"]),
                             "n_flags": sum(len(v) for v in res["flags"].values()),
                             "ranked": ranked, "metrics": res["metrics"],
                             "sector_count": len(res["sector"])}
            job["state"] = "done"
        _emit(job, "done", 100,
              f"{len(res['scores'])} entities, "
              f"{sum(len(v) for v in res['flags'].values())} flags")
    except Exception as ex:
        with _JOBS_LOCK:
            job["state"] = "error"
            job["error"] = str(ex)[:500]
        _emit(job, "error", job.get("pct", 0), str(ex)[:300])



if os.path.isdir(DIST):
    app.mount("/app", StaticFiles(directory=DIST, html=True), name="react")

    @app.get("/app", include_in_schema=False)
    def app_noslash():
        return RedirectResponse(url="/app/")
