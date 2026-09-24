"""Alert-level risk explainer: XGBoost + SHAP (CPU-only, offline).

Role in the architecture: RULES detect (never the model); the model EXPLAINS.
For every flagged hot alert we surface the top feature drivers
("handling_minutes pushed risk up +0.31") so a supervisor sees WHY the
statistics point at an alert, next to the rule ID + evidence that fired it.
No finding ever depends on the model alone.

Model: binary classifier P(violation | alert features), violation = E2-style
un-escalated hot alert OR E3-style fast-closed hot alert. Trained on the
ingested window itself (supervisory batch, not a pretrained black box);
model params + AUC are ledger-logged with the run.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

TECH_RISK = {"T1486": 1.0, "T1003": 0.9, "T1190": 0.8, "T1566": 0.7,
             "T1078": 0.7, "T1059": 0.5, "T1133": 0.5, "T1021": 0.5}
SEV_ORD = {"low": 0, "medium": 1, "high": 2, "critical": 3}
TIER_ORD = {"Tier-3": 0, "Tier-2": 1, "Tier-1": 2}
FEATURES = ["sev", "log_handling_min", "deadline_prox", "tier",
            "tech_risk", "not_escalated"]


def featurize(alerts: pd.DataFrame) -> pd.DataFrame:
    a = alerts.copy()
    # DuckDB round-trips datetimes as mixed ISO strings; parse flexibly.
    a["created"] = pd.to_datetime(a["created_at"], format="mixed")
    a["closed"] = pd.to_datetime(a["closed_at"], format="mixed")
    window_min = a["sla_hours"].astype(float) * 60.0
    elapsed = (a["closed"] - a["created"]).dt.total_seconds() / 60.0
    X = pd.DataFrame({
        "sev": a["severity"].map(SEV_ORD).fillna(0).astype(float),
        "log_handling_min": np.log1p(np.clip(a["handling_minutes"].astype(float), 0, None)),
        "deadline_prox": np.clip(elapsed / np.clip(window_min, 1, None), 0, 1),
        "tier": a["criticality"].map(TIER_ORD).fillna(0).astype(float),
        "tech_risk": a["technique_id"].map(TECH_RISK).fillna(0.5).astype(float),
        "not_escalated": (~a["escalated"].astype(bool)).astype(float),
    })
    return X


def violation_label(alerts: pd.DataFrame) -> pd.Series:
    hot = alerts["severity"].isin(["high", "critical"])
    e2 = hot & (alerts["criticality"] == "Tier-1") & (~alerts["escalated"].astype(bool))
    e3 = hot & (alerts["handling_minutes"].astype(float) <= 15)
    return (e2 | e3).astype(int)


def train_explain(alerts: pd.DataFrame, top_per_entity: int = 3,
                  top_drivers: int = 3, seed: int = 42) -> dict:
    """Train on the window, SHAP-explain the riskiest flagged alerts per entity."""
    import xgboost as xgb
    X = featurize(alerts)
    y = violation_label(alerts)
    if y.sum() < 10 or y.mean() in (0.0, 1.0):
        return {"model": {"trained": False, "reason": "insufficient positives"},
                "drivers": {}}
    clf = xgb.XGBClassifier(n_estimators=200, max_depth=4, learning_rate=0.08,
                            subsample=0.9, colsample_bytree=0.9, reg_lambda=1.0,
                            random_state=seed, n_jobs=-1, eval_metric="logloss")
    clf.fit(X, y)
    proba = clf.predict_proba(X)[:, 1]
    auc = float(__import__("sklearn.metrics", fromlist=["roc_auc_score"])
                .roc_auc_score(y, proba))

    import shap
    ex = shap.TreeExplainer(clf)
    sv = np.asarray(ex.shap_values(X))
    base = float(np.asarray(ex.expected_value).ravel()[0])

    out = {"alert_id": alerts["alert_id"].tolist(),
           "entity": alerts["entity_id"].tolist(),
           "proba": proba.tolist()}
    d = pd.DataFrame(out)
    d["is_viol"] = y.tolist()
    drivers: dict = {}
    for ent, g in d.sort_values("proba", ascending=False).groupby("entity"):
        for row_idx, r in g.head(top_per_entity).iterrows():
            idx = int(row_idx)
            row_sv = sv[idx] if sv.ndim == 2 else sv[idx, :]
            order = np.argsort(-np.abs(row_sv))[:top_drivers]
            drivers[r["alert_id"]] = {
                "entity_id": ent, "p_violation": round(float(r["proba"]), 3),
                "label_violation": int(r["is_viol"]),
                "base_logodds": round(base, 3),
                "top_drivers": [{"feature": FEATURES[j],
                                 "shap": round(float(row_sv[j]), 3),
                                 "value": round(float(X.iloc[idx, j]), 3)}
                                for j in order],
            }
    return {"model": {"trained": True, "auc_train": round(auc, 3),
                      "n_alerts": len(X), "n_violations": int(y.sum()),
                      "features": FEATURES,
                      "params": {"n_estimators": 200, "max_depth": 4}},
            "drivers": drivers}
