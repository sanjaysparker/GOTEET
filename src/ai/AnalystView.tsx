import React, { useState } from 'react';
import { AlertTriangle, ArrowUpRight, Bot, CircleAlert, Info, Loader2, Play, Sparkles } from 'lucide-react';
import { ago, date, shortDate, type Row } from '../lib/api';
import { Avatar, Meter } from '../work/bits';

export type AnalystActions = {
  run: (focus?: string) => void;
  running: boolean;
  openTask: (id: string) => void;
  openProject: (id: string) => void;
  external: (url: string) => void;
  track: (finding: Row) => void;
  showPlan: () => void;
  providerLabel: string;
};

const SEV_ICON = { critical: CircleAlert, warn: AlertTriangle, info: Info } as const;
const HEALTH_TONE: Record<string, string> = {
  'On track': 'var(--ok)',
  'At risk': 'var(--warn)',
  'Off track': 'var(--critical)',
  Done: 'var(--ok)',
  'No plan': 'var(--text-faint)',
};

export function Score({ value }: { value: number }) {
  const tone = value >= 80 ? 'var(--ok)' : value >= 55 ? 'var(--warn)' : 'var(--critical)';
  return (
    <div className="ai-score" style={{ ['--tone' as string]: tone }}>
      <svg viewBox="0 0 64 64" aria-hidden="true">
        <circle cx="32" cy="32" r="27" fill="none" stroke="var(--surface-3)" strokeWidth="5" />
        <circle
          cx="32"
          cy="32"
          r="27"
          fill="none"
          stroke={tone}
          strokeWidth="5"
          strokeDasharray={`${(value / 100) * 169.6} 170`}
          transform="rotate(-90 32 32)"
        />
      </svg>
      <span className="num">{value}</span>
    </div>
  );
}

export function FindingRow({ f, a }: { f: Row; a: AnalystActions }) {
  const Icon = SEV_ICON[f.severity as keyof typeof SEV_ICON] || Info;
  return (
    <article className={'ai-finding ' + f.severity}>
      <Icon size={15} aria-label={f.severity} />
      <div className="grow">
        <strong>{f.title}</strong>
        {f.detail && <p>{f.detail}</p>}
        {f.suggestion && <p className="ai-suggest">→ {f.suggestion}</p>}
      </div>
      <div className="ai-evidence">
        {f.evidence?.map((e: Row) =>
          e.type === 'task' ? (
            <button key={e.id} className="sm" onClick={() => a.openTask(e.id)}>
              Open task
            </button>
          ) : e.type === 'project' ? (
            <button key={e.id} className="sm" onClick={() => a.openProject(e.id)}>
              Open project
            </button>
          ) : e.type === 'followup' ? (
            <button key={e.id} className="sm" onClick={() => a.track(f)}>
              Track as task
            </button>
          ) : e.url ? (
            <button key={e.id} className="sm" onClick={() => a.external(e.url)}>
              Evidence <ArrowUpRight size={12} />
            </button>
          ) : null,
        )}
      </div>
    </article>
  );
}

/** Compact agent brief for Today: verdict, score, top risks, one-click deep analysis. */
export function AgentBrief({
  insights,
  latest,
  a,
}: {
  insights: Row | null;
  latest: Row | null;
  a: AnalystActions;
}) {
  if (!insights)
    return (
      <section className="ai-brief skeleton" aria-busy="true">
        <div className="sk-line" />
        <div className="sk-line short" />
      </section>
    );
  const top = insights.findings.slice(0, 4);
  return (
    <section className="ai-brief ticks" aria-label="Agent brief">
      <header>
        <Score value={insights.score} />
        <div className="grow">
          <span className="micro-label">
            <Bot size={12} /> Agent brief · analysed{' '}
            {ago(insights.generated_at) === 'now' ? 'just now' : ago(insights.generated_at) + ' ago'}
          </span>
          <h2 className="moment">
            {insights.counts.critical
              ? `${insights.counts.critical} critical, ${insights.counts.warn} to watch.`
              : insights.counts.warn
                ? `${insights.counts.warn} things need a decision.`
                : 'Clear runway. Nothing urgent.'}
          </h2>
          <p>
            {insights.totals.open} open · {insights.totals.blocked} blocked · {insights.projects.length}{' '}
            projects · sources:{' '}
            {insights.sources
              .map((s: Row) => `${s.name} ${s.mode === 'live' ? 'live' : shortDate(s.captured_at)}`)
              .join(', ')}
          </p>
        </div>
        <div className="ai-actions">
          <button className="primary" disabled={a.running} onClick={() => a.run()}>
            {a.running ? <Loader2 size={14} className="spin" /> : <Sparkles size={14} />}
            {a.running ? 'Analysing…' : 'Deep analysis'}
          </button>
          <small>{a.providerLabel}</small>
        </div>
      </header>
      {latest && (
        <div className="ai-report">
          <span className="micro-label">
            Latest AI report · {latest.provider} · {date(latest.created_at)}
          </span>
          <p>{latest.summary}</p>
          <button className="text-link" onClick={a.showPlan}>
            Review proposed changes <ArrowUpRight size={12} />
          </button>
        </div>
      )}
      <div className="ai-findings">
        {top.length ? (
          top.map((f: Row) => <FindingRow key={f.id} f={f} a={a} />)
        ) : (
          <p className="faint">No findings from current records.</p>
        )}
      </div>
    </section>
  );
}

