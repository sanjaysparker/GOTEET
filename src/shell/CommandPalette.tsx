import React, { useEffect, useMemo, useRef, useState } from 'react';
import { CornerDownLeft, Search, Sparkles } from 'lucide-react';

export type Command = {
  id: string;
  label: string;
  hint?: string;
  group: string;
  icon?: React.ReactNode;
  run: () => void;
};

// ONE ENTRY POINT FOR EVERYTHING (Linear/Raycast pattern): views, records, actions and the agent.
// Unmatched text falls through to the agent so a question never dead-ends.
export function CommandPalette({
  open,
  close,
  commands,
  ask,
}: {
  open: boolean;
  close: () => void;
  commands: Command[];
  ask: (q: string) => void;
}) {
  const [q, setQ] = useState('');
  const [i, setI] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (open) {
      setQ('');
      setI(0);
      setTimeout(() => input.current?.focus(), 0);
    }
  }, [open]);
  const results = useMemo(() => {
    const t = q.trim().toLowerCase();
    if (!t) return commands.filter((c) => c.group !== 'Task').slice(0, 14);
    const words = t.split(/\s+/);
    return commands
      .filter((c) =>
        words.every((w) => (c.label + ' ' + c.group + ' ' + (c.hint || '')).toLowerCase().includes(w)),
      )
      .slice(0, 14);
  }, [q, commands]);
  if (!open) return null;
  const choose = (k: number) => {
    const c = results[k];
    close();
    if (c) c.run();
    else if (q.trim()) ask(q.trim());
  };
  let lastGroup = '';
  return (
    <div className="palette-backdrop" onMouseDown={(e) => e.target === e.currentTarget && close()}>
      <div className="palette" role="dialog" aria-modal="true" aria-label="Command palette">
        <label className="palette-input">
          <Search size={16} />
          <input
            ref={input}
            value={q}
            placeholder="Jump to a view, find a task, run an action, or ask the agent…"
            onChange={(e) => {
              setQ(e.target.value);
              setI(0);
            }}
            onKeyDown={(e) => {
              if (e.nativeEvent.isComposing) return;
              if (e.key === 'Escape') close();
              else if (e.key === 'ArrowDown') {
                e.preventDefault();
                setI(Math.min(i + 1, results.length - 1));
              } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                setI(Math.max(i - 1, 0));
              } else if (e.key === 'Enter') {
                e.preventDefault();
                choose(e.metaKey || !results.length ? -1 : i);
              }
            }}
            aria-activedescendant={results[i] ? 'cmd-' + results[i].id : undefined}
          />
          <kbd>esc</kbd>
        </label>
        <div className="palette-list" role="listbox">
          {results.map((c, k) => {
            const head = c.group !== lastGroup ? (lastGroup = c.group) : '';
            return (
              <React.Fragment key={c.id}>
                {head && <div className="palette-group micro-label">{head}</div>}
                <button
                  id={'cmd-' + c.id}
                  role="option"
                  aria-selected={k === i}
                  className="palette-item"
                  onMouseMove={() => setI(k)}
                  onClick={() => choose(k)}
                >
                  {c.icon}
                  <span className="grow">{c.label}</span>
                  {c.hint && <kbd>{c.hint}</kbd>}
                </button>
              </React.Fragment>
            );
          })}
          {q.trim() && (
            <button
              className={'palette-item ask ' + (!results.length ? 'selected' : '')}
              aria-selected={!results.length}
              onClick={() => choose(-1)}
            >
              <Sparkles size={15} />
              <span className="grow">Ask the agent: “{q.trim()}”</span>
              <kbd>
                <CornerDownLeft size={11} />
              </kbd>
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
