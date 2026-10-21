import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  CalendarDays,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Diamond,
  GripVertical,
  Plus,
  RefreshCw,
} from 'lucide-react';
import { type Row } from '../lib/api';
import { Avatar, Key, Meter, PriorityIcon, StatusIcon } from '../work/bits';
import { shortDate } from '../lib/api';

/* Roadmap: a timeline that reads like a calendar.
   Dates are never inferred: unscheduled work stays in the tray until a person places it. Dragging a bar
   changes only the dates on that item; the change is saved through the same partial-update API as the editor. */

const DAY = 864e5;
const ISO = (n: number) => new Date(n * DAY).toISOString().slice(0, 10);
const NUM = (s: string) => Math.round(Date.UTC(+s.slice(0, 4), +s.slice(5, 7) - 1, +s.slice(8, 10)) / DAY);
const todayN = () => {
  const d = new Date();
  return Math.round(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()) / DAY);
};
const WEEKDAY = (n: number) => new Date(n * DAY).getUTCDay();
const LABEL = (n: number, opts: Intl.DateTimeFormatOptions) =>
  new Date(n * DAY).toLocaleDateString('en-IN', { timeZone: 'UTC', ...opts });

const ZOOM = {
  week: { dayW: 44, span: 28, step: 7, name: 'Week' },
  month: { dayW: 18, span: 84, step: 14, name: 'Month' },
  quarter: { dayW: 7, span: 182, step: 30, name: 'Quarter' },
} as const;
type Zoom = keyof typeof ZOOM;

const HEALTH_TONE: Record<string, string> = {
  'On track': 'var(--ok)',
  'At risk': 'var(--warn)',
  'Off track': 'var(--critical)',
  Done: 'var(--ok)',
  'No plan': 'var(--text-faint)',
};

type Drag = {
  id: string;
  kind: 'task' | 'project';
  mode: 'move' | 'end';
  x0: number;
  s0: number;
  e0: number;
  ds: number;
  de: number;
};

