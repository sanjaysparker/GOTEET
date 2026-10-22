import React, { useMemo, useState } from 'react';
import {
  ArrowUpRight,
  Check,
  CheckCircle2,
  Flag,
  FolderKanban,
  ListTodo,
  Milestone as MilestoneIcon,
  Pencil,
  Plus,
  Sparkles,
  Target,
  Trash2,
  X,
} from 'lucide-react';
import { api, remove, date, shortDate, todayISO, type Row } from '../lib/api';
import { Avatar, Meter } from '../work/bits';
import { Score } from '../ai/AnalystView';

/* Goals, plans and deadlines.
   A goal is a measurable outcome with a date. Progress is computed, never typed in for task-based key results:
   it comes from the saved tasks of the linked project. The time marker on each bar shows how much of the
   schedule has elapsed, so a goal that is behind is visible without reading a number. */

type Props = {
  goals: Row[];
  deadlines: Row | null;
  projects: Row[];
  owner: boolean;
  reload: () => void;
  openTask: (id: string) => void;
  openProject: (id: string) => void;
  askAgent: (q: string) => void;
  fail: (e: unknown) => void;
  notify: (t: string) => void;
};

const TONE: Record<string, string> = {
  'On track': 'var(--ok)',
  'At risk': 'var(--warn)',
  'Off track': 'var(--critical)',
  Achieved: 'var(--ok)',
  'No plan': 'var(--text-faint)',
};
const pct = (n: number) => Math.round((n || 0) * 100);

type Edit = { kind: 'goal'; data: Row } | { kind: 'kr'; data: Row } | { kind: 'milestone'; data: Row } | null;

