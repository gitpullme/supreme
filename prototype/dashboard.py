"""Offline supervisor dashboard: server-rendered HTML, zero CDN/JS deps.

Charts are matplotlib PNGs embedded as base64 -> the page works fully
air-gapped with no npm build step (the React+Recharts UI in the plan builds
against the same API contracts in api.py).
"""
from __future__ import annotations

import base64
import io

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def _png(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=110)
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def scatter_chart(scores: dict) -> str:
    fig, ax = plt.subplots(figsize=(5.2, 4.2))
    for ent, s in sorted(scores.items()):
        ax.scatter(s["CAS"], s["EIS"], s=160)
        ax.annotate(ent, (s["CAS"], s["EIS"]), textcoords="offset points",
                    xytext=(6, 6), fontsize=9, weight="bold")
    ax.set_xlabel("CAS — Coverage Assurance (worse →)")
    ax.set_ylabel("EIS — Execution Integrity (worse →)")
    ax.set_title("Supervisory triage: EIS × CAS (keep axes separate)")
    ax.set_xlim(-2, 102)
    ax.set_ylim(-2, 102)
    ax.grid(alpha=0.3)
    return _png(fig)


def bars_chart(scores: dict) -> str:
    ents = sorted(scores)
    eis = [scores[e]["EIS"] for e in ents]
    cas = [scores[e]["CAS"] for e in ents]
    x = range(len(ents))
    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    ax.bar([i - 0.2 for i in x], eis, width=0.4, label="EIS")
    ax.bar([i + 0.2 for i in x], cas, width=0.4, label="CAS")
    ax.set_xticks(list(x))
    ax.set_xticklabels(ents)
    ax.set_ylim(0, 100)
    ax.set_title("EIS / CAS per entity (0–100, higher = worse)")
    ax.legend()
    return _png(fig)


def cliff_chart(signals: dict) -> str:
    ents = sorted(signals)
    vals = [signals[e].get("cliff_frac", 0) * 100 for e in ents]
    fig, ax = plt.subplots(figsize=(6.4, 3.0))
    ax.bar(ents, vals)
    ax.axhline(10, linestyle="--", label="uniform-handling baseline (~10%)")
    ax.axhline(30, linestyle=":", label="flag threshold (30%)")
    ax.set_title("% closures in final 10% of SLA window (E1 cliff)")
    ax.legend(fontsize=8)
    return _png(fig)


def trend_chart(trends: dict | None) -> str:
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    if not trends or not trends.get("windows"):
        ax.text(0.5, 0.5, "no trend windows", ha="center")
        return _png(fig)
    w = trends["windows"]
    x = range(len(w))
    for ent in sorted(trends["series"]):
        ax.plot(x, trends["series"][ent]["EIS"], marker="o", label=f"{ent} EIS")
    for ent in sorted(trends["series"]):
        ax.plot(x, trends["series"][ent]["CAS"], marker="x", linestyle="--",
                label=f"{ent} CAS")
    ax.set_xticks(list(x))
    ax.set_xticklabels(w)
    ax.set_ylim(0, 105)
    ax.set_title("EIS (solid) / CAS (dashed) across submission windows")
    ax.legend(fontsize=7, ncol=2)
    return _png(fig)


def shap_panel(explanations: dict | None) -> str:
    if not explanations or not explanations.get("drivers"):
        return ""
    m = explanations.get("model", {})
    items = []
    for aid, d in list(explanations["drivers"].items())[:10]:
        drv = ", ".join(f"{t['feature']} {t['shap']:+.2f}"
                        for t in d["top_drivers"])
        items.append(f"<li><code>{aid}</code> ({d['entity_id']}, "
                     f"p={d['p_violation']}) → {drv}</li>")
    return (f"<div class='card'><h2>Why flagged — model drivers (XGBoost+SHAP, "
            f"AUC {m.get('auc_train')}; rules detect, model explains)</h2>"
            f"<ul>{''.join(items)}</ul></div>")


def sector_panel(sector: list | None) -> str:
    if not sector:
        return ""
    items = "".join(
        f"<li><b>[{f['rule_id']}]</b> {f['title']}<br>"
        f"<span class='ev'>{f['evidence']}</span></li>" for f in sector)
    return (f"<div class='card'><h2>Sector dark spots (X2 — portfolio level, "
            f"no single-entity audit could surface these)</h2><ul>{items}</ul></div>")


