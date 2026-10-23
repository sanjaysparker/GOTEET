import { useEffect, useState, useRef } from 'react';
import { ArrowUp, Copy, File, Folder, FolderOpen, RefreshCw, Share2, Trash2 } from 'lucide-react';
type Row = Record<string, any>;
const api = (route: string) => window.goteet.request('GET', route);
export function FilesPanel({
  initialPath,
  preview,
  fail,
  onPath,
  query,
  setQuery,
}: {
  query: string;
  setQuery: (value: string) => void;
  initialPath: string;
  preview: (f: Row) => void;
  fail: (e: unknown) => void;
  onPath: (path: string) => void;
}) {
  const [path, setPath] = useState(initialPath),
    [address, setAddress] = useState(initialPath),
    [listing, setListing] = useState<Row | null>(null),
    [hidden, setHidden] = useState(false),
    [sort, setSort] = useState('name'),
    [offset, setOffset] = useState(0),
    [selected, setSelected] = useState<Row | null>(null),
    [busy, setBusy] = useState(false),
    [notice, setNotice] = useState('');
  const request = useRef(0);
  const load = async () => {
    const sequence = ++request.current;
    setBusy(true);
    try {
      const value = await api(
        '/api/files?' +
          new URLSearchParams({ path, query, hidden: String(hidden), sort, offset: String(offset) }),
      );
      if (sequence !== request.current) return;
      setListing(value);
      setAddress(value.path);
      onPath(value.path);
      setSelected(null);
    } catch (e) {
      fail(e);
    } finally {
      if (sequence === request.current) setBusy(false);
    }
  };
  useEffect(() => {
    setPath(initialPath);
    setOffset(0);
  }, [initialPath]);
  useEffect(() => {
    load();
  }, [path, query, hidden, sort, offset]);
  function go(folder: string) {
    setPath(folder);
    setOffset(0);
    setQuery('');
  }
  async function open(item: Row) {
    if (item.kind === 'Folder') {
      go(item.path);
      return;
    }
    if (!item.previewable) {
      setSelected(item);
      setNotice('Select Reveal to open this file in its own app.');
      return;
    }
    try {
      preview(await window.goteet.browsePreview(item.path));
    } catch (e) {
      fail(e);
    }
  }
  async function action(name: string) {
    if (!selected) return;
    setBusy(true);
    try {
      const result = await window.goteet.fileAction(name, selected.path);
      setNotice(result.message);
      if (name === 'trash') await load();
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="files-panel">
      <div className="file-places">
        {listing?.roots.map((r: Row) => (
          <button
            key={r.path}
            className={listing.path === r.path ? 'selected' : ''}
            onClick={() => go(r.path)}
          >
            <Folder size={14} />
            {r.name}
          </button>
        ))}
      </div>
      <form
        className="file-address"
        onSubmit={(e) => {
          e.preventDefault();
          go(address);
        }}
      >
        <button
          type="button"
          aria-label="Parent folder"
          disabled={!listing || listing.path === listing.parent}
          onClick={() => go(listing!.parent)}
        >
          <ArrowUp size={16} />
        </button>
        <input aria-label="Folder path" value={address} onChange={(e) => setAddress(e.target.value)} />
        <button>Go</button>
        <button type="button" aria-label="Refresh folder" disabled={busy} onClick={load}>
          <RefreshCw size={16} />
        </button>
      </form>
      <div className="library-tools">
        <label>
          Search this folder
          <input
            type="search"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setOffset(0);
            }}
            placeholder="Filename…"
          />
        </label>
        <label>
          Sort
          <select value={sort} onChange={(e) => setSort(e.target.value)}>
            <option value="name">Folders & name</option>
            <option value="size">Largest first</option>
            <option value="modified">Recently modified</option>
          </select>
        </label>
        <label className="check-label">
          <input type="checkbox" checked={hidden} onChange={(e) => setHidden(e.target.checked)} />
          Show hidden
        </label>
      </div>
      <div className="file-actions">
        <span>{selected ? selected.name : 'Select an item for actions'}</span>
        <button disabled={!selected || busy} onClick={() => action('copy-path')}>
          <Copy size={14} />
          Copy path
        </button>
        <button
          disabled={!selected || selected.kind !== 'File' || selected.is_symlink || busy}
          onClick={() => action('copy')}
        >
          <Copy size={14} />
          Copy file…
        </button>
        <button disabled={!selected || busy} onClick={() => action('share')}>
          <Share2 size={14} />
          Share…
        </button>
        <button disabled={!selected || busy} onClick={() => action('reveal')}>
          <FolderOpen size={14} />
          Reveal
        </button>
        <button disabled={!selected || busy} onClick={() => action('trash')}>
          <Trash2 size={14} />
          Trash…
        </button>
      </div>
      {notice && (
        <p role="status" className="inline-note">
          {notice}
        </p>
      )}
      {busy && <p role="status">Reading folder…</p>}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Kind</th>
              <th>Size</th>
              <th>Modified</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {listing?.items.map((item: Row) => (
              <tr
                key={item.path}
                className={selected?.path === item.path ? 'file-selected' : ''}
                onClick={() => setSelected(item)}
              >
                <td>
                  <button className="media-name file-name" onClick={() => open(item)}>
                    {item.kind === 'Folder' ? <Folder size={17} /> : <File size={17} />}
                    <span>
                      {item.name}
                      {item.is_symlink ? ' ↗' : ''}
                    </span>
                  </button>
                  <small className="path" title={item.path}>
                    {item.path}
                  </small>
                </td>
                <td>{item.kind}</td>
                <td>{item.kind === 'Folder' ? '—' : (item.size / 1e6).toFixed(2) + ' MB'}</td>
                <td>{new Date(item.modified * 1000).toLocaleDateString()}</td>
                <td>
                  <button aria-label={'Select ' + item.name} onClick={() => setSelected(item)}>
                    Actions
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="folder-footer">
        <span>
          {listing?.total || 0} items · {listing?.unreadable || 0} unreadable
          {listing?.truncated ? ' · folder listing capped at 20,000 entries' : ''}
        </span>
        <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 200))}>
          Previous
        </button>
        <button disabled={!listing || offset + 200 >= listing.total} onClick={() => setOffset(offset + 200)}>
          Next
        </button>
      </div>
      <p className="muted">
        Browse on demand with this user’s OS access. Trash is recoverable; system and application-data
        locations are protected. Copy supports regular files.
      </p>
    </div>
  );
}
