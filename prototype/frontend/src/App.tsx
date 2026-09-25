import { useCallback, useEffect, useState } from 'react';
import { getEntities, getTrends, getValidate } from './api';
import type { EntitySummary, ValidateResponse, View } from './types';
import TriageView from './views/TriageView';
import EntityView from './views/EntityView';
import TrendsView from './views/TrendsView';
import AuditView from './views/AuditView';
import ValidateView from './views/ValidateView';
import UploadView from './views/UploadView';

function UtcClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  const p = (n: number) => String(n).padStart(2, '0');
  return (
    <span className="clock">
      {`${now.getUTCFullYear()}-${p(now.getUTCMonth() + 1)}-${p(now.getUTCDate())} ${p(now.getUTCHours())}:${p(now.getUTCMinutes())}:${p(now.getUTCSeconds())}Z`}
    </span>
  );
}

export default function App() {
  const [view, setView] = useState<View>('triage');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [entities, setEntities] = useState<EntitySummary[]>([]);
  const [entitiesError, setEntitiesError] = useState<string | null>(null);
  const [validate, setValidate] = useState<ValidateResponse | null>(null);
  const [validateError, setValidateError] = useState<string | null>(null);
  const [trendsAvailable, setTrendsAvailable] = useState<boolean | null>(null);

  useEffect(() => {
    let alive = true;
    loadAll(alive);
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function loadAll(alive = true) {
    setEntitiesError(null);
    setValidateError(null);
    getEntities()
      .then((d) => {
        if (alive) setEntities(d.entities ?? []);
      })
      .catch((e) => {
        if (alive)
          setEntitiesError(
            e instanceof Error ? e.message : 'Failed to load entities',
          );
      });
    getValidate()
      .then((d) => {
        if (alive) setValidate(d);
      })
      .catch((e) => {
        if (alive)
          setValidateError(
            e instanceof Error ? e.message : 'Failed to load validation',
          );
      });
    // Probe /api/trends once: hide the Trends tab gracefully on 404.
    getTrends()
      .then((t) => {
        if (alive) setTrendsAvailable(t !== null);
      })
      .catch(() => {
        if (alive) setTrendsAvailable(false);
      });
  }

  const afterUpload = useCallback(() => {
    setSelectedId(null);
    loadAll(true);
    setView('triage');
  }, []);

  const openEntity = useCallback((id: string) => {
    setSelectedId(id);
    setView('entity');
  }, []);

  const goTriage = useCallback(() => setView('triage'), []);

  return (
    <div className="app-shell">
      <header className="topbar">
        <h1>
          SAT-SA <span className="amber">//</span> SUPERVISORY CONSOLE
        </h1>
        <span className="sub">NCIIPC · AIR-GAPPED · READ-ONLY</span>
        <UtcClock />
        <span className="sys-tag">LOCAL // OFFLINE-SAFE</span>
        <div className="chips">
          {validate ? (
            <>
              <span className="chip ok">
                PREC{' '}
                <b>
                  {validate.precision == null
                    ? '—'
                    : Number(validate.precision).toFixed(2)}
                </b>
              </span>
              <span className="chip ok">
                REC{' '}
                <b>
                  {validate.recall == null
                    ? '—'
                    : Number(validate.recall).toFixed(2)}
                </b>
              </span>
              <span className="chip">
                TOP-3 <b>{validate.top3_overlap ?? '—'}</b>
              </span>
            </>
          ) : validateError ? (
            <span className="chip warn">VALIDATION UNAVAILABLE</span>
          ) : (
            <span className="chip">LOADING VALIDATION…</span>
          )}
        </div>
      </header>

      <nav className="nav">
        <button
          className={view === 'triage' ? 'active' : ''}
          onClick={() => setView('triage')}
        >
          Triage
        </button>
        <button
          className={view === 'entity' ? 'active' : ''}
          onClick={() => selectedId && setView('entity')}
          disabled={!selectedId}
          title={selectedId ? `Entity ${selectedId}` : 'Select an entity first'}
        >
          Entity{selectedId ? ` · ${selectedId}` : ''}
        </button>
        {trendsAvailable !== false && (
          <button
            className={view === 'trends' ? 'active' : ''}
            onClick={() => setView('trends')}
          >
            Trends
          </button>
        )}
        <button
          className={view === 'audit' ? 'active' : ''}
          onClick={() => setView('audit')}
        >
          Audit
        </button>
        <button
          className={view === 'validate' ? 'active' : ''}
          onClick={() => setView('validate')}
        >
          Validate
        </button>
        <button
          className={view === 'upload' ? 'active' : ''}
          onClick={() => setView('upload')}
        >
          Upload
        </button>
      </nav>

      {entitiesError && <div className="err">{entitiesError}</div>}

      {view === 'triage' && (
        <TriageView
          entities={entities}
          selectedId={selectedId}
          onSelect={openEntity}
        />
      )}
      {view === 'entity' && selectedId && (
        <EntityView entityId={selectedId} onBack={goTriage} />
      )}
      {view === 'entity' && !selectedId && (
        <div className="card muted">Select an entity from Triage first.</div>
      )}
      {view === 'trends' && <TrendsView key="trends" />}
      {view === 'audit' && <AuditView key="audit" />}
      {view === 'validate' && <ValidateView key="validate" />}
      {view === 'upload' && <UploadView key="upload" onDone={afterUpload} />}

      <div className="footer">
        SAT-SA · SUPERVISORY CONSOLE v0.3 · SAME-ORIGIN /API · NO EXTERNAL
        CALLS · RULES DETECT / MODELS EXPLAIN
      </div>
    </div>
  );
}
