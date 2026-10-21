import { useEffect, useRef, useState, lazy, Suspense } from 'react';
import { ArrowLeft, ArrowRight, FolderOpen, Maximize2, Minus, Plus, X } from 'lucide-react';
type Row = Record<string, any>;
const PdfReader = lazy(() => import('./PdfReader'));
const WordReader = lazy(() => import('./WordReader'));
const ModelViewer = lazy(() => import('./ModelViewer'));
export function MediaViewer({
  initial,
  files,
  onChange,
  onClose,
  fail,
}: {
  initial: Row;
  files: Row[];
  onChange: (f: Row) => void;
  onClose: () => void;
  fail: (e: unknown) => void;
}) {
  const video = useRef<HTMLVideoElement>(null),
    modal = useRef<HTMLDialogElement>(null),
    [rotation, setRotation] = useState(0),
    [zoom, setZoom] = useState(0),
    [loaded, setLoaded] = useState(false),
    [error, setError] = useState(''),
    [dimensions, setDimensions] = useState('');
  const candidates = files.filter((f) => ['Image', 'Video', 'Audio'].includes(f.category)),
    index = candidates.findIndex((f) => f.path === initial.path);
  async function move(delta: number) {
    const file = candidates[index + delta];
    if (!file) return;
    try {
      onChange(await window.workmate.preview(file.path));
    } catch (e) {
      fail(e);
    }
  }
  useEffect(() => {
    modal.current?.showModal();
    return () => modal.current?.close();
  }, []);
  useEffect(() => {
    setZoom(0);
    setRotation(0);
    setLoaded(false);
    setError('');
    setDimensions('');
  }, [initial.path]);
  return (
    <dialog
      ref={modal}
      className="media-viewer"
      aria-labelledby="media-title"
      onCancel={onClose}
      onKeyDown={(e) => {
        if (
          e.target instanceof HTMLInputElement ||
          e.target instanceof HTMLSelectElement ||
          e.target instanceof HTMLTextAreaElement ||
          e.target instanceof HTMLVideoElement ||
          e.target instanceof HTMLAudioElement
        )
          return;
        if (e.key === 'ArrowLeft') move(-1);
        if (e.key === 'ArrowRight') move(1);
      }}
    >
      <header>
        <div className="viewer-title">
          <strong id="media-title">{initial.name}</strong>
          <small>
            {initial.mime_type} · {(initial.size / 1e6).toFixed(2)} MB{dimensions && ' · ' + dimensions}
          </small>
        </div>
        <button onClick={() => window.workmate.reveal(initial.path).catch(fail)}>
          <FolderOpen size={15} />
          Reveal
        </button>
        <button className="icon-button" autoFocus aria-label="Close media preview" onClick={onClose}>
          <X size={20} />
        </button>
      </header>
      <div className={'viewer-stage ' + (zoom ? 'actual-size' : '')}>
        {error ? (
          <div className="viewer-error">
            <h3>Preview unavailable</h3>
            <p>{error}</p>
            <button onClick={() => window.workmate.reveal(initial.path).catch(fail)}>
              Reveal original file
            </button>
          </div>
        ) : initial.kind === 'image' ? (
          <>
            <img
              key={initial.path}
              src={initial.url}
              alt={initial.name}
              style={{
                transform: `rotate(${rotation}deg)`,
                ...(zoom ? { maxWidth: 'none', maxHeight: 'none', width: zoom + '%' } : {}),
              }}
              onLoad={(e) => {
                setLoaded(true);
                setDimensions(e.currentTarget.naturalWidth + ' × ' + e.currentTarget.naturalHeight);
              }}
              onError={() =>
                setError('This image format could not be decoded. The original file is unchanged.')
              }
            />
            {!loaded && (
              <span className="viewer-loading" role="status">
                Loading image…
              </span>
            )}
          </>
        ) : initial.kind === 'video' ? (
          <video
            ref={video}
            key={initial.path}
            src={initial.url}
            controls
            playsInline
            preload="metadata"
            onLoadedMetadata={(e) => {
              setLoaded(true);
              setDimensions(e.currentTarget.videoWidth + ' × ' + e.currentTarget.videoHeight);
            }}
            onError={() =>
              setError(
                'This video codec is not supported by this desktop build. Use Reveal to play it in another app.',
              )
            }
          />
        ) : initial.kind === 'audio' ? (
          <div className="audio-preview">
            <h2>{initial.name}</h2>
            <audio
              key={initial.path}
              src={initial.url}
              controls
              preload="metadata"
              onError={() => setError('This audio codec is not supported by this desktop build.')}
            />
          </div>
        ) : initial.kind === 'model' ? (
          <Suspense fallback={<p>Opening 3D viewer…</p>}>
            <ModelViewer url={initial.url} name={initial.name} />
          </Suspense>
        ) : initial.mime_type === 'application/pdf' ? (
          <Suspense fallback={<p>Opening PDF…</p>}>
            <PdfReader url={initial.url} />
          </Suspense>
        ) : initial.blocks ? (
          <Suspense fallback={<p>Opening document…</p>}>
            <WordReader blocks={initial.blocks} />
          </Suspense>
        ) : initial.text !== undefined ? (
          <div className="text-preview">
            {initial.note && <p>{initial.note}</p>}
            <pre>{initial.text}</pre>
            {initial.truncated && <p>Showing the first 200 KB. Reveal the original for the complete file.</p>}
          </div>
        ) : (
          <p>Use Reveal to open this format in its own app.</p>
        )}
      </div>
      <footer>
        <div className="button-row">
          <button aria-label="Previous media" disabled={index <= 0} onClick={() => move(-1)}>
            <ArrowLeft size={16} />
          </button>
          <span>{index >= 0 ? `${index + 1} of ${candidates.length}` : 'Local preview'}</span>
          <button
            aria-label="Next media"
            disabled={index < 0 || index >= candidates.length - 1}
            onClick={() => move(1)}
          >
            <ArrowRight size={16} />
          </button>
        </div>
        {initial.kind === 'video' && (
          <div className="button-row">
            <button
              onClick={() => {
                if (video.current) video.current.currentTime = Math.max(0, video.current.currentTime - 10);
              }}
            >
              −10 s
            </button>
            <select
              aria-label="Playback speed"
              defaultValue="1"
              onChange={(e) => {
                if (video.current) video.current.playbackRate = Number(e.target.value);
              }}
            >
              {[0.5, 1, 1.5, 2].map((v) => (
                <option key={v} value={v}>
                  {v}×
                </option>
              ))}
            </select>
            <button
              onClick={() => {
                if (video.current)
                  video.current.currentTime = Math.min(
                    video.current.duration || 0,
                    video.current.currentTime + 10,
                  );
              }}
            >
              +10 s
            </button>
          </div>
        )}
        {initial.kind === 'image' && (
          <div className="button-row">
            <button onClick={() => setRotation((r) => (r + 90) % 360)}>Rotate view</button>
            <button
              aria-label="Zoom out"
              disabled={zoom === 0 || zoom <= 25}
              onClick={() => setZoom(Math.max(25, zoom - 25))}
            >
              <Minus size={14} />
            </button>
            <button onClick={() => setZoom(zoom ? 0 : 100)}>
              <Maximize2 size={14} />
              {zoom ? zoom + '%' : 'Fit'}
            </button>
            <button
              aria-label="Zoom in"
              disabled={zoom >= 300}
              onClick={() => setZoom(zoom ? Math.min(300, zoom + 25) : 100)}
            >
              <Plus size={14} />
            </button>
          </div>
        )}
        <span>Esc to close · ← → to browse</span>
      </footer>
    </dialog>
  );
}