def build_dashboard_html(scores, flags, signals, metrics, ledger_tail,
                         trends=None, explanations=None, sector=None) -> str:
    if metrics is None:
        metrics = {"precision": "n/a", "recall": "n/a", "ranked": sorted(scores),
                   "tool_top3": [], "manual_top3": [], "top3_overlap": "n/a",
                   "pattern_checks": {}}  # uploaded assessment, no ground truth
    rows = []
    for ent in sorted(scores):
        s = scores[ent]
        fl = flags.get(ent, [])
        flaglis = "".join(
            f"<li><b>[{f['rule_id']}]</b> {f['title']} "
            f"<i>({f['severity']})</i><br><span class='ev'>{f['evidence']}</span><br>"
            f"<span class='rec'>observed: {f['observed']} · expected: {f['expected']} · "
            f"records: {f['n_records']}</span></li>" for f in fl) or "<li>— no flags —</li>"
        rows.append(
            f"<section class='card'><h2>{ent} — {s['band']} "
            f"<span class=' pill'>EIS {s['EIS']} · CAS {s['CAS']} · Prio {s['priority']}</span></h2>"
            f"<ul>{flaglis}</ul></section>")
    ledgerlis = "".join(
        f"<li>#{r['seq']} <b>{r['event']}</b> <code>{r['hash'][:12]}</code> "
        f"<span class='rec'>{r['ts']}</span></li>" for r in ledger_tail[-8:])
    checks = "".join(
        f"<li>{e}: expects <b>{v['expected']}</b> → "
        f"{'✅ PASS' if v['pass'] else '❌ FAIL'} "
        f"<span class='rec'>fired: {', '.join(v['fired']) or '—'}</span></li>"
        for e, v in metrics["pattern_checks"].items())
    return f"""<!DOCTYPE html><html><head><meta charset='utf-8'>
<title>SAT-SA Supervisor Dashboard (prototype v0)</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;background:#0b0e14;color:#e6e6e6;margin:0}}
header{{background:#11161f;padding:18px 28px;border-bottom:2px solid #2b6cb0}}
h1{{margin:0;font-size:22px}}h2{{font-size:17px}}.sub{{color:#9fb3c8}}
main{{padding:20px 28px;max-width:1100px;margin:auto}}
.card{{background:#151b26;border:1px solid #2a3344;border-radius:10px;padding:14px 18px;margin:14px 0}}
.pill{{background:#2b6cb0;border-radius:20px;padding:2px 12px;font-size:13px}}
.ev{{color:#c8d6e5}}.rec{{color:#8fa3b8;font-size:12px}}code{{color:#9ae6b4}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}img{{width:100%;background:#fff;border-radius:8px}}
ul{{line-height:1.55}}.ok{{color:#9ae6b4}}.bad{{color:#feb2b2}}
footer{{color:#8fa3b8;padding:20px 28px;text-align:center;font-size:12px}}</style></head>
<body><header><h1>SAT-SA · Supervisory Analytics — prototype v0</h1>
<div class='sub'>Dual scores: <b>EIS</b> (is investigation real?) + <b>CAS</b> (what's missing?) ·
precision {metrics['precision']} · recall {metrics['recall']} · top-3 overlap {metrics['top3_overlap']} ·
ranking: {' → '.join(metrics['ranked'])}</div></header><main>
<div class='grid'><div class='card'><img src='data:image/png;base64,{scatter_chart(scores)}'></div>
<div class='card'><img src='data:image/png;base64,{bars_chart(scores)}'></div></div>
<div class='card'><img src='data:image/png;base64,{cliff_chart(signals)}'></div>
<div class='card'><img src='data:image/png;base64,{trend_chart(trends)}'></div>
{shap_panel(explanations)}
{sector_panel(sector)}
<div class='card'><h2>Validation vs ground truth (stand-in for manual review)</h2><ul>{checks}</ul>
<div>precision <b>{metrics['precision']}</b> · recall <b>{metrics['recall']}</b> ·
tool top-3: <b>{', '.join(metrics['tool_top3'])}</b> · manual top-3: <b>{', '.join(metrics['manual_top3'])}</b></div></div>
{''.join(rows)}
<div class='card'><h2>Audit ledger (hash-chained, tamper-evident)</h2><ul>{ledgerlis}</ul></div>
</main><footer>SAT-SA prototype · every flag ships with rule_id + evidence · no cloud · no external AI ·
<a style='color:#9fb3c8' href='/api/validate'>/api/validate</a> · <a style='color:#9fb3c8' href='/api/entities'>/api/entities</a></footer></body></html>"""