export function Roadmap({
  projects,
  tasks,
  cycles,
  insights,
  owner,
  openTask,
  openProject,
  saveTask,
  saveProject,
  createTask,
  createProject,
  fail,
  calendar,
  syncCalendar,
}: {
  projects: Row[];
  tasks: Row[];
  cycles: Row[];
  insights: Row | null;
  owner: boolean;
  openTask: (t: Row) => void;
  openProject: (p: Row) => void;
  saveTask: (t: Row) => Promise<void>;
  saveProject: (p: Row) => Promise<void>;
  createTask: () => void;
  createProject: () => void;
  fail: (e: unknown) => void;
  calendar: Row | null;
  syncCalendar?: () => void;
}) {
  const [zoom, setZoom] = useState<Zoom>(() => (localStorage.getItem('gt.zoom') as Zoom) || 'week');
  const [anchor, setAnchor] = useState(todayN());
  const [project, setProject] = useState('all');
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const [drag, setDrag] = useState<Drag | null>(null);
  const [preview, setPreview] = useState<Record<string, [number, number]>>({});
  const [hover, setHover] = useState<string>('');
  const [sel, setSel] = useState<string>('');
  const area = useRef<HTMLDivElement>(null);
  const Z = ZOOM[zoom];

  useEffect(() => {
    try {
      localStorage.setItem('gt.zoom', zoom);
    } catch {}
  }, [zoom]);

  const start = anchor - Math.floor(Z.span / 3);
  const days = Array.from({ length: Z.span }, (_, i) => start + i);
  const end = start + Z.span - 1;
  const today = todayN();

  // System calendar events are read-only context: they never move, and they are not dated tasks.
  const calEvents: Row[] = (calendar?.events || [])
    .filter((e: Row) => e.start && e.start.slice(0, 10) >= ISO(start - 1) && e.start.slice(0, 10) <= ISO(end))
    .slice(0, 40);
  const insightFor = (id: string) => insights?.projects?.find((p: Row) => p.id === id);
  const shownProjects = projects.filter((p) => project === 'all' || p.id === project);
  const span = (s?: string, e?: string): [number, number] | null => {
    if (!s || !e) return null;
    const a = NUM(s),
      b = NUM(e);
    return b < a ? [b, a] : [a, b];
  };
  const barFor = (id: string, s: number, e: number): [number, number] => preview[id] || [s, e];

  // Grouped rows: project header, then its tasks (scheduled or not). Ungrouped tasks at the bottom.
  const groups = shownProjects.map((p) => {
    const own = tasks.filter((t) => t.project === p.name);
    const done = own.filter((t) => t.status === 'Done').length;
    return { p, own, done, health: insightFor(p.id)?.health || (own.length ? 'On track' : 'No plan') };
  });
  const ungrouped = tasks.filter(
    (t) => (project === 'all' || project === '') && !projects.some((p) => p.name === t.project),
  );

  // Smart strip: what is late, what lands this range, and what is unplaced.
  const scheduled = tasks.filter((t) => t.status !== 'Done' && t.due);
  const overdue = scheduled.filter((t) => NUM(t.due) < today).length;
  const inRange = scheduled.filter((t) => NUM(t.due) >= start && NUM(t.due) <= end).length;
  const unplaced = tasks.filter((t) => t.status !== 'Done' && !t.due).length;
  const nextMilestone = projects
    .filter((p) => p.target_date && p.status !== 'Done' && NUM(p.target_date) >= today)
    .sort((a, b) => NUM(a.target_date) - NUM(b.target_date))[0];

  // Load per day: how many open tasks are due, so overloaded days are visible at a glance.
  const load = useMemo(() => {
    const m: Record<number, number> = {};
    tasks.forEach((t) => {
      if (t.status !== 'Done' && t.due) m[NUM(t.due)] = (m[NUM(t.due)] || 0) + 1;
    });
    return m;
  }, [tasks]);

  function pointerDown(
    e: React.PointerEvent,
    kind: 'task' | 'project',
    id: string,
    s: number,
    en: number,
    mode: 'move' | 'end',
  ) {
    if (!owner) return;
    e.preventDefault();
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    setDrag({ id, kind, mode, x0: e.clientX, s0: s, e0: en, ds: 0, de: 0 });
    setSel(id);
  }
  useEffect(() => {
    if (!drag) return;
    const dayW = Z.dayW;
    const move = (ev: PointerEvent) => {
      const d = Math.round((ev.clientX - drag.x0) / dayW);
      const [s, en] =
        drag.mode === 'move' ? [drag.s0 + d, drag.e0 + d] : [drag.s0, Math.max(drag.s0, drag.e0 + d)];
      setPreview({ [drag.id]: [s, en] });
    };
    const up = async (ev: PointerEvent) => {
      const d = Math.round((ev.clientX - drag.x0) / dayW);
      setDrag(null);
      const [s, en] =
        drag.mode === 'move' ? [drag.s0 + d, drag.e0 + d] : [drag.s0, Math.max(drag.s0, drag.e0 + d)];
      setPreview({});
      if (d === 0 && drag.mode === 'move') return;
      try {
        if (drag.kind === 'task') {
          const t = tasks.find((x) => x.id === drag.id);
          if (t) await saveTask({ ...t, start_date: ISO(s), due: ISO(en) });
        } else {
          const p = projects.find((x) => x.id === drag.id);
          if (p) await saveProject({ ...p, start_date: ISO(s), target_date: ISO(en) });
        }
      } catch (e) {
        fail(e);
      }
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up, { once: true });
    return () => {
      window.removeEventListener('pointermove', move);
    };
  }, [drag]);

  // Keyboard: select a bar, then arrows move it a day (Shift = a week). Enter opens details.
  function onKey(e: React.KeyboardEvent, kind: 'task' | 'project', item: Row) {
    if (!owner) return;
    const step = e.shiftKey ? 7 : 1;
    const sp =
      kind === 'task' ? span(item.start_date || item.due, item.due) : span(item.start_date, item.target_date);
    if (!sp) return;
    let [s, en] = sp;
    if (e.key === 'ArrowLeft') (s -= step), (en -= step);
    else if (e.key === 'ArrowRight') (s += step), (en += step);
    else if (e.key === 'Enter') return kind === 'task' ? openTask(item) : openProject(item);
    else return;
    e.preventDefault();
    const save =
      kind === 'task'
        ? saveTask({ ...item, start_date: ISO(s), due: ISO(en) })
        : saveProject({ ...item, start_date: ISO(s), target_date: ISO(en) });
    save.catch(fail);
  }

  const monthHeads: { label: string; from: number; to: number }[] = [];
  days.forEach((d) => {
    const label = LABEL(d, { month: 'long', year: 'numeric' });
    const last = monthHeads[monthHeads.length - 1];
    if (last && last.label === label) last.to = d;
    else monthHeads.push({ label, from: d, to: d });
  });
  const gridW = Z.span * Z.dayW;
  const x = (n: number) => (n - start) * Z.dayW;

  function Bar({
    kind,
    item,
    s,
    en,
    tone,
  }: {
    kind: 'task' | 'project';
    item: Row;
    s: number;
    en: number;
    tone: string;
  }) {
    const [ps, pe] = barFor(item.id, s, en);
    const left = x(ps);
    const width = Math.max(Z.dayW, (pe - ps + 1) * Z.dayW);
    const overdueTask = kind === 'task' && item.status !== 'Done' && pe < today;
    const active = sel === item.id;
    return (
      <div
        role="button"
        tabIndex={0}
        aria-label={`${kind === 'task' ? item.key || item.title : item.name} · ${LABEL(ps, { day: 'numeric', month: 'short' })} to ${LABEL(pe, { day: 'numeric', month: 'short' })}`}
        className={`rm-bar ${kind} ${overdueTask ? 'late' : ''} ${active ? 'active' : ''} ${width < Z.dayW * 3 ? 'short' : ''}`}
        style={{ left, width, ['--tone' as string]: tone }}
        onPointerDown={(e) => pointerDown(e, kind, item.id, s, en, 'move')}
        onKeyDown={(e) => onKey(e, kind, item)}
        onClick={() => (kind === 'task' ? openTask(item) : openProject(item))}
        onMouseEnter={() => setHover(item.id)}
        onMouseLeave={() => setHover('')}
      >
        {kind === 'project' && item.progress !== undefined && (
          <span className="rm-bar-fill" style={{ width: `${item.progress * 100}%` }} />
        )}
        <span className="rm-bar-label">{kind === 'task' ? item.title : item.name}</span>
        {owner && (
          <span
            className="rm-handle"
            onPointerDown={(e) => {
              e.stopPropagation();
              pointerDown(e, kind, item.id, ps, pe, 'end');
            }}
            aria-hidden="true"
          />
        )}
        {hover === item.id && (
          <span className="rm-tip">
            {kind === 'task'
              ? `${item.key || ''} · ${item.status} · ${item.owner || 'Unassigned'}`
              : `${item.status} · ${Math.round((item.progress || 0) * 100)}% done`}
            <br />
            {LABEL(ps, { day: 'numeric', month: 'short' })} –{' '}
            {LABEL(pe, { day: 'numeric', month: 'short', year: 'numeric' })}
          </span>
        )}
      </div>
    );
  }

  return (
    <div className="rm">
      <div className="rm-smart" role="region" aria-label="Schedule summary">
        <Stat label="Overdue" value={overdue} tone={overdue ? 'var(--critical)' : undefined} />
        <Stat label="Due in view" value={inRange} />
        <Stat label="Unplaced" value={unplaced} hint="drag from tray" />
        <Stat
          label="Next milestone"
          value={nextMilestone ? `${Math.max(0, NUM(nextMilestone.target_date) - today)} d` : '—'}
          hint={nextMilestone ? nextMilestone.name : 'set a target date'}
        />
      </div>

      <div className="rm-bar-top">
        <div className="rm-nav">
          <button className="sm" aria-label="Previous" onClick={() => setAnchor(anchor - Z.step)}>
            <ChevronLeft size={14} />
          </button>
          <button className="sm" onClick={() => setAnchor(todayN())}>
            Today
          </button>
          <button className="sm" aria-label="Next" onClick={() => setAnchor(anchor + Z.step)}>
            <ChevronRight size={14} />
          </button>
          <strong className="rm-range">
            {LABEL(start, { day: 'numeric', month: 'short' })} –{' '}
            {LABEL(end, { day: 'numeric', month: 'short', year: 'numeric' })}
          </strong>
        </div>
        <div className="wk-seg" role="group" aria-label="Zoom">
          {(Object.keys(ZOOM) as Zoom[]).map((z) => (
            <button key={z} aria-pressed={zoom === z} onClick={() => setZoom(z)}>
              {ZOOM[z].name}
            </button>
          ))}
        </div>
        <select aria-label="Project" value={project} onChange={(e) => setProject(e.target.value)}>
          <option value="all">All projects</option>
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
        <span className="grow" />
        {syncCalendar && calendar?.enabled && (
          <button
            className="sm"
            onClick={syncCalendar}
            title={
              calendar.captured_at ? `Last read ${calendar.captured_at}` : 'Read the system calendar now'
            }
          >
            <RefreshCw size={13} />
            Sync calendar
          </button>
        )}
        {owner && (
          <>
            <button className="sm" onClick={createProject}>
              <Plus size={13} />
              Project
            </button>
            <button className="primary sm" onClick={createTask}>
              <Plus size={13} />
              Task
            </button>
          </>
        )}
      </div>

      <div className="rm-body">
        <div className="rm-grid" ref={area}>
          <div className="rm-left">
            <div className="rm-head rm-head-left">Work</div>
            {calEvents.length > 0 && (
              <>
                <div className="rm-group static rm-cal-head">
                  <CalendarDays size={13} />
                  <span className="grow">Calendar · read-only</span>
                  <span className="num faint">{calEvents.length}</span>
                </div>
                {calEvents.map((ev) => (
                  <div key={ev.uid} className="rm-row-label rm-cal-row" title={ev.location || ''}>
                    <span className="rm-cal-dot" />
                    <span className="grow rm-title">{ev.title}</span>
                    <span className="num faint rm-cal-when">{shortDate(ev.start)}</span>
                  </div>
                ))}
              </>
            )}
            {groups.map(({ p, own, done, health }) => (
              <React.Fragment key={p.id}>
                <button
                  className="rm-group"
                  onClick={() => setOpen({ ...open, [p.id]: open[p.id] === false })}
                  aria-expanded={open[p.id] !== false}
                >
                  <ChevronDown
                    size={13}
                    style={{ transform: open[p.id] === false ? 'rotate(-90deg)' : 'none' }}
                  />
                  <span className="grow rm-group-name">{p.name}</span>
                  <span
                    className="chip-health"
                    style={{ color: HEALTH_TONE[health], borderColor: HEALTH_TONE[health] }}
                  >
                    {health}
                  </span>
                </button>
                {open[p.id] !== false &&
                  own.map((t) => (
                    <div key={t.id} className="rm-row-label" onClick={() => openTask(t)}>
                      <StatusIcon status={t.status} />
                      <Key task={t} />
                      <span className="grow rm-title">{t.title}</span>
                      <Avatar name={t.owner} size={18} />
                    </div>
                  ))}
              </React.Fragment>
            ))}
            {ungrouped.length > 0 && <div className="rm-group static">Ungrouped</div>}
            {ungrouped.map((t) => (
              <div key={t.id} className="rm-row-label" onClick={() => openTask(t)}>
                <StatusIcon status={t.status} />
                <Key task={t} />
                <span className="grow rm-title">{t.title}</span>
              </div>
            ))}
          </div>

          <div
            className="rm-scroll"
            onDragOver={(e) => owner && e.preventDefault()}
            onDrop={(e) => {
              const id = e.dataTransfer.getData('text/goteet-task');
              const t = tasks.find((x) => x.id === id);
              if (!t || !owner) return;
              const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
              const d =
                start +
                Math.floor((e.clientX - rect.left + (e.currentTarget as HTMLElement).scrollLeft) / Z.dayW);
              saveTask({ ...t, due: ISO(d), start_date: t.start_date || ISO(d) }).catch(fail);
            }}
          >
            <div className="rm-canvas" style={{ width: gridW }}>
              <div className="rm-months" style={{ width: gridW }}>
                {monthHeads.map((m) => (
                  <div
                    key={m.label + m.from}
                    style={{ left: x(m.from), width: (m.to - m.from + 1) * Z.dayW }}
                    className="rm-month"
                  >
                    {m.label}
                  </div>
                ))}
              </div>
              <div className="rm-days" style={{ width: gridW }}>
                {days.map((d) => {
                  const wk = WEEKDAY(d) === 0 || WEEKDAY(d) === 6;
                  return (
                    <div
                      key={d}
                      className={`rm-day ${d === today ? 'today' : ''} ${wk ? 'weekend' : ''} ${(load[d] || 0) >= 3 ? 'busy' : ''}`}
                      style={{ left: x(d), width: Z.dayW }}
                      title={`${LABEL(d, { weekday: 'short', day: 'numeric', month: 'short' })}${load[d] ? ` · ${load[d]} due` : ''}`}
                    >
                      {Z.dayW >= 16 && <span>{LABEL(d, { day: 'numeric' })}</span>}
                      {Z.dayW >= 16 && Z.dayW < 30 && (
                        <span className="rm-wd">{LABEL(d, { weekday: 'narrow' })}</span>
                      )}
                    </div>
                  );
                })}
              </div>
              <div className="rm-cycles" style={{ width: gridW }}>
                {cycles.map((c) => {
                  const sp = span(c.start, c.end);
                  if (!sp || sp[1] < start || sp[0] > end) return null;
                  return (
                    <div
                      key={c.id}
                      className={`rm-cycle ${c.status}`}
                      style={{ left: x(sp[0]), width: (sp[1] - sp[0] + 1) * Z.dayW }}
                    >
                      {c.name}
                    </div>
                  );
                })}
              </div>
              <div className="rm-lanes" style={{ width: gridW }}>
                {days.map((d) => (
                  <div
                    key={d}
                    className={`rm-col ${d === today ? 'today' : ''} ${WEEKDAY(d) % 6 === 0 ? 'weekend' : ''}`}
                    style={{ left: x(d), width: Z.dayW }}
                  />
                ))}
                <div className="rm-now" style={{ left: x(today) + Z.dayW / 2 }} aria-hidden="true" />
                {groups.map(({ p, own }) => {
                  const sp = span(p.start_date, p.target_date);
                  return (
                    <React.Fragment key={p.id}>
                      <div className="rm-lane project">
                        {sp && (
                          <Bar
                            kind="project"
                            item={{
                              ...p,
                              title: p.name,
                              progress: own.length
                                ? own.filter((t) => t.status === 'Done').length / own.length
                                : 0,
                            }}
                            s={sp[0]}
                            en={sp[1]}
                            tone={HEALTH_TONE[insightFor(p.id)?.health] || 'var(--accent)'}
                          />
                        )}
                        {p.target_date && (
                          <span
                            className="rm-milestone"
                            style={{ left: x(NUM(p.target_date)) + Z.dayW / 2 - 6 }}
                            title={`${p.name} target ${p.target_date}`}
                          >
                            <Diamond size={12} />
                          </span>
                        )}
                      </div>
                      {open[p.id] !== false &&
                        own.map((t) => {
                          const tsp = span(t.start_date || t.due, t.due);
                          return (
                            <div key={t.id} className="rm-lane">
                              {tsp && (
                                <Bar
                                  kind="task"
                                  item={t}
                                  s={tsp[0]}
                                  en={tsp[1]}
                                  tone={
                                    t.status === 'Done'
                                      ? 'var(--ok)'
                                      : t.status === 'Blocked'
                                        ? 'var(--critical)'
                                        : 'var(--accent)'
                                  }
                                />
                              )}
                            </div>
                          );
                        })}
                    </React.Fragment>
                  );
                })}
                {calEvents.length > 0 && (
                  <>
                    <div className="rm-lane project" />
                    {calEvents.map((ev) => {
                      const sp = span(ev.start.slice(0, 10), (ev.end || ev.start).slice(0, 10));
                      return (
                        <div key={ev.uid} className="rm-lane rm-cal-lane">
                          {sp && (
                            <div
                              className="rm-cal-bar"
                              style={{
                                left: x(sp[0]),
                                width: Math.max(Z.dayW, (sp[1] - sp[0] + 1) * Z.dayW),
                              }}
                              title={`${ev.title} · ${ev.calendar || ''}`}
                            >
                              {ev.title}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </>
                )}
                {ungrouped.length > 0 && <div className="rm-lane project" />}
                {ungrouped.map((t) => {
                  const tsp = span(t.start_date || t.due, t.due);
                  return (
                    <div key={t.id} className="rm-lane">
                      {tsp && <Bar kind="task" item={t} s={tsp[0]} en={tsp[1]} tone="var(--accent)" />}
                    </div>
                  );
                })}
              </div>
              <div className="rm-loadrow" style={{ width: gridW }}>
                {days.map((d) => (
                  <span
                    key={d}
                    className={`rm-load ${(load[d] || 0) >= 3 ? 'busy' : ''}`}
                    style={{ left: x(d), width: Z.dayW }}
                  >
                    {load[d] ? <i style={{ height: Math.min(16, load[d] * 5) }} /> : null}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>

        <aside className="rm-tray" aria-label="Unscheduled work">
          <div className="rm-tray-head">
            <span className="micro-label">Unscheduled · {unplaced}</span>
          </div>
          <p className="faint small">
            Drag onto the timeline to set a due date. Nothing is dated automatically.
          </p>
          {tasks
            .filter((t) => t.status !== 'Done' && !t.due)
            .map((t) => (
              <div
                key={t.id}
                className="rm-tray-item"
                draggable={owner}
                onDragStart={(e) => e.dataTransfer.setData('text/goteet-task', t.id)}
                onClick={() => openTask(t)}
              >
                <GripVertical size={13} />
                <PriorityIcon priority={t.priority} />
                <span className="grow rm-title">{t.title}</span>
                <CalendarDays size={13} />
              </div>
            ))}
          {unplaced === 0 && <p className="faint small">Everything open has a due date.</p>}
        </aside>
      </div>
      <p className="faint small rm-foot">
        Drag a bar to move it, drag its right edge to change its end. Select a bar and use ← → (Shift for a
        week). Diamonds are project targets. Busy days are shaded.
      </p>
    </div>
  );
}

function Stat({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: React.ReactNode;
  hint?: string;
  tone?: string;
}) {
  return (
    <div className="rm-stat">
      <span className="micro-label">{label}</span>
      <strong className="num" style={tone ? { color: tone } : undefined}>
        {value}
      </strong>
      {hint && <small>{hint}</small>}
    </div>
  );
}
