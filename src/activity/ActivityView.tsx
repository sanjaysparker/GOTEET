import React, { useMemo, useState } from 'react';
import {
  AlertTriangle,
  Bot,
  CircleAlert,
  Clock,
  Eye,
  GitBranch,
  Info,
  Link2,
  Loader2,
  Plus,
  RefreshCw,
  Shield,
  Terminal,
  Trash2,
  X,
} from 'lucide-react';
import { api, ago, shortDate, type Row } from '../lib/api';
import { hueOf } from '../work/bits';

/* Activity: what is actually being worked on, observed from the machine rather than typed in.
   Sources are the local Claude Code and Codex session logs, running agent processes and git history.
   Only counts and project names are kept: never prompts, commands, file names or outputs. Time is an estimate
   from session activity (gaps over 5 minutes are idle) and says so on screen. */

type Props = {
  data: Row | null;
  busy: boolean;
  owner: boolean;
  scan: () => void;
  enable: (on: boolean) => void;
  reload: () => void;
  createTask: (seed: Row) => void;
  openProject: (name: string) => void;
  fail: (e: unknown) => void;
  notify: (t: string) => void;
};

const SEV = { critical: CircleAlert, warn: AlertTriangle, info: Info } as const;
const color = (name: string) => `oklch(0.74 0.09 ${hueOf(name)})`;
const hours = (m: number) => (m >= 90 ? (m / 60).toFixed(1) + ' h' : Math.round(m) + ' min');

