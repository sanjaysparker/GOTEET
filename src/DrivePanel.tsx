import { useEffect, useRef, useState } from 'react';
import {
  Folder,
  FileText,
  Image as ImageIcon,
  Film,
  Grid2X2,
  List,
  ChevronRight,
  RefreshCw,
} from 'lucide-react';
type Row = Record<string, any>;
const folderMime = 'application/vnd.google-apps.folder';
export function DrivePanel({
  account,
  request,
  onPreview,
  contentAccess,
}: {
  account: string;
  request: (path: string, value?: unknown) => Promise<any>;
  onPreview: (value: Row) => void;
  contentAccess: boolean;
}) {
  const [trail, setTrail] = useState([{ id: 'root', name: 'My Drive' }]),
    [rows, setRows] = useState<Row[]>([]),
    [thumbs, setThumbs] = useState<Record<string, string>>({}),
    [query, setQuery] = useState(''),
    [search, setSearch] = useState(''),
    [kind, setKind] = useState('all'),
    [order, setOrder] = useState('name'),
    [layout, setLayout] = useState('grid'),
    [next, setNext] = useState(''),
    [busy, setBusy] = useState(false),
    [opening, setOpening] = useState(''),
    [error, setError] = useState(''),
    [captured, setCaptured] = useState('');
  const generation = useRef(0),
    parent = trail[trail.length - 1].id;
  async function load(page = '') {
    const n = ++generation.current;
    setBusy(true);
    setError('');
    try {
      const r = await request(
        '/api/drive/files?' + new URLSearchParams({ parent, query: search, page, kind, order }),
      );
      if (n !== generation.current) return;
      setRows((old) => (page ? [...old, ...r.files] : r.files));
      setNext(r.next);
      setCaptured(new Date().toLocaleTimeString());
      if (r.incomplete)
        setError('Google reports an incomplete search. Open a specific folder to narrow the results.');
      const pending = r.files.filter((f: Row) => f.hasThumbnail);
      let i = 0;
      await Promise.all(
        Array.from({ length: 3 }, async () => {
          while (i < pending.length && n === generation.current) {
            const file = pending[i++];
            try {
              const t = await request('/api/drive/thumbnail/' + encodeURIComponent(file.id));
              if (n === generation.current && t.url) setThumbs((old) => ({ ...old, [file.id]: t.url }));
            } catch {}
          }
        }),
      );
    } catch (e) {
      if (n === generation.current)
        setError(String(e).replace(/^Error invoking remote method '[^']+': (?:Error: )?/, ''));
    } finally {
      if (n === generation.current) setBusy(false);
    }
  }
  useEffect(() => {
    setRows([]);
    setThumbs({});
    setNext('');
    load();
    return () => {
      generation.current++;
    };
  }, [parent, search, kind, order, account, contentAccess]);
  async function open(file: Row) {
    if (file.mimeType === folderMime) {
      setTrail((t) => [...t, { id: file.id, name: file.name }]);
      setSearch('');
      setQuery('');
      setKind('all');
      return;
    }
    setOpening(file.id);
    setError('');
    try {
      const r = await request('/api/drive/preview', { id: file.id });
      onPreview(await window.goteet.preview(r.path));
    } catch (e) {
      setError(String(e).replace(/^Error invoking remote method '[^']+': (?:Error: )?/, ''));
    } finally {
      setOpening('');
    }
  }
  return (
    <div className="drive-browser">
      <div className="section-title">
        <div>
          <h2>Drive</h2>
          <small>
            {account} · live folder browser{captured ? ' · refreshed ' + captured : ''}
          </small>
        </div>
        <button disabled={busy} aria-label="Refresh Drive folder" onClick={() => load()}>
          <RefreshCw size={15} />
        </button>
      </div>
      <div className="drive-toolbar">
        <select
          aria-label="Drive location"
          value={trail[0].id}
          onChange={(e) => {
            setTrail([{ id: e.target.value, name: e.target.selectedOptions[0].text }]);
            setQuery('');
            setSearch('');
          }}
        >
          <option value="root">My Drive</option>
          <option value="shared">Shared with me</option>
          <option value="recent">All accessible files</option>
        </select>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setSearch(query);
          }}
        >
          <input
            aria-label="Search this Drive folder"
            placeholder="Search this folder…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <button>Search</button>
        </form>
        <select aria-label="Drive file type" value={kind} onChange={(e) => setKind(e.target.value)}>
          {[
            ['all', 'All types'],
            ['image', 'Images'],
            ['video', 'Videos'],
            ['pdf', 'PDFs'],
            ['document', 'Documents'],
          ].map(([v, l]) => (
            <option key={v} value={v}>
              {l}
            </option>
          ))}
        </select>
        <select aria-label="Sort Drive files" value={order} onChange={(e) => setOrder(e.target.value)}>
          <option value="name">Name</option>
          <option value="modified">Recently modified</option>
          <option value="size">Largest first</option>
        </select>
        <button
          aria-label="Drive grid view"
          aria-pressed={layout === 'grid'}
          onClick={() => setLayout('grid')}
        >
          <Grid2X2 size={16} />
        </button>
        <button
          aria-label="Drive list view"
          aria-pressed={layout === 'list'}
          onClick={() => setLayout('list')}
        >
          <List size={16} />
        </button>
      </div>
      <nav className="drive-breadcrumbs" aria-label="Drive folder path">
        {trail.map((f, i) => (
          <span key={f.id}>
            {i > 0 && <ChevronRight size={13} />}
            <button onClick={() => setTrail((t) => t.slice(0, i + 1))}>{f.name}</button>
          </span>
        ))}
      </nav>
      {!contentAccess && (
        <p className="inline-note">
          Folder browsing is available. To open full files, click Enable Drive previews above and complete
          Google’s read-content consent. Drive then sets up automatically.
        </p>
      )}
      {error && (
        <p className="inline-note" role="alert">
          {error}
        </p>
      )}
      <div className={'drive-items ' + layout}>
        {rows.map((file) => {
          const Icon =
            file.mimeType === folderMime
              ? Folder
              : file.mimeType.startsWith('image/')
                ? ImageIcon
                : file.mimeType.startsWith('video/')
                  ? Film
                  : FileText;
          return (
            <button
              className="drive-file"
              key={file.id}
              onClick={() => open(file)}
              disabled={!!opening}
              aria-label={(file.mimeType === folderMime ? 'Open folder ' : 'Open file ') + file.name}
            >
              <div className={'drive-thumb ' + (file.mimeType === folderMime ? 'folder' : '')}>
                {thumbs[file.id] ? (
                  <img src={thumbs[file.id]} alt="" loading="lazy" />
                ) : (
                  <Icon size={file.mimeType === folderMime ? 36 : 30} />
                )}
              </div>
              <div className="drive-label">
                <strong title={file.name}>{file.name}</strong>
                <small>
                  {opening === file.id
                    ? 'Opening…'
                    : file.mimeType === folderMime
                      ? 'Folder'
                      : (file.size ? (Number(file.size) / 1048576).toFixed(1) + ' MB · ' : '') +
                        (file.modifiedTime ? new Date(file.modifiedTime).toLocaleDateString() : 'File')}
                </small>
              </div>
            </button>
          );
        })}
      </div>
      {busy && <p role="status">Loading Drive…</p>}
      {!busy && !rows.length && !error && (
        <div className="empty">
          <Folder size={30} />
          <h3>No files in this view</h3>
          <p>Try another folder or clear your filters.</p>
        </div>
      )}
      {next && (
        <button disabled={busy} onClick={() => load(next)}>
          Load more files
        </button>
      )}
      <small>
        Read-only · thumbnails supplied by Google when available · click a folder to browse or a file to
        preview.
      </small>
    </div>
  );
}
