import { useEffect, useState } from 'react';
import { Activity, FolderOpen, Sparkles } from 'lucide-react';
type Row = Record<string, any>;
const gb = (value: number) => (value / 2 ** 30).toFixed(2) + ' GB';
export function ResourceVisuals({ value }: { value: Row | null }) {
  const [history, setHistory] = useState<number[]>([]);
  useEffect(() => {
    if (value) setHistory((h) => [...h.slice(-23), value.cpu_percent]);
  }, [value?.captured_at]);
  if (!value) return null;
  const resources = [
    {
      name: 'Memory',
      percent: value.memory.percent,
      detail: gb(value.memory.available) + ' available',
      tone: 'memory',
    },
    { name: 'Storage', percent: value.disk.percent, detail: gb(value.disk.free) + ' free', tone: 'disk' },
    { name: 'CPU', percent: value.cpu_percent, detail: 'Current sample', tone: 'cpu' },
  ];
  return (
    <div className="resource-visuals">
      {resources.map((r) => (
        <div className={'resource-visual ' + r.tone} key={r.name}>
          <svg
            viewBox="0 0 100 100"
            role="img"
            aria-label={r.name + ' ' + r.percent.toFixed(1) + ' percent used'}
          >
            <circle className="gauge-track" cx="50" cy="50" r="40" />
            <circle
              className="gauge-value"
              cx="50"
              cy="50"
              r="40"
              strokeDasharray={`${Math.min(100, r.percent) * 2.513} 251.3`}
              transform="rotate(-90 50 50)"
            />
            <text x="50" y="54" textAnchor="middle">
              {Math.round(r.percent)}%
            </text>
          </svg>
          <div>
            <strong>{r.name}</strong>
            <small>{r.detail}</small>
          </div>
        </div>
      ))}
      <div className="cpu-history">
        <span>CPU samples</span>
        <svg
          viewBox="0 0 240 80"
          preserveAspectRatio="none"
          role="img"
          aria-label="Recent CPU utilization samples"
        >
          <path
            d={'M ' + history.map((v, i) => `${(i * 240) / 23},${76 - v * 0.68}`).join(' L ')}
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
          />
        </svg>
        <small>Observed while System is open</small>
      </div>
    </div>
  );
}
export function SystemReview({
  provider,
  model,
  initial,
  browse,
  fail,
}: {
  provider: string;
  model: string;
  initial: Row | null;
  browse: (path: string) => void;
  fail: (e: unknown) => void;
}) {
  const [health, setHealth] = useState<Row | null>(initial),
    [answer, setAnswer] = useState(''),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    if (initial) setHealth(initial);
  }, [initial]);
  async function check(ai = false) {
    setBusy(true);
    try {
      const result = await window.goteet.request(
        'POST',
        ai ? '/api/system/analyse' : '/api/system/health',
        ai ? { provider, model } : {},
      );
      setHealth(ai ? result.evidence : result);
      setAnswer(ai ? result.answer : '');
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="system-review">
      <div className="section-title">
        <h2>Health & storage review</h2>
        <div className="button-row">
          <button disabled={busy} onClick={() => check()}>
            <Activity size={15} />
            Run health check
          </button>
          <button className="primary" disabled={busy} onClick={() => check(true)}>
            <Sparkles size={15} />
            Explain with AI
          </button>
        </div>
      </div>
      <p>
        Measure current resource use and review large files, older downloads, user caches and Trash. AI uses
        your selected assistant provider ({provider}).
      </p>
      {busy && (
        <p role="status">
          {provider === 'ollama' ? 'Checking your system…' : 'Reading system measurements…'}
        </p>
      )}
      {answer && (
        <div className="system-ai-answer">
          <h3>AI review</h3>
          <p>{answer}</p>
        </div>
      )}
      {health && (
        <>
          <div className="health-findings">
            {health.findings.map((f: Row) => (
              <article key={f.title}>
                <span className={'badge ' + (f.level === 'ok' ? 'ok' : 'warn')}>
                  {f.level === 'ok' ? 'Measured' : 'Review'}
                </span>
                <h3>{f.title}</h3>
                <p>{f.evidence}</p>
                <p>{f.next}</p>
              </article>
            ))}
          </div>
          <h3>Top memory users</h3>
          <div className="memory-processes">
            {health.top_memory.map((p: Row) => (
              <div key={p.pid}>
                <span>
                  {p.name}
                  <small>PID {p.pid}</small>
                </span>
                <div>
                  <span style={{ width: Math.min(100, (p.rss / health.metrics.memory.total) * 100) + '%' }} />
                </div>
                <strong>{gb(p.rss)}</strong>
              </div>
            ))}
          </div>
          <h3>Storage candidates to review</h3>
          {health.storage_reviews.map((folder: Row) => (
            <div className="storage-review" key={folder.path}>
              <div className="section-title">
                <div>
                  <strong>{folder.path.split('/').at(-1)}</strong>
                  <small>{folder.path}</small>
                </div>
                <button onClick={() => browse(folder.path)}>
                  <FolderOpen size={14} />
                  Inspect files
                </button>
              </div>
              <p>
                {gb(folder.bytes)} sampled · {folder.files} files · {gb(folder.old_bytes)} older than 90 days
                {folder.truncated ? ' · partial scan' : ''} · {folder.errors} access/read errors
              </p>
              {folder.large_files.slice(0, 5).map((f: Row) => (
                <button
                  className="large-file"
                  key={f.path}
                  onClick={() => browse(f.path.slice(0, f.path.lastIndexOf('/')))}
                >
                  <span>{f.name}</span>
                  <strong>{gb(f.size)}</strong>
                </button>
              ))}
            </div>
          ))}
          <p className="muted">{health.coverage}</p>
        </>
      )}
    </section>
  );
}
