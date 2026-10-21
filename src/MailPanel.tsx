import { useEffect, useRef, useState } from 'react';
type Row = Record<string, any>;
export function MailPanel({
  account,
  request,
  onConnections,
}: {
  account: string;
  request: (path: string, value?: unknown) => Promise<any>;
  onConnections: () => void;
}) {
  const [folder, setFolder] = useState('INBOX'),
    [query, setQuery] = useState(''),
    [search, setSearch] = useState(''),
    [rows, setRows] = useState<Row[]>([]),
    [next, setNext] = useState(''),
    [message, setMessage] = useState<Row | null>(null),
    [busy, setBusy] = useState(false),
    [reading, setReading] = useState(false),
    [error, setError] = useState(''),
    [excluded, setExcluded] = useState(0);
  const generation = useRef(0),
    reader = useRef(0);
  async function load(page = '') {
    const id = ++generation.current;
    setBusy(true);
    setError('');
    try {
      const data = await request('/api/mail?' + new URLSearchParams({ folder, query: search, page }));
      if (id !== generation.current) return;
      setRows((old) => (page ? [...old, ...data.messages] : data.messages));
      setNext(data.next);
      setExcluded(data.excluded);
    } catch (e) {
      if (id === generation.current) setError(String(e));
    } finally {
      if (id === generation.current) setBusy(false);
    }
  }
  useEffect(() => {
    setRows([]);
    setMessage(null);
    setReading(false);
    reader.current++;
    load();
    return () => {
      generation.current++;
      reader.current++;
    };
  }, [folder, search, account]);
  async function open(id: string) {
    const n = ++reader.current;
    setReading(true);
    setMessage(null);
    setError('');
    try {
      const data = await request('/api/mail/' + encodeURIComponent(id));
      if (n === reader.current) setMessage(data);
    } catch (e) {
      if (n === reader.current) setError(String(e));
    } finally {
      if (n === reader.current) setReading(false);
    }
  }
  return (
    <section className="mail-panel">
      <div className="section-title">
        <div>
          <h2>Mail</h2>
          <small>{account || 'Connect your Google account'}</small>
        </div>
        <button onClick={onConnections}>Account settings</button>
      </div>
      <div className="mail-tools">
        <div className="button-row">
          {[
            ['INBOX', 'Inbox'],
            ['STARRED', 'Starred'],
            ['SENT', 'Sent'],
            ['ALL', 'All mail'],
          ].map(([id, label]) => (
            <button key={id} aria-pressed={folder === id} onClick={() => setFolder(id)}>
              {label}
            </button>
          ))}
        </div>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setSearch(query);
          }}
        >
          <input
            aria-label="Search mail"
            placeholder="Search mail · from: or subject:"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <button type="submit">Search</button>
        </form>
        <button disabled={busy} onClick={() => load()}>
          Refresh
        </button>
      </div>
      <p className="muted">
        Read-only · messages load on demand · remote images and tracking are blocked · authentication,
        identity and payroll messages excluded.
      </p>
      {error && (
        <p role="alert" className="inline-note">
          {error}
        </p>
      )}
      <div className="mail-split">
        <div className="mail-list" aria-label="Message list">
          {rows.map((row) => (
            <button
              key={row.id}
              className={'mail-item ' + (message?.id === row.id ? 'selected' : '')}
              onClick={() => open(row.id)}
            >
              <span>
                {row.unread ? '● ' : ''}
                {row.from}
              </span>
              <strong>{row.subject}</strong>
              <small>{row.date}</small>
            </button>
          ))}
          {busy && <p role="status">Loading messages…</p>}
          {!busy && !rows.length && <p>No messages in this view.</p>}
          {next && (
            <button disabled={busy} onClick={() => load(next)}>
              Load more messages
            </button>
          )}
          {excluded > 0 && <p className="muted">{excluded} excluded on this page.</p>}
        </div>
        <article className="mail-reading" aria-label="Mail reading pane">
          {reading ? (
            <p role="status">Opening message…</p>
          ) : message ? (
            <>
              <h2>{message.subject}</h2>
              <p>
                <strong>From</strong> {message.from}
                <br />
                <strong>To</strong> {message.to}
                <br />
                {message.date}
              </p>
              <div className="button-row">
                <button onClick={() => window.workmate.external(message.url)}>Open in Gmail</button>
                <button onClick={() => window.workmate.copyText(message.text)}>Copy message text</button>
              </div>
              <div className="mail-body">{message.text || 'No readable text body in this message.'}</div>
              {message.truncated && <p>Showing the first 200 KB.</p>}
              {message.attachments?.length > 0 && (
                <div className="mail-attachments">
                  <h3>Attachments</h3>
                  {message.attachments.map((a: Row, i: number) => (
                    <div key={i}>
                      {a.name} · {(a.size / 1024).toFixed(0)} KB
                    </div>
                  ))}
                  <small>Attachment downloads are available in Gmail.</small>
                </div>
              )}
            </>
          ) : (
            <div className="empty">
              <h3>Your mail, right here.</h3>
              <p>Select a message to read it inside GOTEET.</p>
            </div>
          )}
        </article>
      </div>
    </section>
  );
}
