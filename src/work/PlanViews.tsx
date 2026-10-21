import React, { useEffect, useState } from 'react';
import { Bell, BellOff, Check, CheckCheck, FileText, Play, Plus, Power, Trash2, Zap } from 'lucide-react';
import { api, remove, ago, date, shortDate, todayISO, STATUSES, type Row } from '../lib/api';
import { Avatar, Burnup, Key, Meter, PriorityIcon, StatusIcon } from './bits';

type Common = { fail: (e: unknown) => void; notify: (t: string) => void; owner: boolean };

/* ───────── Cycles: time-boxed sprints with burn-up ───────── */
export function CyclesView({
  cycles,
  tasks,
  reload,
  refresh,
  openTask,
  fail,
  notify,
  owner,
}: Common & {
  cycles: Row[];
  tasks: Row[];
  reload: () => void;
  refresh: () => Promise<unknown>;
  openTask: (id: string) => void;
}) {
  const [draft, setDraft] = useState<Row | null>(null);
  const [open, setOpen] = useState<string>(
    () => cycles.find((c) => c.status === 'active')?.id || cycles[0]?.id || '',
  );
  const current = cycles.find((c) => c.id === open);
  const items = tasks.filter((t) => t.cycle_id === open);
  const backlog = tasks.filter((t) => !t.cycle_id && t.status !== 'Done');
  async function save() {
    try {
      await api('/api/cycles', draft);
      setDraft(null);
      reload();
      notify('Cycle saved');
    } catch (e) {
      fail(e);
    }
  }
  const nextStart = () => {
    const last = cycles
      .map((c) => c.end)
      .sort()
      .at(-1);
    const d = last ? new Date(last + 'T12:00') : new Date();
    if (last) d.setDate(d.getDate() + 1);
    const s = d.toLocaleDateString('en-CA');
    d.setDate(d.getDate() + 13);
    return { start: s, end: d.toLocaleDateString('en-CA') };
  };
  return (
    <div className="cy-view">
      <div className="cy-rail">
        {owner && (
          <button
            className="primary sm"
            onClick={() => setDraft({ name: `Cycle ${cycles.length + 1}`, goal: '', ...nextStart() })}
          >
            <Plus size={13} />
            New cycle
          </button>
        )}
        {cycles.map((c) => (
          <button
            key={c.id}
            className={'cy-item ' + (open === c.id ? 'active' : '')}
            onClick={() => setOpen(c.id)}
          >
            <span className={'cy-state ' + c.status}>{c.status}</span>
            <strong>{c.name}</strong>
            <small className="num">
              {shortDate(c.start)} – {shortDate(c.end)}
            </small>
            <Meter
              value={
                c.stats?.points
                  ? c.stats.done_points / c.stats.points
                  : c.stats?.issues
                    ? c.stats.done / c.stats.issues
                    : 0
              }
            />
          </button>
        ))}
        {!cycles.length && <p className="faint">No cycles yet. Two-week cycles keep scope honest.</p>}
      </div>
      <div className="cy-main">
        {draft ? (
          <form
            className="cy-form"
            onSubmit={(e) => {
              e.preventDefault();
              save();
            }}
          >
            <h2>{draft.id ? 'Edit cycle' : 'New cycle'}</h2>
            <label>
              Name
              <input
                required
                value={draft.name}
                onChange={(e) => setDraft({ ...draft, name: e.target.value })}
              />
            </label>
            <div className="form-row">
              <label>
                Start
                <input
                  type="date"
                  required
                  value={draft.start}
                  onChange={(e) => setDraft({ ...draft, start: e.target.value })}
                />
              </label>
              <label>
                End
                <input
                  type="date"
                  required
                  value={draft.end}
                  onChange={(e) => setDraft({ ...draft, end: e.target.value })}
                />
              </label>
            </div>
            <label>
              Goal
              <textarea
                rows={3}
                value={draft.goal}
                onChange={(e) => setDraft({ ...draft, goal: e.target.value })}
              />
            </label>
            <div className="dialog-actions">
              <button type="button" onClick={() => setDraft(null)}>
                Cancel
              </button>
              <button className="primary">Save cycle</button>
            </div>
          </form>
        ) : current ? (
          <>
            <section className="cy-head ticks">
              <div className="grow">
                <span className="micro-label">
                  {current.status} · {date(current.start)} – {date(current.end)}
                </span>
                <h2 className="moment">{current.name}</h2>
                {current.goal && <p>{current.goal}</p>}
                <div className="cy-stats">
                  {[
                    ['Issues', `${current.stats?.done ?? 0}/${current.stats?.issues ?? 0}`],
                    ['Points', `${current.stats?.done_points ?? 0}/${current.stats?.points ?? 0}`],
                    ['Blocked', current.stats?.blocked ?? 0],
                  ].map(([k, v]) => (
                    <span key={String(k)}>
                      <small className="micro-label">{k}</small>
                      <strong className="num">{v}</strong>
                    </span>
                  ))}
                </div>
              </div>
              <div className="cy-burn">
                <Burnup history={current.stats?.history || []} />
              </div>
              {owner && (
                <div className="cy-tools">
                  <button className="sm" onClick={() => setDraft({ ...current })}>
                    Edit
                  </button>
                  <button
                    className="sm danger-ghost"
                    onClick={async () => {
                      if (!confirm(`Delete ${current.name}? Its tasks stay and return to the backlog.`))
                        return;
                      await remove('/api/cycles/' + current.id).catch(fail);
                      reload();
                      await refresh();
                    }}
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              )}
            </section>
            <div className="cy-cols">
              <section>
                <div className="section-title">
                  <h2>In this cycle</h2>
                  <span>{items.length}</span>
                </div>
                {STATUSES.map((s) =>
                  items
                    .filter((t) => t.status === s)
                    .map((t) => (
                      <div key={t.id} className="wk-row compact cy-row" onClick={() => openTask(t.id)}>
                        <PriorityIcon priority={t.priority} />
                        <Key task={t} />
                        <StatusIcon status={t.status} />
                        <span className="wk-title">{t.title}</span>
                        <span className="num faint">{t.estimate ? t.estimate + 'pt' : ''}</span>
                        <Avatar name={t.owner} />
                        {owner && (
                          <button
                            className="ghost sm"
                            onClick={(e) => {
                              e.stopPropagation();
                              api('/api/tasks', { id: t.id, cycle_id: '' }).then(refresh).catch(fail);
                            }}
                          >
                            Remove
                          </button>
                        )}
                      </div>
                    )),
                )}
                {!items.length && <p className="faint">Pull work in from the backlog.</p>}
              </section>
              <section>
                <div className="section-title">
                  <h2>Backlog</h2>
                  <span>{backlog.length} open, unplanned</span>
                </div>
                {backlog.slice(0, 40).map((t) => (
                  <div key={t.id} className="wk-row compact cy-back">
                    <PriorityIcon priority={t.priority} />
                    <Key task={t} />
                    <span className="wk-title">{t.title}</span>
                    {owner && current.status !== 'completed' && (
                      <button
                        className="sm"
                        onClick={() =>
                          api('/api/tasks', { id: t.id, cycle_id: current.id }).then(refresh).catch(fail)
                        }
                      >
                        <Plus size={12} />
                        Add
                      </button>
                    )}
                  </div>
                ))}
              </section>
            </div>
          </>
        ) : (
          <div className="wk-empty">
            <h3 className="moment">Give the work a rhythm.</h3>
            <p>Create a cycle, pull tasks in, and the burn-up tracks scope and completion.</p>
          </div>
        )}
      </div>
    </div>
  );
}

