export type Row = Record<string, any>;

export const api = (route: string, value?: unknown) =>
  window.goteet.request(value === undefined ? 'GET' : 'POST', route, value);
export const remove = (route: string) => window.goteet.request('DELETE', route);

export const cleanError = (e: unknown) =>
  (e instanceof Error ? e.message : String(e)).replace(
    /^Error invoking remote method '[^']+': (?:Error: )?/,
    '',
  );

export let displayZone = 'Asia/Kolkata';
export const setDisplayZone = (zone: string) => {
  displayZone = zone || 'Asia/Kolkata';
};

// DATE-ONLY VALUES ARE CALENDAR DAYS, NOT INSTANTS: new Date('2026-11-01') is UTC midnight and rendered a day
// early west of UTC (bug audit, main.tsx:29). Anchor bare dates at local noon before formatting.
export const parseDay = (value: string) =>
  new Date(/^\d{4}-\d{2}-\d{2}$/.test(value) ? value + 'T12:00' : value);
export const date = (value?: string) =>
  value
    ? parseDay(value).toLocaleDateString('en-IN', {
        day: 'numeric',
        month: 'short',
        year: 'numeric',
        ...(/^\d{4}-\d{2}-\d{2}$/.test(value) ? {} : { timeZone: displayZone }),
      })
    : 'Not set';
export const shortDate = (value?: string) =>
  value ? parseDay(value).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' }) : '—';
export const ago = (value?: string) => {
  if (!value) return '';
  const s = (Date.now() - new Date(value).getTime()) / 1000;
  return s < 60
    ? 'now'
    : s < 3600
      ? Math.floor(s / 60) + 'm'
      : s < 86400
        ? Math.floor(s / 3600) + 'h'
        : Math.floor(s / 86400) + 'd';
};
export const todayISO = () => new Date().toLocaleDateString('en-CA', { timeZone: displayZone });

export const STATUSES = ['Backlog', 'Todo', 'In progress', 'In review', 'Blocked', 'Done'] as const;
export const PRIORITIES = ['Urgent', 'High', 'Normal', 'Low'] as const;
