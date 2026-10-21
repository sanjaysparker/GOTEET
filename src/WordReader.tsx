import { useState } from 'react';
type Row = Record<string, any>;
export default function WordReader({ blocks }: { blocks: Row[] }) {
  const [zoom, setZoom] = useState(1),
    [query, setQuery] = useState('');
  function para(block: Row, index: number) {
    const content = block.runs?.map((r: Row, i: number) => (
      <span
        key={i}
        style={{ fontWeight: r.bold ? 700 : undefined, fontStyle: r.italic ? 'italic' : undefined }}
      >
        {r.text}
      </span>
    ));
    return block.type === 'heading' ? (
      <h2 id={'word-heading-' + index} key={index}>
        {content}
      </h2>
    ) : (
      <p key={index}>{content}</p>
    );
  }
  const filtered = query
    ? blocks.filter((b) => JSON.stringify(b).toLowerCase().includes(query.toLowerCase()))
    : blocks;
  return (
    <div className="document-reader">
      <div className="document-tools">
        <input
          aria-label="Find in Word document"
          placeholder="Find paragraphs…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <select aria-label="Word zoom" value={zoom} onChange={(e) => setZoom(Number(e.target.value))}>
          {[0.75, 1, 1.25, 1.5].map((z) => (
            <option key={z} value={z}>
              {z * 100}%
            </option>
          ))}
        </select>
        <span>{blocks.length} blocks</span>
        {!query && (
          <select
            aria-label="Document outline"
            defaultValue=""
            onChange={(e) => document.getElementById(e.target.value)?.scrollIntoView({ block: 'start' })}
          >
            <option value="" disabled>
              Jump to heading
            </option>
            {blocks.map((b, i) =>
              b.type === 'heading' ? (
                <option key={i} value={'word-heading-' + i}>
                  {b.runs.map((r: Row) => r.text).join('')}
                </option>
              ) : null,
            )}
          </select>
        )}
      </div>
      <div className="document-scroll">
        <article className="word-page" style={{ fontSize: 16 * zoom }}>
          {filtered.map((b, i) =>
            b.type === 'table' ? (
              <table key={i}>
                <tbody>
                  {b.rows.map((row: Row[][], j: number) => (
                    <tr key={j}>
                      {row.map((cell: any[], k: number) => (
                        <td key={k}>{cell.map(para)}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              para(b, i)
            ),
          )}
          {!filtered.length && <p>No matching paragraphs.</p>}
        </article>
      </div>
      <small>
        Reading view · headings, text emphasis and tables · embedded images and exact Word pagination are not
        rendered.
      </small>
    </div>
  );
}