/* ───────── Inbox: what changed that needs you ───────── */
const KIND_LABEL: Record<string, string> = {
  assigned: 'Assigned',
  mention: 'Mention',
  status: 'Status',
  blocked: 'Blocked',
  automation: 'Automation',
  agent: 'Agent',
  chat: 'Chat',
};
export function InboxView({
  items,
  reload,
  open,
  fail,
}: {
  items: Row[];
  reload: () => void;
  open: (item: Row) => void;
  fail: (e: unknown) => void;
}) {
  const [filter, setFilter] = useState('unread');
  const shown = items.filter((i) =>
    filter === 'unread' ? !i.read : filter === 'all' ? true : i.kind === filter,
  );
  const mark = (ids: string[] | 'all') => api('/api/inbox/read', { ids }).then(reload).catch(fail);
  return (
    <div className="ib-view">
      <div className="wk-bar">
        <div className="wk-seg" role="group" aria-label="Inbox filter">
          {['unread', 'all', 'agent', 'blocked', 'mention', 'assigned'].map((f) => (
            <button key={f} aria-pressed={filter === f} onClick={() => setFilter(f)}>
              {f === 'unread' ? `Unread · ${items.filter((i) => !i.read).length}` : KIND_LABEL[f] || 'All'}
            </button>
          ))}
        </div>
        <span className="grow" />
        <button className="sm" onClick={() => mark('all')}>
          <CheckCheck size={13} />
          Mark all read
        </button>
      </div>
      {shown.length ? (
        shown.map((i) => (
          <div key={i.id} className={'ib-row ' + (i.read ? '' : 'unread')}>
            <Avatar name={i.actor || 'GOTEET'} />
            <span className={'ib-kind ' + i.kind}>{KIND_LABEL[i.kind] || i.kind}</span>
            <button
              className="ib-main"
              onClick={() => {
                if (!i.read) mark([i.id]);
                open(i);
              }}
            >
              <strong>{i.title}</strong>
              {i.detail && <small>{i.detail}</small>}
            </button>
            <span className="num faint">{ago(i.created_at)}</span>
            {!i.read && (
              <button className="ghost" aria-label="Mark read" onClick={() => mark([i.id])}>
                <Check size={14} />
              </button>
            )}
            <button
              className="ghost"
              aria-label="Snooze until tomorrow"
              title="Snooze until tomorrow 09:00"
              onClick={() => {
                const d = new Date();
                d.setDate(d.getDate() + 1);
                d.setHours(9, 0, 0, 0);
                api('/api/inbox/snooze', { id: i.id, until: d.toISOString() }).then(reload).catch(fail);
              }}
            >
              <BellOff size={14} />
            </button>
          </div>
        ))
      ) : (
        <div className="wk-empty">
          <Bell size={22} />
          <h3 className="moment">Inbox zero.</h3>
          <p>Assignments, blockers, mentions and agent reports land here.</p>
        </div>
      )}
    </div>
  );
}

