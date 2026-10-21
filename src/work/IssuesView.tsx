import React, { useEffect, useMemo, useState } from 'react';
import { Columns3, Filter, List, Plus, Save, Sparkles, Trash2, X, Link2, Maximize2 } from 'lucide-react';
import { api, remove, date, shortDate, todayISO, STATUSES, PRIORITIES, type Row } from '../lib/api';
import { Avatar, Key, Label, PriorityIcon, StatusIcon } from './bits';

type Props = {
  tasks: Row[];
  projects: Row[];
  cycles: Row[];
  insights: Row | null;
  query: string;
  owner: boolean;
  refresh: () => Promise<unknown>;
  openDetails: (task: Row) => void;
  create: (seed?: Row) => void;
  fail: (e: unknown) => void;
  notify: (text: string) => void;
  initialStatus?: string;
  focus?: string;
};
const GROUPS = { status: 'Status', project: 'Project', owner: 'Owner', priority: 'Priority' } as const;
type Group = keyof typeof GROUPS;
const EMPTY: Row = { status: '', priority: '', owner: '', project: '', label: '', cycle_id: '' };

export function IssuesView(p: Props) {
  const [layout, setLayout] = useState<'list' | 'board'>(
    () => (localStorage.getItem('gt.layout') as 'list') || 'list',
  );
  const [group, setGroup] = useState<Group>('status');
  const [filters, setFilters] = useState<Row>({
    ...EMPTY,
    status: p.initialStatus && p.initialStatus !== 'All' ? p.initialStatus : '',
  });
  const [showFilters, setShowFilters] = useState(false);
  const [views, setViews] = useState<Row[]>([]);
  const [selected, setSelected] = useState<string>(p.focus || '');
  useEffect(() => {
    if (p.focus) setSelected(p.focus);
  }, [p.focus]);
  useEffect(() => {
    try {
      localStorage.setItem('gt.layout', layout);
    } catch {}
  }, [layout]);
  useEffect(() => {
    api('/api/views')
      .then(setViews)
      .catch(() => setViews([]));
  }, []);
  const owners = [...new Set(p.tasks.map((t) => t.owner || 'Unassigned'))].sort();
  const labels = [...new Set(p.tasks.flatMap((t) => t.labels || []))].sort();
  const q = p.query.toLowerCase();
  const visible = useMemo(
    () =>
      p.tasks.filter(
        (t) =>
          (!q ||
            `${t.key} ${t.title} ${t.project} ${t.owner} ${(t.labels || []).join(' ')}`
              .toLowerCase()
              .includes(q)) &&
          (!filters.status || t.status === filters.status) &&
          (!filters.priority || t.priority === filters.priority) &&
          (!filters.owner || (t.owner || 'Unassigned') === filters.owner) &&
          (!filters.project || t.project === filters.project) &&
          (!filters.label || (t.labels || []).includes(filters.label)) &&
          (!filters.cycle_id || t.cycle_id === filters.cycle_id),
      ),
    [p.tasks, q, filters],
  );
  const groupKeys =
    group === 'status'
      ? [...STATUSES]
      : group === 'priority'
        ? [...PRIORITIES]
        : [
            ...new Set(
              visible.map((t) => (group === 'owner' ? t.owner || 'Unassigned' : t[group]) || 'None'),
            ),
          ].sort();
  const keyOf = (t: Row) => (group === 'owner' ? t.owner || 'Unassigned' : t[group]) || 'None';
  const order = groupKeys.flatMap((g) => visible.filter((t) => keyOf(t) === g));
  const current = p.tasks.find((t) => t.id === selected);

  async function patch(task: Row, change: Row) {
    try {
      await api('/api/tasks', { id: task.id, ...change });
      await p.refresh();
    } catch (e) {
      p.fail(e);
    }
  }
  // J/K MOVE THROUGH THE VISIBLE ORDER LIKE LINEAR; typing in a field never steals the key.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = document.activeElement as HTMLElement | null;
      if (el && /INPUT|TEXTAREA|SELECT/.test(el.tagName)) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const i = order.findIndex((t) => t.id === selected);
      if (e.key === 'j' && order.length) setSelected(order[Math.min(i + 1, order.length - 1)].id);
      else if (e.key === 'k' && order.length) setSelected(order[Math.max(i - 1, 0)].id);
      else if (e.key === 'Escape') setSelected('');
      else if (e.key === 'Enter' && current) p.openDetails(current);
      else if (e.key === 'c' && p.owner) {
        e.preventDefault();
        p.create(filters.project ? { project: filters.project } : {});
      } else return;
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [order, selected, current, filters.project]);

  const activeFilters = Object.entries(filters).filter(([, v]) => v);
  const cycleName = (id: string) => p.cycles.find((c) => c.id === id)?.name || '';
  // ELECTRON HAS NO window.prompt: name the view inline.
  const [viewName, setViewName] = useState<string | null>(null);
  async function saveView() {
    const name = (viewName || '').trim();
    if (!name) return;
    try {
      await api('/api/views', { name, filters });
      setViewName(null);
      setViews(await api('/api/views'));
      p.notify('View saved');
    } catch (e) {
      p.fail(e);
    }
  }
  return (
    <div className={'wk-issues ' + (current ? 'with-peek' : '')}>
      <div className="wk-main">
        <div className="wk-bar">
          <div className="wk-seg" role="group" aria-label="Layout">
            <button aria-pressed={layout === 'list'} onClick={() => setLayout('list')}>
              <List size={13} />
              List
            </button>
            <button aria-pressed={layout === 'board'} onClick={() => setLayout('board')}>
              <Columns3 size={13} />
              Board
            </button>
          </div>
          {layout === 'list' && (
            <label className="wk-inline">
              Group
              <select value={group} onChange={(e) => setGroup(e.target.value as Group)}>
                {Object.entries(GROUPS).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </select>
            </label>
          )}
          <button className="sm" aria-expanded={showFilters} onClick={() => setShowFilters(!showFilters)}>
            <Filter size={13} />
            Filter{activeFilters.length ? ` · ${activeFilters.length}` : ''}
          </button>
          {activeFilters.map(([k, v]) => (
            <button key={k} className="wk-chip removable" onClick={() => setFilters({ ...filters, [k]: '' })}>
              {k === 'cycle_id' ? cycleName(v) : v}
              <X size={11} />
            </button>
          ))}
          <span className="grow" />
          <select
            aria-label="Saved views"
            value=""
            onChange={(e) => {
              const v = views.find((x) => x.id === e.target.value);
              if (v) setFilters({ ...EMPTY, ...v.filters });
            }}
          >
            <option value="">Saved views{views.length ? ` (${views.length})` : ''}</option>
            <option value="__mine" disabled>
              ──
            </option>
            {views.map((v) => (
              <option key={v.id} value={v.id}>
                {v.name}
              </option>
            ))}
          </select>
          {activeFilters.length > 0 &&
            (viewName === null ? (
              <button className="sm" onClick={() => setViewName('')}>
                <Save size={13} />
                Save view
              </button>
            ) : (
              <form
                className="wk-inline"
                onSubmit={(e) => {
                  e.preventDefault();
                  saveView();
                }}
              >
                <input
                  autoFocus
                  aria-label="View name"
                  placeholder="View name"
                  value={viewName}
                  onChange={(e) => setViewName(e.target.value)}
                  onKeyDown={(e) => e.key === 'Escape' && setViewName(null)}
                />
                <button className="sm primary" disabled={!viewName.trim()}>
                  Save
                </button>
              </form>
            ))}
          {p.owner && (
            <button
              className="primary sm"
              onClick={() => p.create(filters.project ? { project: filters.project } : {})}
            >
              <Plus size={13} />
              New task <kbd>C</kbd>
            </button>
          )}
        </div>
        {showFilters && (
          <div className="wk-filters">
            {(
              [
                ['status', 'Status', STATUSES],
                ['priority', 'Priority', PRIORITIES],
                ['owner', 'Owner', owners],
                ['project', 'Project', p.projects.map((x) => x.name)],
                ['label', 'Label', labels],
              ] as [string, string, readonly string[]][]
            ).map(([k, l, opts]) => (
              <label key={k}>
                {l}
                <select value={filters[k]} onChange={(e) => setFilters({ ...filters, [k]: e.target.value })}>
                  <option value="">Any</option>
                  {opts.map((o) => (
                    <option key={o}>{o}</option>
                  ))}
                </select>
              </label>
            ))}
            <label>
              Cycle
              <select
                value={filters.cycle_id}
                onChange={(e) => setFilters({ ...filters, cycle_id: e.target.value })}
              >
                <option value="">Any</option>
                {p.cycles.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>
            <button className="sm" onClick={() => setFilters(EMPTY)}>
              Clear all
            </button>
          </div>
        )}
        {!visible.length ? (
          <div className="wk-empty">
            <h3>Nothing matches.</h3>
            <p>Clear a filter, or press C to capture the next piece of work.</p>
          </div>
        ) : layout === 'list' ? (
          <div className="wk-list" role="listbox" aria-label="Tasks">
            {groupKeys.map((g) => {
              const items = visible.filter((t) => keyOf(t) === g);
              if (!items.length) return null;
              return (
                <section key={g}>
                  <header className="wk-group">
                    {group === 'status' && <StatusIcon status={g} />}
                    {group === 'priority' && <PriorityIcon priority={g} />}
                    {group === 'owner' && <Avatar name={g} size={16} />}
                    <strong>{g}</strong>
                    <span className="num">{items.length}</span>
                    <span className="grow" />
                    {p.owner && (
                      <button
                        className="ghost"
                        aria-label={'New task in ' + g}
                        onClick={() => p.create(group === 'owner' ? { owner: g } : { [group]: g })}
                      >
                        <Plus size={13} />
                      </button>
                    )}
                  </header>
                  {items.map((t) => (
                    <div
                      key={t.id}
                      role="option"
                      aria-selected={selected === t.id}
                      tabIndex={0}
                      className="wk-row"
                      onClick={() => setSelected(t.id)}
                      onDoubleClick={() => p.openDetails(t)}
                      onKeyDown={(e) => e.key === ' ' && setSelected(t.id)}
                    >
                      <PriorityIcon priority={t.priority} />
                      <Key task={t} />
                      <StatusIcon status={t.status} />
                      <span className="wk-title">
                        {t.title}
                        {t.parent_id && <small> ↳ sub-task</small>}
                      </span>
                      <span className="wk-tags">
                        {(t.labels || []).slice(0, 3).map((l: string) => (
                          <Label key={l} name={l} />
                        ))}
                        {t.cycle_id && <span className="wk-chip">{cycleName(t.cycle_id)}</span>}
                      </span>
                      <span
                        className={
                          'num wk-due ' + (t.due && t.due < todayISO() && t.status !== 'Done' ? 'late' : '')
                        }
                      >
                        {t.due ? shortDate(t.due) : ''}
                      </span>
                      <Avatar name={t.owner} />
                    </div>
                  ))}
                </section>
              );
            })}
          </div>
        ) : (
          <div className="wk-board">
            {STATUSES.map((s) => {
              const items = visible.filter((t) => t.status === s);
              return (
                <div
                  key={s}
                  className="wk-col"
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={(e) => {
                    const t = p.tasks.find((x) => x.id === e.dataTransfer.getData('text/goteet-task'));
                    if (t && t.status !== s)
                      patch(t, { status: s }).then(() => p.notify(`${t.key || t.title} → ${s}`));
                  }}
                >
                  <header>
                    <StatusIcon status={s} />
                    {s}
                    <span className="num">{items.length}</span>
                    <span className="grow" />
                    <span className="num faint">
                      {items.reduce((a, t) => a + (Number(t.estimate) || 0), 0)} pt
                    </span>
                  </header>
                  <div className="wk-col-body">
                    {items.map((t) => (
                      <button
                        key={t.id}
                        className={'wk-card ' + (selected === t.id ? 'selected' : '')}
                        draggable={p.owner}
                        onDragStart={(e) => e.dataTransfer.setData('text/goteet-task', t.id)}
                        onClick={() => setSelected(t.id)}
                        onDoubleClick={() => p.openDetails(t)}
                      >
                        <span className="wk-card-top">
                          <Key task={t} />
                          <span className="grow" />
                          <Avatar name={t.owner} />
                        </span>
                        <span className="wk-card-title">{t.title}</span>
                        <span className="wk-card-meta">
                          <PriorityIcon priority={t.priority} />
                          {(t.labels || []).slice(0, 2).map((l: string) => (
                            <Label key={l} name={l} />
                          ))}
                          <span className="grow" />
                          {t.due && <span className="num faint">{shortDate(t.due)}</span>}
                          {Number(t.estimate) > 0 && <span className="num faint">{t.estimate}pt</span>}
                        </span>
                      </button>
                    ))}
                    {p.owner && (
                      <button className="wk-add" onClick={() => p.create({ status: s })}>
                        <Plus size={13} />
                        Add
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
      {current && (
        <Peek
          key={current.id}
          task={current}
          {...p}
          patch={(c) => patch(current, c)}
          close={() => setSelected('')}
          select={setSelected}
        />
      )}
    </div>
  );
}

function Peek({
  task,
  tasks,
  projects,
  cycles,
  insights,
  owner,
  patch,
  close,
  select,
  openDetails,
  create,
  refresh,
  fail,
  notify,
}: Props & { task: Row; patch: (c: Row) => Promise<void>; close: () => void; select: (id: string) => void }) {
  const [relations, setRelations] = useState<Row[]>([]);
  const [label, setLabel] = useState('');
  const [linkTo, setLinkTo] = useState('');
  const loadRelations = () =>
    api('/api/relations?task_id=' + encodeURIComponent(task.id))
      .then(setRelations)
      .catch(() => setRelations([]));
  useEffect(() => {
    loadRelations();
  }, [task.id]);
  const subs = tasks.filter((t) => t.parent_id === task.id);
  const findings = (insights?.findings || []).filter((f: Row) =>
    f.evidence?.some((e: Row) => e.type === 'task' && e.id === task.id),
  );
  const byId = (id: string) => tasks.find((t) => t.id === id);
  const Prop = ({ name, children }: { name: string; children: React.ReactNode }) => (
    <div className="wk-prop">
      <span>{name}</span>
      {children}
    </div>
  );
  return (
    <aside className="wk-peek" aria-label={'Details for ' + task.title}>
      <header>
        <Key task={task} />
        <span className="grow" />
        <button className="sm" onClick={() => openDetails(task)}>
          <Maximize2 size={13} />
          Full details
        </button>
        <button className="ghost" aria-label="Close details" onClick={close}>
          <X size={15} />
        </button>
      </header>
      <div className="wk-peek-body">
        <h2>{task.title}</h2>
        {task.description ? (
          <p className="wk-desc">{task.description}</p>
        ) : (
          <p className="faint">No description yet.</p>
        )}
        {findings.length > 0 && (
          <div className="wk-ai-note">
            <strong>
              <Sparkles size={13} />
              Agent noticed
            </strong>
            {findings.map((f: Row) => (
              <p key={f.id}>
                <span className={'sev ' + f.severity}>{f.severity}</span> {f.title}. {f.suggestion}
              </p>
            ))}
          </div>
        )}
        <Prop name="Status">
          <select disabled={!owner} value={task.status} onChange={(e) => patch({ status: e.target.value })}>
            {STATUSES.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </Prop>
        <Prop name="Priority">
          <select
            disabled={!owner}
            value={task.priority}
            onChange={(e) => patch({ priority: e.target.value })}
          >
            {PRIORITIES.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </Prop>
        <Prop name="Owner">
          <input
            disabled={!owner}
            defaultValue={task.owner}
            onBlur={(e) => e.target.value !== task.owner && patch({ owner: e.target.value || 'Unassigned' })}
          />
        </Prop>
        <Prop name="Project">
          <select disabled={!owner} value={task.project} onChange={(e) => patch({ project: e.target.value })}>
            {[...new Set(['General', task.project, ...projects.map((x) => x.name)])].map((n) => (
              <option key={n}>{n}</option>
            ))}
          </select>
        </Prop>
        <Prop name="Cycle">
          <select
            disabled={!owner}
            value={task.cycle_id || ''}
            onChange={(e) => patch({ cycle_id: e.target.value })}
          >
            <option value="">None</option>
            {cycles.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </Prop>
        <Prop name="Estimate">
          <select
            disabled={!owner}
            value={String(task.estimate || 0)}
            onChange={(e) => patch({ estimate: Number(e.target.value) })}
          >
            {[0, 1, 2, 3, 5, 8, 13].map((n) => (
              <option key={n} value={n}>
                {n ? n + ' pt' : 'None'}
              </option>
            ))}
          </select>
        </Prop>
        <Prop name="Due">
          <input
            disabled={!owner}
            type="date"
            value={task.due || ''}
            onChange={(e) => patch({ due: e.target.value })}
          />
        </Prop>
        <Prop name="Labels">
          <span className="wk-tags wrap">
            {(task.labels || []).map((l: string) => (
              <button
                key={l}
                className="wk-chip removable"
                disabled={!owner}
                onClick={() => patch({ labels: (task.labels || []).filter((x: string) => x !== l) })}
              >
                {l}
                <X size={10} />
              </button>
            ))}
            {owner && (
              <input
                className="wk-label-input"
                placeholder="+ label"
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && label.trim() && !e.nativeEvent.isComposing) {
                    patch({ labels: [...new Set([...(task.labels || []), label.trim().toLowerCase()])] });
                    setLabel('');
                  }
                }}
              />
            )}
          </span>
        </Prop>
        <hr className="wk-double" />
        <div className="wk-subhead">
          <span className="micro-label">
            Sub-tasks · {subs.filter((s) => s.status === 'Done').length}/{subs.length}
          </span>
          {owner && (
            <button
              className="ghost sm"
              onClick={() => create({ parent_id: task.id, project: task.project, cycle_id: task.cycle_id })}
            >
              <Plus size={12} />
              Add
            </button>
          )}
        </div>
        {subs.map((s) => (
          <button key={s.id} className="wk-line" onClick={() => select(s.id)}>
            <StatusIcon status={s.status} />
            <Key task={s} />
            {s.title}
          </button>
        ))}
        <div className="wk-subhead">
          <span className="micro-label">Relations</span>
        </div>
        {relations.map((r) => {
          const other = byId(r.from_id === task.id ? r.to_id : r.from_id);
          const verb = r.type === 'blocks' ? (r.from_id === task.id ? 'blocks' : 'blocked by') : r.type;
          return (
            <div key={r.id} className="wk-line">
              <span className="faint">{verb}</span>
              {other ? (
                <button className="link" onClick={() => select(other.id)}>
                  <Key task={other} /> {other.title}
                </button>
              ) : (
                <span className="faint">deleted task</span>
              )}
              {owner && (
                <button
                  className="ghost"
                  aria-label="Remove relation"
                  onClick={() =>
                    remove('/api/relations/' + r.id)
                      .then(loadRelations)
                      .catch(fail)
                  }
                >
                  <X size={12} />
                </button>
              )}
            </div>
          );
        })}
        {owner && (
          <div className="wk-line">
            <Link2 size={13} />
            <select value={linkTo} onChange={(e) => setLinkTo(e.target.value)} aria-label="Task to link">
              <option value="">Link another task…</option>
              {tasks
                .filter((t) => t.id !== task.id)
                .map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.key || ''} {t.title}
                  </option>
                ))}
            </select>
            {['blocks', 'relates'].map((type) => (
              <button
                key={type}
                className="sm"
                disabled={!linkTo}
                onClick={() =>
                  api('/api/relations', { from_id: task.id, to_id: linkTo, type })
                    .then(() => {
                      setLinkTo('');
                      return loadRelations();
                    })
                    .catch(fail)
                }
              >
                {type}
              </button>
            ))}
          </div>
        )}
        <hr className="wk-double" />
        <p className="faint small">
          Created {date(task.created_at)} · updated {date(task.updated_at)}
          {task.source_url ? ' · has source link' : ''}
        </p>
        {owner && (
          <button
            className="danger-ghost sm"
            onClick={async () => {
              if (!confirm(`Delete ${task.key || task.title}? Relations are removed; sub-tasks are kept.`))
                return;
              try {
                await remove('/api/tasks/' + task.id);
                close();
                await refresh();
                notify('Task deleted');
              } catch (e) {
                fail(e);
              }
            }}
          >
            <Trash2 size={13} />
            Delete task
          </button>
        )}
      </div>
    </aside>
  );
}