export function GoalsView(p: Props) {
  const [edit, setEdit] = useState<Edit>(null);
  const [focus, setFocus] = useState('');
  const [showAll, setShowAll] = useState(false);
  const active = p.goals.filter((g) => g.status === 'Active');
  const shown = showAll ? p.goals : active.length ? active : p.goals;
  const overall = active.length ? active.reduce((a, g) => a + g.progress, 0) / active.length : 0;
  const count = (h: string) => active.filter((g) => g.health === h).length;
  const nextDue = useMemo(() => {
    const items = [
      ...(p.deadlines?.overdue || []),
      ...(p.deadlines?.this_week || []),
      ...(p.deadlines?.later || []),
    ];
    return items[0] as Row | undefined;
  }, [p.deadlines]);

  async function save(path: string, body: Row, done = 'Saved') {
    try {
      await api(path, body);
      setEdit(null);
      p.reload();
      p.notify(done);
    } catch (e) {
      p.fail(e);
    }
  }
  async function drop(path: string, what: string) {
    if (!confirm(`Delete this ${what}?`)) return;
    try {
      await remove(path);
      p.reload();
    } catch (e) {
      p.fail(e);
    }
  }

  return (
    <div className="gl">
      <section className="gl-hero ticks" aria-label="Goal summary">
        <Score value={pct(overall)} />
        <div className="grow">
          <span className="micro-label">
            <Target size={12} /> {active.length} active goal{active.length === 1 ? '' : 's'}
          </span>
          <h2 className="moment">
            {!p.goals.length
              ? 'Set the outcomes that matter.'
              : count('Off track')
                ? `${count('Off track')} off track, ${count('At risk')} at risk.`
                : count('At risk')
                  ? `${count('At risk')} at risk. The rest on course.`
                  : `${pct(overall)}% there, on course.`}
          </h2>
          <div className="gl-health">
            {(['On track', 'At risk', 'Off track'] as const).map((h) => (
              <span key={h} className="gl-health-item">
                <i style={{ background: TONE[h] }} />
                <b className="num">{count(h)}</b>
                {h}
              </span>
            ))}
            {nextDue && (
              <span className="gl-health-item faint">
                Next: {nextDue.title} ·{' '}
                {nextDue.days < 0
                  ? `${-nextDue.days} d overdue`
                  : nextDue.days === 0
                    ? 'today'
                    : `in ${nextDue.days} d`}
              </span>
            )}
          </div>
        </div>
        <div className="gl-hero-actions">
          {p.owner && (
            <button
              className="primary"
              onClick={() => setEdit({ kind: 'goal', data: { status: 'Active', start_date: todayISO() } })}
            >
              <Plus size={14} />
              New goal
            </button>
          )}
          <button
            className="sm"
            onClick={() =>
              p.askAgent(
                'Review my projects, tasks and deadlines and suggest 3 measurable goals with key results and a target date each. Suggest only; do not create anything.',
              )
            }
          >
            <Sparkles size={13} />
            Ask agent for goals
          </button>
        </div>
      </section>

      {edit && (
        <Editor
          edit={edit}
          projects={p.projects}
          goals={p.goals}
          close={() => setEdit(null)}
          save={save}
          setEdit={setEdit}
        />
      )}

      <div className="gl-body">
        <div className="gl-cards">
          {p.goals.length > active.length && (
            <button className="text-link gl-toggle" onClick={() => setShowAll(!showAll)}>
              {showAll ? 'Show active only' : `Show all ${p.goals.length} goals`}
            </button>
          )}
          {!shown.length && (
            <div className="wk-empty">
              <h3 className="moment">A goal is an outcome with a date.</h3>
              <p>
                Add key results from your tasks, or measure something by hand. Progress and deadlines take
                care of themselves.
              </p>
            </div>
          )}
          {shown.map((g) => (
            <article key={g.id} className={'gl-card ' + (focus === g.id ? 'focus' : '')} id={'goal-' + g.id}>
              <header>
                <div className="grow">
                  <span className="gl-eyebrow">
                    <span className="gl-chip" style={{ color: TONE[g.health], borderColor: TONE[g.health] }}>
                      {g.health}
                    </span>
                    {g.status !== 'Active' && <span className="gl-chip">{g.status}</span>}
                    {g.owner && (
                      <span className="gl-owner">
                        <Avatar name={g.owner} size={16} />
                        {g.owner}
                      </span>
                    )}
                  </span>
                  <h3 className="moment">{g.title}</h3>
                  {g.description && <p>{g.description}</p>}
                </div>
                <div className="gl-big num">
                  {pct(g.progress)}
                  <small>%</small>
                </div>
              </header>

              <div
                className="gl-timebar"
                aria-label={`Progress ${pct(g.progress)}%${g.elapsed != null ? `, ${pct(g.elapsed)}% of time elapsed` : ''}`}
              >
                <span
                  className="gl-fill"
                  style={{ width: pct(g.progress) + '%', background: TONE[g.health] }}
                />
                {g.elapsed != null && (
                  <i className="gl-elapsed" style={{ left: pct(g.elapsed) + '%' }} title="Time elapsed" />
                )}
              </div>
              <div className="gl-dates num">
                <span>{g.start_date ? shortDate(g.start_date) : 'No start'}</span>
                <span>
                  {g.target_date
                    ? `${shortDate(g.target_date)} · ${g.days_left == null ? '' : g.days_left < 0 ? `${-g.days_left} d past` : `${g.days_left} d left`}`
                    : 'No deadline'}
                </span>
              </div>

              <div className="gl-krs">
                <div className="gl-sub">
                  <span className="micro-label">Key results</span>
                  {p.owner && (
                    <button
                      className="ghost sm"
                      onClick={() => setEdit({ kind: 'kr', data: { goal_id: g.id, kind: 'tasks' } })}
                    >
                      <Plus size={12} />
                      Add
                    </button>
                  )}
                </div>
                {g.key_results.map((k: Row) => (
                  <div key={k.id} className="gl-kr">
                    <span className="gl-kr-icon">
                      {k.kind === 'tasks' ? <ListTodo size={13} /> : <Flag size={13} />}
                    </span>
                    <div className="grow">
                      <div className="gl-kr-title">{k.title}</div>
                      <Meter value={k.progress} tone={k.progress >= 1 ? 'var(--ok)' : 'var(--accent)'} />
                    </div>
                    <span className="num gl-kr-detail">{k.detail}</span>
                    <span className="num gl-kr-pct">{pct(k.progress)}%</span>
                    {p.owner && (
                      <span className="gl-row-actions">
                        <button
                          className="ghost"
                          aria-label="Edit key result"
                          onClick={() => setEdit({ kind: 'kr', data: { ...k } })}
                        >
                          <Pencil size={12} />
                        </button>
                        <button
                          className="ghost"
                          aria-label="Delete key result"
                          onClick={() => drop('/api/key-results/' + k.id, 'key result')}
                        >
                          <Trash2 size={12} />
                        </button>
                      </span>
                    )}
                  </div>
                ))}
                {!g.key_results.length && (
                  <p className="faint small">No key results yet. Add one to measure progress.</p>
                )}
              </div>

              <div className="gl-ms">
                <div className="gl-sub">
                  <span className="micro-label">Plan · milestones</span>
                  {p.owner && (
                    <button
                      className="ghost sm"
                      onClick={() =>
                        setEdit({ kind: 'milestone', data: { goal_id: g.id, due: g.target_date || '' } })
                      }
                    >
                      <Plus size={12} />
                      Add
                    </button>
                  )}
                </div>
                {g.milestones.length > 0 && <MilestoneTrack goal={g} />}
                {g.milestones.map((m: Row) => {
                  const late = !m.done && m.due < todayISO();
                  return (
                    <div key={m.id} className={'gl-m ' + (m.done ? 'done' : '') + (late ? ' late' : '')}>
                      <button
                        className="gl-check"
                        aria-label={m.done ? 'Mark not done' : 'Mark done'}
                        aria-pressed={m.done}
                        disabled={!p.owner}
                        onClick={() =>
                          save(
                            '/api/milestones',
                            { id: m.id, done: !m.done },
                            m.done ? 'Milestone reopened' : 'Milestone done',
                          )
                        }
                      >
                        {m.done ? <Check size={12} /> : null}
                      </button>
                      <span className="grow">{m.title}</span>
                      <span className={'num ' + (late ? 'gl-late' : 'faint')}>{shortDate(m.due)}</span>
                      {p.owner && (
                        <span className="gl-row-actions">
                          <button
                            className="ghost"
                            aria-label="Edit milestone"
                            onClick={() => setEdit({ kind: 'milestone', data: { ...m } })}
                          >
                            <Pencil size={12} />
                          </button>
                          <button
                            className="ghost"
                            aria-label="Delete milestone"
                            onClick={() => drop('/api/milestones/' + m.id, 'milestone')}
                          >
                            <Trash2 size={12} />
                          </button>
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>

              {p.owner && (
                <footer>
                  <button className="sm" onClick={() => setEdit({ kind: 'goal', data: { ...g } })}>
                    <Pencil size={12} />
                    Edit
                  </button>
                  {g.status === 'Active' && (
                    <button
                      className="sm"
                      onClick={() =>
                        save('/api/goals', { id: g.id, status: 'Achieved' }, 'Goal marked achieved')
                      }
                    >
                      <CheckCircle2 size={12} />
                      Mark achieved
                    </button>
                  )}
                  {g.status !== 'Active' && (
                    <button
                      className="sm"
                      onClick={() => save('/api/goals', { id: g.id, status: 'Active' }, 'Goal reopened')}
                    >
                      Reopen
                    </button>
                  )}
                  <span className="grow" />
                  <button
                    className="ghost danger-ghost"
                    aria-label="Delete goal"
                    onClick={() => drop('/api/goals/' + g.id, 'goal')}
                  >
                    <Trash2 size={13} />
                  </button>
                </footer>
              )}
            </article>
          ))}
        </div>

        <aside className="gl-deadlines" aria-label="Deadlines">
          <div className="section-title">
            <h2>Deadlines</h2>
            <span>tasks, milestones, goals, projects</span>
          </div>
          {(
            [
              ['overdue', 'Overdue', 'var(--critical)'],
              ['this_week', 'This week', 'var(--warn)'],
              ['later', 'Later', 'var(--text-faint)'],
            ] as const
          ).map(([key, label, tone]) => {
            const items: Row[] = p.deadlines?.[key] || [];
            if (!items.length) return null;
            return (
              <div key={key} className="gl-dl-group">
                <div className="gl-dl-head" style={{ color: tone }}>
                  <span className="micro-label" style={{ color: tone }}>
                    {label}
                  </span>
                  <span className="num">{items.length}</span>
                </div>
                {items.slice(0, key === 'later' ? 8 : 12).map((d) => (
                  <button
                    key={d.type + d.id}
                    className="gl-dl"
                    onClick={() => {
                      if (d.type === 'task') p.openTask(d.ref_id || d.id);
                      else if (d.type === 'project') p.openProject(d.ref_id || d.id);
                      else {
                        setFocus(d.goal_id || d.ref_id || d.id);
                        document
                          .getElementById('goal-' + (d.goal_id || d.id))
                          ?.scrollIntoView({ behavior: 'smooth', block: 'center' });
                      }
                    }}
                  >
                    <span className="gl-dl-icon">
                      {d.type === 'task' ? (
                        <ListTodo size={13} />
                      ) : d.type === 'project' ? (
                        <FolderKanban size={13} />
                      ) : d.type === 'milestone' ? (
                        <MilestoneIcon size={13} />
                      ) : (
                        <Target size={13} />
                      )}
                    </span>
                    <span className="grow gl-dl-title">{d.title}</span>
                    <span className="num gl-dl-when" style={{ color: tone }}>
                      {d.days < 0 ? `${-d.days}d late` : d.days === 0 ? 'today' : `${d.days}d`}
                    </span>
                    <ArrowUpRight size={11} />
                  </button>
                ))}
              </div>
            );
          })}
          {!(
            p.deadlines?.overdue?.length ||
            p.deadlines?.this_week?.length ||
            p.deadlines?.later?.length
          ) && (
            <p className="faint small">
              No dated work yet. Dates on tasks, milestones, goals and projects appear here, nearest first.
            </p>
          )}
          {nextDue && <p className="faint small gl-foot">Next on the calendar: {date(nextDue.due)}.</p>}
        </aside>
      </div>
    </div>
  );
}

/** A dotted track between start and target: where each milestone lands against the schedule. */
function MilestoneTrack({ goal }: { goal: Row }) {
  const t = (s: string) => new Date(s + 'T12:00').getTime();
  const a = goal.start_date ? t(goal.start_date) : Math.min(...goal.milestones.map((m: Row) => t(m.due)));
  const b = goal.target_date ? t(goal.target_date) : Math.max(...goal.milestones.map((m: Row) => t(m.due)));
  const span = Math.max(b - a, 86400e3);
  const pos = (s: string) => Math.max(0, Math.min(100, ((t(s) - a) / span) * 100));
  const now = pos(todayISO());
  return (
    <div className="gl-track" aria-hidden="true">
      <i className="gl-track-line" />
      <i className="gl-track-now" style={{ left: now + '%' }} />
      {goal.milestones.map((m: Row) => (
        <i
          key={m.id}
          className={'gl-track-dot ' + (m.done ? 'done' : '')}
          style={{ left: pos(m.due) + '%' }}
          title={`${m.title} · ${m.due}`}
        />
      ))}
    </div>
  );
}

function Editor({
  edit,
  projects,
  goals,
  close,
  save,
  setEdit,
}: {
  edit: NonNullable<Edit>;
  projects: Row[];
  goals: Row[];
  close: () => void;
  save: (path: string, body: Row, done?: string) => void;
  setEdit: (e: Edit) => void;
}) {
  const d = edit.data;
  const set = (k: string, v: unknown) => setEdit({ ...edit, data: { ...d, [k]: v } } as NonNullable<Edit>);
  const title =
    edit.kind === 'goal'
      ? d.id
        ? 'Edit goal'
        : 'New goal'
      : edit.kind === 'kr'
        ? d.id
          ? 'Edit key result'
          : 'New key result'
        : d.id
          ? 'Edit milestone'
          : 'New milestone';
  const path =
    edit.kind === 'goal' ? '/api/goals' : edit.kind === 'kr' ? '/api/key-results' : '/api/milestones';
  const body = (): Row => {
    if (edit.kind === 'kr') {
      const manual = d.kind === 'manual';
      return {
        ...d,
        target: manual ? Number(d.target) || 0 : 0,
        current: manual ? Number(d.current) || 0 : 0,
        project_name: manual ? '' : d.project_name || '',
      };
    }
    return d;
  };
  return (
    <form
      className="gl-editor"
      onSubmit={(e) => {
        e.preventDefault();
        save(path, body());
      }}
    >
      <header>
        <h3 className="moment">{title}</h3>
        <button type="button" className="ghost" aria-label="Close" onClick={close}>
          <X size={15} />
        </button>
      </header>
      <label>
        Title
        <input
          autoFocus
          required
          maxLength={300}
          value={d.title || ''}
          onChange={(e) => set('title', e.target.value)}
          placeholder={
            edit.kind === 'goal'
              ? 'Ship AIGIS 2.4 to field teams'
              : edit.kind === 'kr'
                ? 'Close every release-blocking task'
                : 'Feature freeze'
          }
        />
      </label>
      {edit.kind === 'goal' && (
        <>
          <label>
            Why it matters
            <textarea
              rows={2}
              value={d.description || ''}
              onChange={(e) => set('description', e.target.value)}
            />
          </label>
          <div className="form-row">
            <label>
              Owner
              <input
                value={d.owner || ''}
                onChange={(e) => set('owner', e.target.value)}
                placeholder="Sanju"
              />
            </label>
            <label>
              Start
              <input
                type="date"
                value={d.start_date || ''}
                onChange={(e) => set('start_date', e.target.value)}
              />
            </label>
            <label>
              Deadline
              <input
                type="date"
                value={d.target_date || ''}
                onChange={(e) => set('target_date', e.target.value)}
              />
            </label>
          </div>
          <label>
            Linked project (optional)
            <select value={d.project_id || ''} onChange={(e) => set('project_id', e.target.value)}>
              <option value="">None</option>
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
        </>
      )}
      {edit.kind === 'kr' && (
        <>
          <div className="form-row">
            <label>
              Measured by
              <select value={d.kind || 'tasks'} onChange={(e) => set('kind', e.target.value)}>
                <option value="tasks">Tasks completed in a project</option>
                <option value="manual">A number I update</option>
              </select>
            </label>
            <label>
              Due
              <input type="date" value={d.due || ''} onChange={(e) => set('due', e.target.value)} />
            </label>
          </div>
          {d.kind !== 'manual' ? (
            <label>
              Project
              <select
                required
                value={d.project_name || ''}
                onChange={(e) => set('project_name', e.target.value)}
              >
                <option value="">Choose…</option>
                {[...new Set(['General', ...projects.map((p) => p.name)])].map((n) => (
                  <option key={n}>{n}</option>
                ))}
              </select>
            </label>
          ) : (
            <div className="form-row">
              <label>
                Current
                <input
                  type="number"
                  step="any"
                  value={d.current ?? ''}
                  onChange={(e) => set('current', e.target.value)}
                />
              </label>
              <label>
                Target
                <input
                  type="number"
                  step="any"
                  min="0"
                  required
                  value={d.target ?? ''}
                  onChange={(e) => set('target', e.target.value)}
                />
              </label>
              <label>
                Unit
                <input
                  maxLength={20}
                  value={d.unit || ''}
                  onChange={(e) => set('unit', e.target.value)}
                  placeholder="%, flights, pts"
                />
              </label>
            </div>
          )}
        </>
      )}
      {edit.kind === 'milestone' && (
        <>
          <div className="form-row">
            <label>
              Date
              <input type="date" required value={d.due || ''} onChange={(e) => set('due', e.target.value)} />
            </label>
            <label>
              Goal
              <select value={d.goal_id || ''} onChange={(e) => set('goal_id', e.target.value)}>
                <option value="">None</option>
                {goals.map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.title}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </>
      )}
      <div className="dialog-actions">
        <button type="button" onClick={close}>
          Cancel
        </button>
        <button className="primary">Save</button>
      </div>
    </form>
  );
}