export function ActivityView(p: Props) {
  const d = p.data;
  const [mapOpen, setMapOpen] = useState(false);
  const [map, setMap] = useState<Row[]>([]);
  const [sev, setSev] = useState('all');
  // HOOKS FIRST: every hook must run on every render, before any early return, or enabling the observer crashes React.
  const projectsAll: Row[] = d?.projects || [];
  const correlationsAll: Row[] = d?.correlations || [];
  const heat = useMemo(() => {
    const top = projectsAll.slice(0, 7).map((x) => x.name);
    const get = (a: string, b: string) =>
      correlationsAll.find((c) => (c.a === a && c.b === b) || (c.a === b && c.b === a));
    return { top, get };
  }, [projectsAll, correlationsAll]);

  if (!d)
    return (
      <div className="ac-skeleton" aria-busy="true">
        <div className="sk-line" />
        <div className="sk-line short" />
      </div>
    );

  if (!d.enabled)
    return (
      <section className="ac-onboard ticks">
        <Eye size={22} />
        <h2 className="moment">Let GOTEET see the work you are already doing.</h2>
        <p>
          GOTEET can read your local Claude Code and Codex session logs, notice running agents and read git
          history, so projects, time, mistakes and links between projects appear without typing anything in.
        </p>
        <div className="ac-promise">
          <div>
            <Shield size={14} />
            <b>Kept</b>
            <span>project names, minutes, counts of turns, tool calls, errors, commits</span>
          </div>
          <div>
            <X size={14} />
            <b>Never kept</b>
            <span>prompts, replies, commands, file names, paths, tokens or outputs</span>
          </div>
          <div>
            <Eye size={14} />
            <b>Read-only</b>
            <span>logs and repositories are never modified. Delete everything any time.</span>
          </div>
        </div>
        {p.owner && (
          <button className="primary" onClick={() => p.enable(true)}>
            <Eye size={14} />
            Turn on activity observer
          </button>
        )}
        <p className="faint small">{d.coverage}</p>
      </section>
    );

  const projects: Row[] = d.projects || [];
  const days: Row[] = d.daily || [];
  const maxDay = Math.max(...days.map((x) => x.total), 1);
  const names = projects.map((x) => x.name);
  const mistakes: Row[] = (d.mistakes || []).filter((m: Row) => sev === 'all' || m.severity === sev);
  const correlations: Row[] = d.correlations || [];

  async function openMap() {
    try {
      setMap(await api('/api/activity/map'));
      setMapOpen(true);
    } catch (e) {
      p.fail(e);
    }
  }
  async function saveMap(next: Row[]) {
    try {
      await api(
        '/api/activity/map',
        next.filter((m) => m.pattern?.trim() && m.project?.trim()),
      );
      p.notify('Project mapping saved');
      p.scan();
    } catch (e) {
      p.fail(e);
    }
  }
  async function wipe() {
    if (!confirm('Delete all observed activity data? Logs and repositories are not touched.')) return;
    try {
      await window.goteet.request('DELETE', '/api/activity/data');
      p.reload();
      p.notify('Activity data deleted');
    } catch (e) {
      p.fail(e);
    }
  }

  return (
    <div className="ac">
      <section className="ac-hero ticks">
        <div className="grow">
          <span className="micro-label">
            <Eye size={12} /> Observed ·{' '}
            {d.captured_at
              ? `read ${ago(d.captured_at) === 'now' ? 'just now' : ago(d.captured_at) + ' ago'}`
              : 'not read yet'}
          </span>
          <h2 className="moment">
            {d.totals?.minutes
              ? `${hours(d.totals.minutes)} of agent work across ${d.totals.projects} projects.`
              : 'No agent activity found yet.'}
          </h2>
          <p className="faint small">
            {d.totals?.sessions || 0} sessions · {d.totals?.commits || 0} commits · minutes are estimates from
            session activity
          </p>
        </div>
        <div className="ac-hero-actions">
          <button className="primary" disabled={p.busy} onClick={p.scan}>
            {p.busy ? <Loader2 size={14} className="spin" /> : <RefreshCw size={14} />}
            {p.busy ? 'Reading…' : 'Scan now'}
          </button>
          <button className="sm" onClick={openMap}>
            <Link2 size={12} />
            Project mapping
          </button>
          {p.owner && (
            <button className="ghost danger-ghost sm" onClick={wipe}>
              <Trash2 size={12} />
              Delete data
            </button>
          )}
          <button className="ghost sm" onClick={() => p.enable(false)}>
            Turn off
          </button>
        </div>
      </section>

      {mapOpen && (
        <MapEditor
          rows={map}
          setRows={setMap}
          projects={names}
          close={() => setMapOpen(false)}
          save={(r) => saveMap(r).then(() => setMapOpen(false))}
        />
      )}

      {d.errors?.length > 0 && (
        <div className="inline-note">
          <b>Coverage:</b> {d.errors.join(' · ')}
        </div>
      )}

      <div className="ac-grid">
        <div className="ac-main">
          <section className="ac-card">
            <div className="section-title">
              <h2>Working now</h2>
              <span>{(d.now || []).length} running</span>
            </div>
            {(d.now || []).length ? (
              (d.now as Row[]).map((n) => (
                <div key={n.pid} className="ac-now">
                  <span className="ac-live" aria-label="running" />
                  <span className={'ac-tool ' + n.tool}>{n.tool}</span>
                  <span className="grow">{n.project || 'unmapped'}</span>
                  <span className="num faint">{ago(n.started)}</span>
                </div>
              ))
            ) : (
              <p className="faint">No agent processes are running right now.</p>
            )}
          </section>

          <section className="ac-card">
            <div className="section-title">
              <h2>Time by project</h2>
              <span>last {days.length} days · agent minutes</span>
            </div>
            <div className="ac-bars" role="img" aria-label="Agent minutes per day, stacked by project">
              {days.map((day) => (
                <div key={day.date} className="ac-day" title={`${day.date} · ${hours(day.total)}`}>
                  <div className="ac-stack" style={{ height: (day.total / maxDay) * 100 + '%' }}>
                    {Object.entries(day.projects as Record<string, number>)
                      .sort((a, b) => b[1] - a[1])
                      .map(([n, m]) => (
                        <i
                          key={n}
                          style={{ flexGrow: m, background: color(n) }}
                          title={`${n}: ${hours(m)}`}
                        />
                      ))}
                  </div>
                  <span className="num">{day.date.slice(8)}</span>
                </div>
              ))}
            </div>
            <div className="ac-legend">
              {projects.slice(0, 8).map((x) => (
                <span key={x.name}>
                  <i style={{ background: color(x.name) }} />
                  {x.name}
                </span>
              ))}
            </div>
          </section>

          <section className="ac-card">
            <div className="section-title">
              <h2>Projects</h2>
              <span>time, sessions, commits</span>
            </div>
            <div className="ac-table">
              {projects.map((x) => {
                const claude = x.tools?.claude || 0,
                  codex = x.tools?.codex || 0,
                  total = claude + codex || 1;
                return (
                  <button key={x.name} className="ac-proj" onClick={() => p.openProject(x.name)}>
                    <span className="ac-dot" style={{ background: color(x.name) }} />
                    <span className="grow ac-name">{x.name}</span>
                    <span className="ac-split" title={`Claude ${hours(claude)} · Codex ${hours(codex)}`}>
                      <i className="claude" style={{ width: (claude / total) * 100 + '%' }} />
                      <i className="codex" style={{ width: (codex / total) * 100 + '%' }} />
                    </span>
                    <span className="num ac-min">{hours(x.minutes)}</span>
                    <span className="num faint ac-cnt">{x.sessions} sess</span>
                    <span className="num faint ac-cnt">
                      <GitBranch size={11} /> {x.commits}
                    </span>
                    <span className="num faint ac-cnt">{x.last_active ? ago(x.last_active) : ''}</span>
                  </button>
                );
              })}
              {!projects.length && <p className="faint">Nothing to attribute yet.</p>}
            </div>
            <p className="faint small">
              <span className="ac-key claude" /> Claude <span className="ac-key codex" /> Codex. Git time is
              an estimate and is not added to agent minutes.
            </p>
          </section>

          <section className="ac-card">
            <div className="section-title">
              <h2>Recent sessions</h2>
              <span>{(d.sessions || []).length} shown</span>
            </div>
            {(d.sessions as Row[] | undefined)?.map((s) => (
              <div key={s.id} className="ac-sess">
                <span className={'ac-tool ' + s.tool}>{s.tool}</span>
                <span className="grow">
                  {s.project}
                  {s.title ? <small> · {s.title}</small> : null}
                </span>
                <span className="num faint">{shortDate(s.started)}</span>
                <span className="num">{hours(s.active_minutes)}</span>
                <span className="num faint">{s.turns} turns</span>
                <span className="num faint">{s.tool_calls} tools</span>
                <span
                  className={
                    'num ' + (s.tool_calls >= 10 && s.tool_errors / s.tool_calls >= 0.3 ? 'ac-bad' : 'faint')
                  }
                >
                  {s.tool_errors} err
                </span>
                {s.state === 'active' && <span className="ac-live" aria-label="active" />}
              </div>
            ))}
          </section>
        </div>

        <aside className="ac-side">
          <section className="ac-card">
            <div className="section-title">
              <h2>Mistakes & rework</h2>
              <span>{(d.mistakes || []).length}</span>
            </div>
            <div className="wk-seg" role="group" aria-label="Severity">
              {['all', 'critical', 'warn', 'info'].map((k) => (
                <button key={k} aria-pressed={sev === k} onClick={() => setSev(k)}>
                  {k}
                </button>
              ))}
            </div>
            {mistakes.map((m) => {
              const Icon = SEV[m.severity as keyof typeof SEV] || Info;
              return (
                <article key={m.id} className={'ai-finding ' + m.severity}>
                  <Icon size={15} aria-label={m.severity} />
                  <div className="grow">
                    <strong>{m.title}</strong>
                    <p>{m.detail}</p>
                    {m.evidence?.length > 0 && <p className="faint small">{m.evidence.join(' · ')}</p>}
                    {m.suggestion && <p className="ai-suggest">→ {m.suggestion}</p>}
                  </div>
                </article>
              );
            })}
            {!mistakes.length && <p className="faint">No patterns worth flagging.</p>}
          </section>

          <section className="ac-card">
            <div className="section-title">
              <h2>Suggested changes</h2>
              <span>review-first</span>
            </div>
            {(d.suggestions as Row[] | undefined)?.map((s) => (
              <div key={s.id} className="ac-sug">
                <div className="grow">
                  <strong>{s.title}</strong>
                  <p>{s.detail}</p>
                  <p className="faint small">{s.reason}</p>
                </div>
                {p.owner && s.project && (
                  <button
                    className="sm"
                    onClick={() =>
                      p.createTask({ title: s.title, project: s.project, description: s.detail })
                    }
                  >
                    <Plus size={12} />
                    Task
                  </button>
                )}
              </div>
            ))}
            {!(d.suggestions || []).length && <p className="faint">Nothing to change right now.</p>}
          </section>

          <section className="ac-card">
            <div className="section-title">
              <h2>Project correlation</h2>
              <span>work that moves together</span>
            </div>
            {heat.top.length > 1 && (
              <div
                className="ac-heat"
                style={{ gridTemplateColumns: `72px repeat(${heat.top.length}, 1fr)` }}
              >
                <span />
                {heat.top.map((n) => (
                  <span key={n} className="ac-heat-h" title={n}>
                    {n.slice(0, 4)}
                  </span>
                ))}
                {heat.top.map((a) => (
                  <React.Fragment key={a}>
                    <span className="ac-heat-l" title={a}>
                      {a}
                    </span>
                    {heat.top.map((b) => {
                      const c = a === b ? null : heat.get(a, b);
                      return (
                        <i
                          key={b}
                          className="ac-cell"
                          style={{
                            opacity: a === b ? 0.15 : 0.12 + (c?.score || 0) * 0.88,
                            background: a === b ? 'var(--text-faint)' : 'var(--accent)',
                          }}
                          title={
                            c
                              ? `${a} ↔ ${b}: ${c.score.toFixed(2)} · ${c.evidence}`
                              : `${a} ↔ ${b}: no link`
                          }
                        />
                      );
                    })}
                  </React.Fragment>
                ))}
              </div>
            )}
            {correlations.slice(0, 6).map((c) => (
              <div key={c.a + c.b} className="ac-corr">
                <div className="grow">
                  <strong>
                    {c.a} <span className="faint">↔</span> {c.b}
                  </strong>
                  <p className="faint small">{c.evidence}</p>
                </div>
                <span className="num">{Math.round(c.score * 100)}</span>
              </div>
            ))}
            {!correlations.length && (
              <p className="faint">Not enough shared activity to compare projects yet.</p>
            )}
          </section>
        </aside>
      </div>

      <p className="faint small ac-foot">
        <Clock size={11} /> {d.coverage} <Terminal size={11} /> <Bot size={11} /> Observed locally; nothing
        leaves this computer except what you send to your selected AI when you run an analysis, and that brief
        contains project names and counts only.
      </p>
    </div>
  );
}