/* ───────── Docs: linked, markdown pages ───────── */
export function DocsView({
  docs,
  tasks,
  projects,
  reload,
  openTask,
  fail,
  notify,
  owner,
  query,
}: Common & {
  docs: Row[];
  tasks: Row[];
  projects: Row[];
  reload: () => void;
  openTask: (id: string) => void;
  query: string;
}) {
  const [sel, setSel] = useState<string>(docs[0]?.id || '');
  const [draft, setDraft] = useState<Row | null>(null);
  useEffect(() => {
    if (!sel && docs[0]) setSel(docs[0].id);
  }, [docs]);
  const shown = docs.filter((d) => !query || (d.title + d.body).toLowerCase().includes(query.toLowerCase()));
  const doc = docs.find((d) => d.id === sel);
  const edit = draft ?? null;
  async function save() {
    try {
      const saved = await api('/api/docs', draft);
      setDraft(null);
      reload();
      if (saved?.id) setSel(saved.id);
      notify('Doc saved');
    } catch (e) {
      fail(e);
    }
  }
  return (
    <div className="dc-view">
      <nav className="dc-list" aria-label="Docs">
        {owner && (
          <button
            className="primary sm"
            onClick={() => setDraft({ title: 'Untitled', body: '', project: '', linked_tasks: [] })}
          >
            <Plus size={13} />
            New doc
          </button>
        )}
        {shown.map((d) => (
          <button
            key={d.id}
            className={'dc-item ' + (sel === d.id && !edit ? 'active' : '')}
            onClick={() => (setSel(d.id), setDraft(null))}
          >
            <FileText size={13} />
            <span>
              {d.title}
              <small>
                {d.project || 'Workspace'} · {ago(d.updated_at)}
              </small>
            </span>
          </button>
        ))}
        {!docs.length && <p className="faint">Specs, decisions and meeting notes, linked to the work.</p>}
      </nav>
      <article className="dc-page">
        {edit ? (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              save();
            }}
          >
            <input
              className="dc-title-input"
              value={edit.title}
              onChange={(e) => setDraft({ ...edit, title: e.target.value })}
              aria-label="Title"
            />
            <div className="form-row">
              <label>
                Project
                <select value={edit.project} onChange={(e) => setDraft({ ...edit, project: e.target.value })}>
                  <option value="">Workspace</option>
                  {projects.map((p) => (
                    <option key={p.id}>{p.name}</option>
                  ))}
                </select>
              </label>
              <label>
                Link task
                <select
                  value=""
                  onChange={(e) =>
                    e.target.value &&
                    setDraft({
                      ...edit,
                      linked_tasks: [...new Set([...(edit.linked_tasks || []), e.target.value])],
                    })
                  }
                >
                  <option value="">Choose…</option>
                  {tasks.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.key} {t.title}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div className="wk-tags wrap">
              {(edit.linked_tasks || []).map((id: string) => {
                const t = tasks.find((x) => x.id === id);
                return (
                  <button
                    type="button"
                    key={id}
                    className="wk-chip removable"
                    onClick={() =>
                      setDraft({ ...edit, linked_tasks: edit.linked_tasks.filter((x: string) => x !== id) })
                    }
                  >
                    {t?.key || 'deleted'} ×
                  </button>
                );
              })}
            </div>
            <textarea
              className="dc-body-input"
              rows={22}
              value={edit.body}
              onChange={(e) => setDraft({ ...edit, body: e.target.value })}
              placeholder="# Heading&#10;Write in Markdown…"
            />
            <div className="dialog-actions">
              <button type="button" onClick={() => setDraft(null)}>
                Cancel
              </button>
              <button className="primary">Save doc</button>
            </div>
          </form>
        ) : doc ? (
          <>
            <div className="dc-meta">
              <span className="micro-label">
                {doc.project || 'Workspace'} · {doc.author || 'Local'} · edited {date(doc.updated_at)}
              </span>
              <span className="grow" />
              {owner && (
                <>
                  <button className="sm" onClick={() => setDraft({ ...doc })}>
                    Edit
                  </button>
                  <button
                    className="sm danger-ghost"
                    aria-label="Delete doc"
                    onClick={async () => {
                      if (!confirm('Delete this doc?')) return;
                      await remove('/api/docs/' + doc.id).catch(fail);
                      setSel('');
                      reload();
                    }}
                  >
                    <Trash2 size={13} />
                  </button>
                </>
              )}
            </div>
            <h1 className="moment dc-title">{doc.title}</h1>
            {(doc.linked_tasks || []).length > 0 && (
              <div className="dc-links">
                {doc.linked_tasks.map((id: string) => {
                  const t = tasks.find((x) => x.id === id);
                  return t ? (
                    <button key={id} className="dc-block" onClick={() => openTask(id)}>
                      <StatusIcon status={t.status} />
                      <Key task={t} />
                      {t.title}
                      <Avatar name={t.owner} />
                    </button>
                  ) : null;
                })}
              </div>
            )}
            <Markdown text={doc.body} />
          </>
        ) : (
          <div className="wk-empty">
            <h3 className="moment">Write it down once.</h3>
            <p>Docs live next to the tasks they describe.</p>
          </div>
        )}
      </article>
    </div>
  );
}
export function Markdown({ text }: { text: string }) {
  return (
    <div className="dc-md">
      {(text || '').split('\n').map((l, i) =>
        l.startsWith('### ') ? (
          <h4 key={i}>{l.slice(4)}</h4>
        ) : l.startsWith('## ') ? (
          <h3 key={i}>{l.slice(3)}</h3>
        ) : l.startsWith('# ') ? (
          <h2 key={i}>{l.slice(2)}</h2>
        ) : /^[-*] \[[ x]\] /.test(l) ? (
          <p key={i} className="dc-check">
            <input type="checkbox" readOnly checked={l[3] === 'x'} /> {l.slice(6)}
          </p>
        ) : /^[-*] /.test(l) ? (
          <p key={i} className="dc-li">
            • {l.slice(2)}
          </p>
        ) : l.startsWith('> ') ? (
          <blockquote key={i}>{l.slice(2)}</blockquote>
        ) : l.startsWith('```') ? null : l ? (
          <p key={i}>{l}</p>
        ) : (
          <br key={i} />
        ),
      )}
    </div>
  );
}

