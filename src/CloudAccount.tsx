import { useEffect, useState } from 'react';
import { api, cleanError, type Row } from './lib/api';

/** Account identity is separate from private Google source imports. */
export function CloudAccount() {
  const [account, setAccount] = useState<Row | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [waiting, setWaiting] = useState(false);
  const [spaces, setSpaces] = useState<Row[]>([]);
  useEffect(() => {
    let alive = true, loading = false;
    const load = async () => {
      if (loading) return;
      loading = true;
      try {
        const next = await api('/api/cloud/status');
        const rows = next.connected ? await api('/api/cloud/workspaces') : [];
        if (alive) { setAccount(next); setSpaces(rows); setError(''); if (next.connected) setWaiting(false); }
      } catch (e) { if (alive) setError(cleanError(e)); }
      finally { loading = false; }
    };
    void load();
    const timer = window.setInterval(load, waiting ? 5000 : 30000);
    window.addEventListener('focus', load);
    return () => { alive = false; window.clearInterval(timer); window.removeEventListener('focus', load); };
  }, [waiting]);
  async function login() {
    setBusy(true); setError('');
    try {
      const result = await api('/api/cloud/start', {});
      await window.goteet.external(result.url);
      setWaiting(true);
    } catch (e) { setError(cleanError(e)); }
    finally { setBusy(false); }
  }
  async function logout() {
    setBusy(true);
    try {
      const result = await api('/api/cloud/logout', {});
      setAccount(null); setSpaces([]); setWaiting(false); setError(result.warning || '');
    } catch (e) { setError(cleanError(e)); }
    finally { setBusy(false); }
  }
  return <section aria-label="GOTEET cloud account" style={{ marginBottom: 32 }}>
    <div className="section-title"><h2>Your GOTEET account</h2>
      <span className="badge">{account?.connected ? 'Signed in to cloud' : 'Cloud workspace'}</span>
    </div>
    <p>{account?.connected ? account.profile?.email : 'One account for your shared team workspaces, across devices.'}</p>
    {account?.connected ? <>
      <p>{spaces.length ? `${spaces.length} shared workspace${spaces.length === 1 ? '' : 's'} available` : 'No shared workspaces yet.'}</p>
      {spaces.map(space => <p key={space.id}>{space.name}</p>)}
      <button disabled={busy} onClick={logout}>Sign out of GOTEET cloud</button>
    </> : <button className="primary" disabled={busy} onClick={login}>Continue with Google</button>}
    {waiting && <p role="status">Finish sign-in in your browser. GOTEET will detect your account automatically.</p>}
    {account && !account.connected && !account.ready && <p>Google cloud login is awaiting provider setup by the app administrator.</p>}
    {error && <p role="alert">{error}</p>}
    <p className="muted">Google sign-in shares your name and email. Mail, Drive and Calendar access is managed separately below. Personal files and activity are not uploaded by signing in.</p>
  </section>;
}
