import { useEffect, useRef, useState } from 'react';
import { FileText } from 'lucide-react';
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url';
let active = 0;
const queue: Array<() => void> = [];
async function bounded<T>(work: () => Promise<T>): Promise<T> {
  if (active >= 2) await new Promise<void>((resolve) => queue.push(resolve));
  active++;
  try {
    return await work();
  } finally {
    active--;
    queue.shift()?.();
  }
}
export default function DocumentThumbnail({ file }: { file: Record<string, any> }) {
  const root = useRef<HTMLSpanElement>(null),
    canvas = useRef<HTMLCanvasElement>(null);
  const [ready, setReady] = useState(false),
    [text, setText] = useState(''),
    [image, setImage] = useState(''),
    [failed, setFailed] = useState(false);
  useEffect(() => {
    let cancelled = false,
      started = false;
    const abort = new AbortController();
    let task: any, render: any;
    setReady(false);
    setFailed(false);
    setImage('');
    setText('');
    const observer = new IntersectionObserver(
      (entries) => {
        if (started || !entries.some((e) => e.isIntersecting)) return;
        started = true;
        observer.disconnect();
        bounded(async () => {
          if (cancelled) return;
          if (file.source === 'Drive') {
            const result = await window.goteet.request(
              'GET',
              '/api/drive/thumbnail/' + encodeURIComponent(file.id),
            );
            if (!cancelled && result.url) {
              setImage(result.url);
              setReady(true);
            }
            return;
          }
          const info = await window.goteet.preview(file.path);
          if (cancelled) return;
          if (info.mime_type === 'application/pdf') {
            if (info.size > 25000000) throw Error('Large PDF');
            const pdf = await import('pdfjs-dist');
            pdf.GlobalWorkerOptions.workerSrc = workerUrl;
            const response = await fetch(info.url, { signal: abort.signal });
            if (!response.ok) throw Error('Unavailable');
            const data = new Uint8Array(await response.arrayBuffer());
            if (cancelled) return;
            task = pdf.getDocument({ data });
            const doc = await task.promise;
            const page = await doc.getPage(1);
            if (cancelled || !canvas.current) return;
            const base = page.getViewport({ scale: 1 }),
              viewport = page.getViewport({ scale: Math.min(320 / base.width, 420 / base.height) });
            canvas.current.width = viewport.width;
            canvas.current.height = viewport.height;
            render = page.render({ canvas: canvas.current, viewport });
            await render.promise;
            if (!cancelled) setReady(true);
          } else {
            const paragraphs = (info.blocks || [])
              .flatMap((b: any) => b.runs?.map((r: any) => r.text) || [])
              .join(' ');
            const content = paragraphs || info.text || '';
            if (!content.trim()) throw Error('No text');
            if (!cancelled) {
              setText(content.slice(0, 700));
              setReady(true);
            }
          }
        })
          .catch(() => {
            if (!cancelled) setFailed(true);
          })
          .finally(() => {
            task?.destroy();
          });
      },
      { rootMargin: '80px' },
    );
    if (root.current) observer.observe(root.current);
    return () => {
      cancelled = true;
      abort.abort();
      observer.disconnect();
      render?.cancel();
      task?.destroy();
    };
  }, [file.path, file.id, file.modified, file.source]);
  return (
    <span
      ref={root}
      className="document-thumbnail"
      aria-label={
        ready
          ? 'Document content preview'
          : failed
            ? 'Preview unavailable — click to open'
            : 'Loading document preview'
      }
    >
      {image ? (
        <img src={image} alt="" />
      ) : text ? (
        <span className="document-thumbnail-text">{text}</span>
      ) : (
        <canvas ref={canvas} style={{ display: ready ? 'block' : 'none' }} />
      )}
      {!ready && (
        <span className="document-thumbnail-fallback">
          <FileText size={24} />
          <small>{failed ? 'Click to open' : 'Loading preview…'}</small>
        </span>
      )}
    </span>
  );
}