/* ───────── Automations: local, audited rules ───────── */
const TRIGGERS: Record<string, string> = {
  task_status: 'When a task moves to status',
  task_blocked_hours: 'When a task stays Blocked for hours',
  task_created: 'When a task is created in project',
};
const ACTIONS: Record<string, string> = {
  set_field: 'Set field',
  notify: 'Notify inbox',
  add_label: 'Add label',
};
export function AutomationsView({
  rules,
  reload,
  fail,
  notify,
  owner,
}: Common & { rules: Row[]; reload: () => void }) {
  const [draft, setDraft] = useState<Row | null>(null);
  const [dry, setDry] = useState<Row | null>(null);
  const describe = (r: Row) => {
    const p = r.params || {};
    const when =
      r.trigger === 'task_status'
        ? `status → ${p.to_status}`
        : r.trigger === 'task_blocked_hours'
          ? `blocked > ${p.hours} h`
          : `created in ${p.project || 'any project'}`;
    const then =
      r.action === 'set_field'
        ? `set ${p.field} = ${p.value}`
        : r.action === 'add_label'
          ? `add label “${p.label}”`
          : 'notify inbox';
    return `${when}  →  ${then}`;
  };
  return (
    <div className="au-view">
      <div className="wk-bar">
        <span className="micro-label">
          Rules run locally after each change · every run is audited · no external messages
        </span>
        <span className="grow" />
        {owner && (
          <button
            className="primary sm"
            onClick={() =>
              setDraft({
                name: '',
                trigger: 'task_status',
                action: 'notify',
                params: { to_status: 'Blocked' },
                enabled: true,
              })
            }
          >
            <Plus size={13} />
            New rule
          </button>
        )}
      </div>
      {draft && (
        <form
          className="au-form"
          onSubmit={(e) => {
            e.preventDefault();
            api('/api/automations', draft)
              .then(() => {
                setDraft(null);
                reload();
                notify('Rule saved');
              })
              .catch(fail);
          }}
        >
          <label>
            Name
            <input
              required
              value={draft.name}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
            />
          </label>
          <div className="form-row">
            <label>
              Trigger
              <select
                value={draft.trigger}
                onChange={(e) => setDraft({ ...draft, trigger: e.target.value, params: {} })}
              >
                {Object.entries(TRIGGERS).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </select>
            </label>
            {draft.trigger === 'task_status' && (
              <label>
                Status
                <select
                  value={draft.params.to_status || ''}
                  onChange={(e) =>
                    setDraft({ ...draft, params: { ...draft.params, to_status: e.target.value } })
                  }
                >
                  {STATUSES.map((s) => (
                    <option key={s}>{s}</option>
                  ))}
                </select>
              </label>
            )}
            {draft.trigger === 'task_blocked_hours' && (
              <label>
                Hours
                <input
                  type="number"
                  min={1}
                  value={draft.params.hours || 48}
                  onChange={(e) =>
                    setDraft({ ...draft, params: { ...draft.params, hours: Number(e.target.value) } })
                  }
                />
              </label>
            )}
            {draft.trigger === 'task_created' && (
              <label>
                Project
                <input
                  value={draft.params.project || ''}
                  onChange={(e) =>
                    setDraft({ ...draft, params: { ...draft.params, project: e.target.value } })
                  }
                />
              </label>
            )}
          </div>
          <div className="form-row">
            <label>
              Action
              <select value={draft.action} onChange={(e) => setDraft({ ...draft, action: e.target.value })}>
                {Object.entries(ACTIONS).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </select>
            </label>
            {draft.action === 'set_field' && (
              <>
                <label>
                  Field
                  <select
                    value={draft.params.field || 'status'}
                    onChange={(e) =>
                      setDraft({ ...draft, params: { ...draft.params, field: e.target.value } })
                    }
                  >
                    {['status', 'priority', 'owner', 'cycle_id'].map((f) => (
                      <option key={f}>{f}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Value
                  <input
                    value={draft.params.value || ''}
                    onChange={(e) =>
                      setDraft({ ...draft, params: { ...draft.params, value: e.target.value } })
                    }
                  />
                </label>
              </>
            )}
            {draft.action === 'add_label' && (
              <label>
                Label
                <input
                  value={draft.params.label || ''}
                  onChange={(e) => setDraft({ ...draft, params: { ...draft.params, label: e.target.value } })}
                />
              </label>
            )}
          </div>
          <div className="dialog-actions">
            <button type="button" onClick={() => setDraft(null)}>
              Cancel
            </button>
            <button className="primary">Save rule</button>
          </div>
        </form>
      )}
      {rules.map((r) => (
        <div key={r.id} className={'au-row ' + (r.enabled ? 'on' : '')}>
          <Zap size={15} />
          <div className="grow">
            <strong>{r.name}</strong>
            <small className="num">{describe(r)}</small>
            {dry && dry.id === r.id && (
              <div className="inline-note">
                <strong>Dry run · nothing changed.</strong> {dry.result?.note}
                {(dry.result?.matches || []).length ? (
                  (dry.result.matches as Row[]).map((m) => (
                    <div key={m.task_id} className="num">
                      {m.key} · {m.would}
                      {m.already_applied ? ' (already applied)' : ''}
                    </div>
                  ))
                ) : (
                  <div>No current task matches this rule.</div>
                )}
              </div>
            )}
          </div>
          <span className="num faint">
            {r.runs} runs{r.last_run ? ' · ' + ago(r.last_run) : ''}
          </span>
          <button
            className="sm"
            title="Dry run: shows what would change, changes nothing"
            onClick={() =>
              api(`/api/automations/${r.id}/run`, {})
                .then((result) => setDry({ id: r.id, result }))
                .catch(fail)
            }
          >
            <Play size={12} />
            Dry run
          </button>
          {owner && (
            <>
              <button
                className={'sm ' + (r.enabled ? 'on' : '')}
                aria-pressed={!!r.enabled}
                onClick={() => api(`/api/automations/${r.id}/toggle`, {}).then(reload).catch(fail)}
              >
                <Power size={12} />
                {r.enabled ? 'On' : 'Off'}
              </button>
              <button className="ghost" aria-label="Edit rule" onClick={() => setDraft({ ...r })}>
                Edit
              </button>
              <button
                className="ghost"
                aria-label="Delete rule"
                onClick={() =>
                  confirm('Delete this rule?') &&
                  remove('/api/automations/' + r.id)
                    .then(reload)
                    .catch(fail)
                }
              >
                <Trash2 size={13} />
              </button>
            </>
          )}
        </div>
      ))}
      {!rules.length && !draft && (
        <div className="wk-empty">
          <h3 className="moment">Let the routine run itself.</h3>
          <p>Rules move work forward when something changes. Nothing leaves this computer.</p>
        </div>
      )}
    </div>
  );
}
export { todayISO };
