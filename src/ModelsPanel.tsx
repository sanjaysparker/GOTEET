import { useEffect, useState } from 'react';
import { Check, Download, ExternalLink, LogIn, RefreshCw } from 'lucide-react';
type Row = Record<string, any>;
const api = (route: string, value?: unknown) =>
  window.goteet.request(value === undefined ? 'GET' : 'POST', route, value);
export function ModelsPanel({
  useModel,
  fail,
}: {
  useModel: (provider: string, model?: string) => void;
  fail: (e: unknown) => void;
}) {
  const [data, setData] = useState<Row | null>(null),
    [tab, setTab] = useState('accounts'),
    [provider, setProvider] = useState('nvidia'),
    [key, setKey] = useState(''),
    [model, setModel] = useState(''),
    [localName, setLocalName] = useState(''),
    [catalog, setCatalog] = useState<string[]>([]),
    [busy, setBusy] = useState(''),
    [notice, setNotice] = useState(''),
    [jobs, setJobs] = useState<Row[]>([]);
  async function load() {
    const value = await api('/api/models');
    setData(value);
    setJobs(value.downloads || []);
    return value;
  }
  async function run(label: string, work: () => Promise<unknown>) {
    setBusy(label);
    setNotice('');
    try {
      await work();
    } catch (e) {
      fail(e);
    } finally {
      setBusy('');
    }
  }
  useEffect(() => {
    load().catch(fail);
  }, []);
  useEffect(() => {
    let active = true;
    const timer = setInterval(
      () =>
        api('/api/models/downloads')
          .then((v) => {
            if (active) setJobs(v);
          })
          .catch(() => {}),
      2500,
    );
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, []);
  useEffect(() => {
    setKey('');
    setCatalog([]);
    setModel(data?.providers?.find((p: Row) => p.id === provider)?.model || '');
  }, [provider, data]);
  const selected = data?.providers?.find((p: Row) => p.id === provider);
  if (!data) return <p role="status">Checking model connections…</p>;
  return (
    <div className="models-panel">
      <div className="models-tabs" role="tablist" aria-label="Model setup">
        <button
          role="tab"
          aria-selected={tab === 'accounts'}
          className={tab === 'accounts' ? 'active' : ''}
          onClick={() => setTab('accounts')}
        >
          Accounts & API
        </button>
        <button
          role="tab"
          aria-selected={tab === 'local'}
          className={tab === 'local' ? 'active' : ''}
          onClick={() => setTab('local')}
        >
          Local models
        </button>
        <button onClick={() => run('Refreshing', load)} disabled={!!busy}>
          <RefreshCw size={14} />
          Refresh status
        </button>
      </div>
      {notice && (
        <p role="status" className="inline-note">
          {notice}
        </p>
      )}
      {tab === 'accounts' ? (
        <>
          <section>
            <h2>Use an existing AI account</h2>
            <p>CLI accounts use their own browser login and account entitlements.</p>
            {['codex', 'claude'].map((name) => (
              <div className="model-account" key={name}>
                <div>
                  <strong>{name === 'codex' ? 'Codex' : 'Claude Code'}</strong>
                  <small>
                    {!data.cli[name].installed
                      ? 'CLI not installed'
                      : data.cli[name].logged_in
                        ? 'Signed in'
                        : 'Sign-in required'}
                  </small>
                </div>
                <button
                  disabled={!!busy || !data.cli[name].installed}
                  onClick={() =>
                    run('Opening sign-in', async () => {
                      const v = await api('/api/models/login', { provider: name });
                      setNotice(v.message || 'Sign-in is already open.');
                    })
                  }
                >
                  <LogIn size={14} />
                  {data.cli[name].logged_in ? 'Sign in again' : 'Browser sign-in'}
                </button>
                <button disabled={!data.cli[name].logged_in} onClick={() => useModel(name)}>
                  Use in assistant
                </button>
              </div>
            ))}
          </section>
          <section>
            <h2>Connect an API provider</h2>
            <p>
              Keys stay in your OS credential store. Cloud requests send the workspace evidence included in
              your request to the selected provider; its account limits and pricing apply.
            </p>
            <div className="model-form">
              <label>
                Provider
                <select value={provider} onChange={(e) => setProvider(e.target.value)}>
                  {data.providers.map((p: Row) => (
                    <option value={p.id} key={p.id}>
                      {p.name}
                      {p.configured ? ' · connected' : ''}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                API key
                <input
                  type="password"
                  autoComplete="off"
                  spellCheck={false}
                  value={key}
                  onChange={(e) => setKey(e.target.value)}
                  placeholder={
                    selected?.configured
                      ? 'Saved in keychain · enter only to replace'
                      : 'Paste provider API key'
                  }
                />
              </label>
              <label>
                Model ID
                <input
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  placeholder="Exact model ID from the provider"
                  list="provider-models"
                />
                <datalist id="provider-models">
                  {catalog.map((m) => (
                    <option key={m} value={m} />
                  ))}
                </datalist>
              </label>
            </div>
            <div className="button-row">
              <button
                className="primary"
                disabled={!!busy || !model.trim() || (!key && !selected?.configured)}
                onClick={() =>
                  run('Saving provider', async () => {
                    await api('/api/models/provider', { provider, api_key: key, model });
                    setKey('');
                    await load();
                    setNotice('Provider saved to the OS credential store.');
                  })
                }
              >
                <Check size={14} />
                Save provider
              </button>
              <button
                disabled={!!busy || !selected?.configured}
                onClick={() =>
                  run('Verifying provider', async () => {
                    const result = await api('/api/models/verify', { provider });
                    setCatalog(result.models);
                    setNotice('Provider verified · ' + result.models.length + ' model IDs available.');
                  })
                }
              >
                Verify & list models
              </button>
              <button disabled={!selected?.configured} onClick={() => useModel(provider, selected.model)}>
                Use in assistant
              </button>
              <button onClick={() => window.goteet.external(selected.site).catch(fail)}>
                <ExternalLink size={14} />
                Get API key
              </button>
              {selected?.configured && (
                <button
                  disabled={!!busy}
                  onClick={() =>
                    run('Disconnecting', async () => {
                      await api('/api/models/disconnect', { provider });
                      await load();
                      setNotice('Provider key removed from GOTEET.');
                    })
                  }
                >
                  Disconnect
                </button>
              )}
            </div>
            <small>{selected?.base}</small>
          </section>
        </>
      ) : (
        <>
          <section>
            <div className="section-title">
              <h2>Models on this computer</h2>
              <span>{data.ollama.online ? 'Ollama running' : 'Ollama offline'}</span>
            </div>
            {!data.ollama.online && (
              <div className="button-row">
                <button
                  disabled={!!busy || !data.ollama.installed}
                  onClick={() =>
                    run('Starting Ollama', async () => {
                      await api('/api/models/ollama/start', {});
                      setNotice('Ollama is starting. Refresh status in a moment.');
                    })
                  }
                >
                  Start Ollama
                </button>
                <button onClick={() => window.goteet.external('https://ollama.com/download').catch(fail)}>
                  Get Ollama
                </button>
              </div>
            )}
            {data.ollama.models.length ? (
              data.ollama.models.map((m: Row) => (
                <div className="model-account" key={m.name}>
                  <div>
                    <strong>{m.name}</strong>
                    <small>
                      {(m.size / 1e9).toFixed(2)} GB · {m.details.parameter_size || 'Local model'} ·{' '}
                      {m.details.quantization_level || ''}
                    </small>
                  </div>
                  <button onClick={() => useModel('ollama', m.name)}>Use in assistant</button>
                </div>
              ))
            ) : (
              <p>No downloaded models detected. Download a model below, then refresh status.</p>
            )}
          </section>
          <section>
            <h2>Download an open-weight model</h2>
            <p>
              Use a model ID from the Ollama library or a public Hugging Face GGUF repository. Check its size,
              license and hardware needs before downloading.
            </p>
            <label className="setting-field">
              Model or GGUF repository
              <input
                value={localName}
                onChange={(e) => setLocalName(e.target.value)}
                placeholder="qwen3:0.6b or hf.co/owner/repository:Q4_K_M"
              />
            </label>
            <div className="button-row">
              <button
                className="primary"
                disabled={
                  !!busy ||
                  !data.ollama.online ||
                  !localName.trim() ||
                  jobs.some((j) => ['queued', 'downloading'].includes(j.status))
                }
                onClick={() =>
                  run('Starting download', async () => {
                    const job = await api('/api/models/pull', { model: localName });
                    setJobs([...jobs.filter((j) => j.id !== job.id), job]);
                    setNotice(
                      'Download started. Progress appears below; models stay in Ollama’s local storage.',
                    );
                  })
                }
              >
                <Download size={14} />
                Download model
              </button>
              <button onClick={() => window.goteet.external('https://ollama.com/library').catch(fail)}>
                <ExternalLink size={14} />
                Ollama library
              </button>
              <button
                onClick={() =>
                  window.goteet.external('https://huggingface.co/models?library=gguf').catch(fail)
                }
              >
                <ExternalLink size={14} />
                Hugging Face GGUF
              </button>
            </div>
            {jobs.map((job) => (
              <div className="model-download" key={job.id}>
                <strong>{job.name}</strong>
                <small>
                  {job.detail}
                  {job.total > 0
                    ? ' · ' + Math.min(100, Math.round((job.completed / job.total) * 100)) + '%'
                    : ''}
                </small>
                {job.total > 0 && (
                  <progress
                    aria-label={'Download progress for ' + job.name}
                    value={job.completed}
                    max={job.total}
                  />
                )}
                <span>{job.status}</span>
              </div>
            ))}
          </section>
        </>
      )}
      {busy && <p role="status">{busy}…</p>}
    </div>
  );
}
