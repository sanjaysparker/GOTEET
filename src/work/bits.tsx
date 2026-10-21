import React from 'react';
import type { Row } from '../lib/api';

// STATUS IS DOUBLE-ENCODED: shape + colour, so it survives colour-blindness and greyscale (AIGIS DESIGN.md).
const STATUS_TONE: Record<string, [string, number]> = {
  Backlog: ['var(--text-faint)', 0],
  Todo: ['var(--text-dim)', 0],
  'In progress': ['var(--warn)', 0.5],
  'In review': ['var(--info)', 0.75],
  Blocked: ['var(--critical)', 0],
  Done: ['var(--ok)', 1],
};
export function StatusIcon({ status, size = 14 }: { status: string; size?: number }) {
  const [c, f] = STATUS_TONE[status] || STATUS_TONE.Todo;
  const label = <title>{status}</title>;
  if (status === 'Done')
    return (
      <svg className="wk-status" width={size} height={size} viewBox="0 0 14 14" role="img">
        {label}
        <circle cx="7" cy="7" r="6" fill={c} />
        <path d="M4 7l2 2 4-4" stroke="var(--bg)" strokeWidth="1.6" fill="none" />
      </svg>
    );
  if (status === 'Blocked')
    return (
      <svg className="wk-status" width={size} height={size} viewBox="0 0 14 14" role="img">
        {label}
        <circle cx="7" cy="7" r="6" fill="none" stroke={c} strokeWidth="1.5" />
        <path d="M3 11l8-8" stroke={c} strokeWidth="1.5" />
      </svg>
    );
  return (
    <svg className="wk-status" width={size} height={size} viewBox="0 0 14 14" role="img">
      {label}
      <circle
        cx="7"
        cy="7"
        r="6"
        fill="none"
        stroke={c}
        strokeWidth="1.5"
        strokeDasharray={status === 'Backlog' ? '2 2' : undefined}
      />
      {f > 0 && (
        <circle
          cx="7"
          cy="7"
          r="3"
          fill="none"
          stroke={c}
          strokeWidth="6"
          strokeDasharray={`${f * 2 * Math.PI * 3} 99`}
          transform="rotate(-90 7 7)"
        />
      )}
    </svg>
  );
}
export function PriorityIcon({ priority }: { priority: string }) {
  if (priority === 'Urgent')
    return (
      <span className="wk-prio urgent" title="Urgent" aria-label="Urgent priority">
        !
      </span>
    );
  const n = priority === 'High' ? 3 : priority === 'Normal' ? 2 : 1;
  return (
    <span className="wk-prio" title={priority} aria-label={priority + ' priority'}>
      {[1, 2, 3].map((i) => (
        <i key={i} className={i <= n ? 'on' : ''} style={{ height: i * 4 }} />
      ))}
    </span>
  );
}
const HUES = [35, 80, 130, 175, 220, 265, 310, 355];
export const hueOf = (text: string) =>
  HUES[[...(text || '?')].reduce((a, c) => (a * 31 + c.charCodeAt(0)) >>> 0, 7) % HUES.length];
export function Avatar({ name, size = 20 }: { name: string; size?: number }) {
  const n = name || 'Unassigned';
  return (
    <span
      className="wk-avatar"
      title={n}
      style={{
        width: size,
        height: size,
        background: n === 'Unassigned' ? 'var(--surface-3)' : `oklch(0.74 0.08 ${hueOf(n)})`,
        fontSize: size * 0.45,
      }}
    >
      {n === 'Unassigned' ? '–' : n[0].toUpperCase()}
    </span>
  );
}
export function Label({ name }: { name: string }) {
  return (
    <span className="wk-chip">
      <span className="wk-dot" style={{ background: `oklch(0.72 0.09 ${hueOf(name)})` }} />
      {name}
    </span>
  );
}
export function Key({ task }: { task: Row }) {
  return <span className="wk-key">{task.key || task.id?.slice(0, 6)}</span>;
}
export function Meter({ value, tone = 'var(--accent)' }: { value: number; tone?: string }) {
  return (
    <span
      className="wk-meter"
      role="meter"
      aria-valuenow={Math.round(value * 100)}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <span style={{ width: Math.max(0, Math.min(1, value)) * 100 + '%', background: tone }} />
    </span>
  );
}
export function Burnup({ history, height = 110 }: { history: Row[]; height?: number }) {
  if (!history?.length) return <p className="muted">History accrues as the cycle progresses.</p>;
  const W = 320,
    H = height,
    max = Math.max(...history.map((h) => h.scope), 1) * 1.1,
    x = (i: number) => (i * W) / Math.max(1, history.length - 1),
    y = (v: number) => H - (v * H) / max;
  const last = history[history.length - 1];
  return (
    <svg
      className="wk-burn"
      viewBox={`0 0 ${W} ${H + 16}`}
      role="img"
      aria-label={`Burn-up: ${last.done} of ${last.scope} done`}
    >
      <line x1="0" x2={W} y1={H} y2={H} stroke="var(--line)" />
      <polyline
        fill="none"
        stroke="var(--text-faint)"
        strokeDasharray="3 3"
        points={history.map((h, i) => `${x(i)},${y(h.scope)}`).join(' ')}
      />
      <polyline
        fill="none"
        stroke="var(--accent)"
        strokeWidth="1.6"
        points={history.map((h, i) => `${x(i)},${y(h.done)}`).join(' ')}
      />
      <circle cx={x(history.length - 1)} cy={y(last.done)} r="2.5" fill="var(--accent)" />
      <text x="0" y={H + 13} className="wk-axis">
        {history[0].date.slice(5)}
      </text>
      <text x={W} y={H + 13} textAnchor="end" className="wk-axis">
        {last.date.slice(5)} · {last.done}/{last.scope}
      </text>
    </svg>
  );
}
