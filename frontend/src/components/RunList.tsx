import { PipelineRunSummary } from "../api/client";

type Props = {
  runs: PipelineRunSummary[];
  selectedRunId: string | null;
  onSelect: (runId: string) => void;
};

const STATUS_GROUPS: Array<{ title: string; statuses: string[] }> = [
  { title: "Awaiting Review", statuses: ["awaiting_review"] },
  { title: "Running", statuses: ["queued", "running"] },
  { title: "Needs Review", statuses: ["needs_review"] },
  { title: "Completed", statuses: ["completed", "cancelled"] },
  { title: "Failed", statuses: ["failed"] },
];

function formatCreatedAt(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function RunList({ runs, selectedRunId, onSelect }: Props) {
  return (
    <div className="panel">
      <div className="panel-header">
        <h2>Pipeline Runs</h2>
        <span>{runs.length} total</span>
      </div>
      <div className="stack">
        {STATUS_GROUPS.map((group) => {
          const items = runs.filter((run) => group.statuses.includes(run.status));
          if (items.length === 0) {
            return null;
          }
          const isFailedGroup = group.title === "Failed";
          const content = (
            <div className="list">
              {items.map((run) => (
                <button
                  key={run.id}
                  className={`run-card run-card-${run.status} ${selectedRunId === run.id ? "active" : ""}`}
                  onClick={() => onSelect(run.id)}
                >
                  <div className="content-meta">
                    <strong>{run.topic}</strong>
                    <span>{formatCreatedAt(run.created_at)}</span>
                  </div>
                  <div className="run-card-badges">
                    <span className="status-pill">{run.provider ?? "not started"}</span>
                    <span className="status-pill muted">{run.status}</span>
                  </div>
                  <span>{run.current_stage}</span>
                  {run.video_status ? <span className="subtle">video: {run.video_status}</span> : null}
                  {run.error_message ? <span className="error">{run.error_message}</span> : null}
                </button>
              ))}
            </div>
          );
          return (
            <section key={group.title} className="stack compact">
              <div className="section-kicker">
                <strong>{group.title}</strong>
                <span>{items.length}</span>
              </div>
              {isFailedGroup ? (
                <details className="run-group-collapse">
                  <summary>Show failed runs</summary>
                  {content}
                </details>
              ) : content}
            </section>
          );
        })}
      </div>
    </div>
  );
}