function MapEditor({
  rows,
  setRows,
  projects,
  close,
  save,
}: {
  rows: Row[];
  setRows: (r: Row[]) => void;
  projects: string[];
  close: () => void;
  save: (r: Row[]) => void;
}) {
  return (
    <form
      className="gl-editor"
      onSubmit={(e) => {
        e.preventDefault();
        save(rows);
      }}
    >
      <header>
        <h3 className="moment">Project mapping</h3>
        <button type="button" className="ghost" onClick={close} aria-label="Close">
          <X size={15} />
        </button>
      </header>
      <p className="faint small">
        Folders are matched to projects by name automatically. Add a rule here when a folder belongs to a
        different project.
      </p>
      {rows.map((r, i) => (
        <div key={i} className="form-row">
          <input
            aria-label="Folder contains"
            placeholder="Folder contains, e.g. aigis-droneo"
            value={r.pattern || ''}
            onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, pattern: e.target.value } : x)))}
          />
          <input
            aria-label="Project"
            list="ac-projects"
            placeholder="Project"
            value={r.project || ''}
            onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, project: e.target.value } : x)))}
          />
          <button
            type="button"
            className="ghost"
            aria-label="Remove rule"
            onClick={() => setRows(rows.filter((_, j) => j !== i))}
          >
            <Trash2 size={13} />
          </button>
        </div>
      ))}
      <datalist id="ac-projects">
        {projects.map((n) => (
          <option key={n} value={n} />
        ))}
      </datalist>
      <button type="button" className="sm" onClick={() => setRows([...rows, { pattern: '', project: '' }])}>
        <Plus size={12} />
        Add rule
      </button>
      <div className="dialog-actions">
        <button type="button" onClick={close}>
          Cancel
        </button>
        <button className="primary">Save and rescan</button>
      </div>
    </form>
  );
}
