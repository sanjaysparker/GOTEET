import { useState } from 'react';
import { CheckCircle2, CalendarDays, ListChecks, Folder, Clock3, Plus, X } from 'lucide-react';
type Row = Record<string, any>;
export function WorkItemDetails({
  type,
  data,
  tasks,
  projects,
  change,
  openTask,
}: {
  type: string;
  data: Row;
  tasks: Row[];
  projects: Row[];
  change: (key: string, value: any) => void;
  openTask: (task: Row) => void;
}) {
  const [entry, setEntry] = useState('');
  const linked = tasks.filter((t) => t.project === (type === 'project' ? data.name : data.project));
  const checks: Row[] = data.checklist || [],
    complete = checks.filter((c) => c.done).length;
  const done = linked.filter((t) => t.status === 'Done').length;
  const project = projects.find((p) => p.name === data.project);
  const when = (value: string) => (value ? new Date(value).toLocaleString() : 'Not recorded');
  return (
    <div className="work-detail-overview">
      <div className="detail-eyebrow">
        <Folder size={14} />
        {type === 'task' ? data.project || 'General' : 'Project workspace'}
        <span>{data.id ? data.id.slice(0, 8).toUpperCase() : 'UNSAVED'}</span>
      </div>
      <div className="detail-metrics">
        <div>
          <CheckCircle2 size={18} />
          <strong>{data.status || (type === 'task' ? 'Todo' : 'Planned')}</strong>
          <small>Current status</small>
        </div>
        <div>
          <CalendarDays size={18} />
          <strong>{(type === 'task' ? data.due : data.target_date) || 'Unscheduled'}</strong>
          <small>{type === 'task' ? 'Due date' : 'Target date'}</small>
        </div>
        <div>
          <ListChecks size={18} />
          <strong>{type === 'task' ? `${complete}/${checks.length}` : `${done}/${linked.length}`}</strong>
          <small>{type === 'task' ? 'Checklist complete' : 'Tasks complete'}</small>
        </div>
      </div>
      {type === 'task' && (
        <>
          <label>
            Description & acceptance criteria
            <textarea
              rows={5}
              maxLength={30000}
              placeholder="Describe the work, expected outcome and how you will verify it…"
              value={data.description || ''}
              onChange={(e) => change('description', e.target.value)}
            />
          </label>
          <label>
            Start date
            <input
              type="date"
              value={data.start_date || ''}
              max={data.due || undefined}
              onChange={(e) => change('start_date', e.target.value)}
            />
          </label>
          <section className="detail-checklist">
            <div className="section-title">
              <h3>Checklist</h3>
              <span>
                {complete} of {checks.length} complete
              </span>
            </div>
            <progress aria-label="Checklist progress" value={complete} max={Math.max(1, checks.length)} />
            {checks.map((item, index) => (
              <div className={'checklist-row ' + (item.done ? 'complete' : '')} key={index}>
                <input
                  type="checkbox"
                  aria-label={'Complete ' + item.text}
                  checked={item.done}
                  onChange={(e) =>
                    change(
                      'checklist',
                      checks.map((c, i) => (i === index ? { ...c, done: e.target.checked } : c)),
                    )
                  }
                />
                <span>{item.text}</span>
                <button
                  type="button"
                  aria-label={'Remove ' + item.text}
                  onClick={() =>
                    change(
                      'checklist',
                      checks.filter((_, i) => i !== index),
                    )
                  }
                >
                  <X size={13} />
                </button>
              </div>
            ))}
            <div className="checklist-add">
              <input
                aria-label="New checklist item"
                maxLength={500}
                value={entry}
                placeholder="Add a concrete step…"
                onChange={(e) => setEntry(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.nativeEvent.isComposing) {
                    e.preventDefault();
                    if (entry.trim()) {
                      change('checklist', [...checks, { text: entry.trim(), done: false }]);
                      setEntry('');
                    }
                  }
                }}
              />
              <button
                type="button"
                disabled={!entry.trim() || checks.length >= 100}
                onClick={() => {
                  change('checklist', [...checks, { text: entry.trim(), done: false }]);
                  setEntry('');
                }}
              >
                <Plus size={14} />
                Add step
              </button>
            </div>
            <small>
              Checklist edits save with the task. Completing steps does not automatically mark the task Done.
            </small>
          </section>
          {project && (
            <div className="detail-project-context">
              <Folder size={15} />
              <strong>{project.name}</strong>
              <span>{project.status}</span>
              <p>{project.description || 'No project description yet.'}</p>
            </div>
          )}
        </>
      )}
      {type === 'project' && (
        <section className="detail-linked">
          <h3>Linked tasks</h3>
          <progress aria-label="Project completion" value={done} max={Math.max(1, linked.length)} />
          {linked.length ? (
            linked.map((t) => (
              <div key={t.id}>
                <button type="button" onClick={() => openTask(t)}>
                  {t.status === 'Done' && <CheckCircle2 size={14} />} {t.title}
                </button>
                <small>
                  {t.status} · {t.owner} · {t.due || 'No due date'}
                </small>
              </div>
            ))
          ) : (
            <p>No tasks linked to this project yet.</p>
          )}
          <small>Save project changes before opening a linked task.</small>
        </section>
      )}
      {data.id && (
        <div className="detail-timestamps">
          <Clock3 size={13} />
          {data.created_at && <span>Created {when(data.created_at)}</span>}
          <span>Updated {when(data.updated_at)}</span>
        </div>
      )}
    </div>
  );
}