/** Full analyst workspace: findings, project health, workload, history. */
export function AnalystView({
  insights,
  history,
  a,
}: {
  insights: Row | null;
  history: Row[];
  a: AnalystActions;
}) {
  const [focus, setFocus] = useState('');
  const [sev, setSev] = useState('all');
  if (!insights) return <AgentBrief insights={null} latest={null} a={a} />;
  const shown = insights.findings.filter((f: Row) => sev === 'all' || f.severity === sev);
  return (
    <div className="ai-view">
      <section className="ai-hero ticks">
        <Score value={insights.score} />
        <div className="grow">
          <span className="micro-label">Workspace health</span>
          <div className="ai-counts">
            {(['critical', 'warn', 'info'] as const).map((k) => (
              <button
                key={k}
                className={'ai-count ' + k}
                aria-pressed={sev === k}
                onClick={() => setSev(sev === k ? 'all' : k)}
              >
                <span className="num">{insights.counts[k]}</span>
                {k === 'warn' ? 'watch' : k}
              </button>
            ))}
          </div>
        </div>
        <form
          className="ai-run"
          onSubmit={(e) => {
            e.preventDefault();
            a.run(focus);
          }}
        >
          <input
            value={focus}
            onChange={(e) => setFocus(e.target.value)}
            placeholder="Optional focus, e.g. “AIGIS release risk”"
            aria-label="Analysis focus"
          />
          <button className="primary" disabled={a.running}>
            {a.running ? <Loader2 size={14} className="spin" /> : <Play size={14} />}
            {a.running ? 'Analysing…' : 'Run AI analysis'}
          </button>
          <small>{a.providerLabel} · proposes, never applies</small>
        </form>
      </section>
      <div className="ai-grid">
        <section>
          <div className="section-title">
            <h2>Findings</h2>
            <span>{shown.length} shown</span>
          </div>
          {shown.length ? (
            shown.map((f: Row) => <FindingRow key={f.id} f={f} a={a} />)
          ) : (
            <p className="faint">Nothing at this level.</p>
          )}
          <p className="faint small ai-method">{insights.method}</p>
        </section>
        <div className="ai-side">
          <section>
            <div className="section-title">
              <h2>Project health</h2>
              <span>progress vs schedule</span>
            </div>
            {insights.projects.length ? (
              insights.projects.map((p: Row) => (
                <button key={p.id} className="ai-proj" onClick={() => a.openProject(p.id)}>
                  <span className="ai-proj-name">{p.name}</span>
                  <span
                    className="wk-chip"
                    style={{ color: HEALTH_TONE[p.health], borderColor: HEALTH_TONE[p.health] }}
                  >
                    {p.health}
                  </span>
                  <Meter value={p.progress} tone={HEALTH_TONE[p.health]} />
                  <span className="num faint">
                    {p.done}/{p.done + p.open}
                    {p.elapsed != null ? ` · ${Math.round(p.elapsed * 100)}% time` : ''}
                  </span>
                </button>
              ))
            ) : (
              <p className="faint">No projects saved.</p>
            )}
          </section>
          <section>
            <div className="section-title">
              <h2>Workload</h2>
              <span>open items, not effort</span>
            </div>
            {insights.workload.map((w: Row) => (
              <div key={w.owner} className="ai-load">
                <Avatar name={w.owner} />
                <span className="grow">{w.owner}</span>
                <Meter value={w.open / Math.max(...insights.workload.map((x: Row) => x.open), 1)} />
                <span className="num">{w.open}</span>
                {w.blocked > 0 && (
                  <span className="num" style={{ color: 'var(--critical)' }}>
                    {w.blocked} blk
                  </span>
                )}
              </div>
            ))}
          </section>
          <section>
            <div className="section-title">
              <h2>AI reports</h2>
              <span>{history.length}</span>
            </div>
            {history.length ? (
              history.map((h) => (
                <div key={h.id} className="ai-hist">
                  <span className="num faint">{shortDate(h.created_at)}</span>
                  <span className="num">{h.score}</span>
                  <p>{h.summary}</p>
                </div>
              ))
            ) : (
              <p className="faint">Run an analysis to start a history.</p>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
