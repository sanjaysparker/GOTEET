import { useEffect, useRef, useState } from 'react';
import { getDocument, GlobalWorkerOptions, type PDFDocumentProxy } from 'pdfjs-dist';
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url';
GlobalWorkerOptions.workerSrc = workerUrl;
export default function PdfReader({ url }: { url: string }) {
  const canvas = useRef<HTMLCanvasElement>(null),
    [doc, setDoc] = useState<PDFDocumentProxy | null>(null),
    [page, setPage] = useState(1),
    [zoom, setZoom] = useState(1),
    [text, setText] = useState(''),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(true),
    [showText, setShowText] = useState(false);
  useEffect(() => {
    let alive = true;
    let task: ReturnType<typeof getDocument> | undefined;
    setError('');
    setDoc(null);
    setPage(1);
    fetch(url)
      .then(async (r) => {
        if (!r.ok) throw Error('PDF unavailable');
        const data = new Uint8Array(await r.arrayBuffer());
        if (!alive) return;
        task = getDocument({ data });
        const value = await task.promise;
        if (alive) setDoc(value);
      })
      .catch((e) => {
        if (alive) setError(String(e));
      });
    return () => {
      alive = false;
      task?.destroy();
    };
  }, [url]);
  useEffect(() => {
    if (!doc) return;
    let cancelled = false;
    let render: any;
    setBusy(true);
    (async () => {
      const p = await doc.getPage(page);
      if (cancelled || !canvas.current) return;
      const viewport = p.getViewport({ scale: zoom * 1.2 });
      canvas.current.width = viewport.width;
      canvas.current.height = viewport.height;
      render = p.render({ canvas: canvas.current, viewport });
      await render.promise;
      const content = await p.getTextContent();
      if (!cancelled) {
        setText(content.items.map((v: any) => v.str || '').join(' '));
        setBusy(false);
      }
    })().catch((e) => {
      if (!cancelled) {
        setError(String(e));
        setBusy(false);
      }
    });
    return () => {
      cancelled = true;
      render?.cancel();
    };
  }, [doc, page, zoom]);
  return (
    <div className="document-reader">
      <div className="document-tools">
        <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
          Previous page
        </button>
        <label>
          Page{' '}
          <input
            aria-label="PDF page"
            type="number"
            min={1}
            max={doc?.numPages || 1}
            value={page}
            onChange={(e) => setPage(Math.max(1, Math.min(doc?.numPages || 1, Number(e.target.value) || 1)))}
          />
        </label>
        <span>of {doc?.numPages || '…'}</span>
        <button disabled={!doc || page >= doc.numPages} onClick={() => setPage((p) => p + 1)}>
          Next page
        </button>
        <select aria-label="PDF zoom" value={zoom} onChange={(e) => setZoom(Number(e.target.value))}>
          {[0.5, 0.75, 1, 1.25, 1.5, 2].map((z) => (
            <option key={z} value={z}>
              {z * 100}%
            </option>
          ))}
        </select>
        <button aria-pressed={showText} onClick={() => setShowText((v) => !v)}>
          Page text
        </button>
      </div>
      {error ? (
        <p role="alert">{error}</p>
      ) : (
        <>
          {busy && <small role="status">Rendering page…</small>}
          <div className="document-scroll">
            <canvas ref={canvas} aria-label={'PDF page ' + page} />
            {showText && <div className="document-text">{text || 'No extractable text on this page.'}</div>}
          </div>
        </>
      )}
    </div>
  );
}
