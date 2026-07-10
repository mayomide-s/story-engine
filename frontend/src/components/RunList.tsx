import { PipelineRunSummary } from "../api/client";
import { formatProvider, formatRunStatus, formatStage, formatVideoStatus } from "../utils/display";

export type RunStatusFilter = "all" | "awaiting_review" | "completed" | "failed" | "archived";
export type RunProviderFilter = "all" | "mock" | "runway";

type Props = {
  runs: PipelineRunSummary[];
  totalRuns: number;
  selectedRunId: string | null;
  selectedRunIds: string[];
  statusFilter: RunStatusFilter;
  providerFilter: RunProviderFilter;
  topicSearch: string;
  showArchived: boolean;
  archivedRunIds: string[];
  onSelect: (runId: string) => void;
  onSelectionChange: (runId: string, selected: boolean) => void;
  onSelectAllVisible: () => void;
  onClearSelection: () => void;
  onStatusFilterChange: (value: RunStatusFilter) => void;
  onProviderFilterChange: (value: RunProviderFilter) => void;
  onTopicSearchChange: (value: string) => void;
  onShowArchivedChange: (value: boolean) => void;
  onArchiveRun: (runId: string) => void;
  onUnarchiveRun: (runId: string) => void;
  onArchiveSelected: () => void;
  onArchiveFailedRuns: () => void;
  onArchiveOldAwaitingReviewRuns: () => void;
  onArchiveOldCorsRuns: () => void;
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

export function RunList({
  runs,
  totalRuns,
  selectedRunId,
  selectedRunIds,
  statusFilter,
  providerFilter,
  topicSearch,
  showArchived,
  archivedRunIds,
  onSelect,
  onSelectionChange,
  onSelectAllVisible,
  onClearSelection,
  onStatusFilterChange,
  onProviderFilterChange,
  onTopicSearchChange,
  onShowArchivedChange,
  onArchiveRun,
  onUnarchiveRun,
  onArchiveSelected,
  onArchiveFailedRuns,
  onArchiveOldAwaitingReviewRuns,
  onArchiveOldCorsRuns,
}: Props) {
  const archivedSet = new Set(archivedRunIds);
  const activeRuns = runs.filter((run) => !archivedSet.has(run.id));
  const archivedRuns = runs.filter((run) => archivedSet.has(run.id));

  return (
    <div className="panel run-list-panel">
      <div className="panel-header">
        <h2>Pipeline Runs</h2>
        <span>{runs.length} shown of {totalRuns}</span>
      </div>
      <div className="stack compact run-list-controls">
        <div className="run-list-filter-grid">
          <label className="field">
            <span>Status</span>
            <select value={statusFilter} onChange={(event) => onStatusFilterChange(event.target.value as RunStatusFilter)}>
              <option value="all">All</option>
              <option value="awaiting_review">Awaiting Review</option>
              <option value="completed">Completed</option>
              <option value="failed">Failed</option>
              <option value="archived">Archived</option>
            </select>
          </label>
          <label className="field">
            <span>Provider</span>
            <select value={providerFilter} onChange={(event) => onProviderFilterChange(event.target.value as RunProviderFilter)}>
              <option value="all">All</option>
              <option value="mock">Mock</option>
              <option value="runway">Runway</option>
            </select>
          </label>
          <label className="field field-wide run-list-search">
            <span>Topic Search</span>
            <input
              value={topicSearch}
              onChange={(event) => onTopicSearchChange(event.target.value)}
              placeholder="Search topics"
            />
          </label>
        </div>
        <div className="panel-header">
          <label className="toggle-chip">
            <input
              type="checkbox"
              checked={showArchived}
              onChange={(event) => onShowArchivedChange(event.target.checked)}
            />
            <span>Show archived runs</span>
          </label>
          <div className="button-row">
            <button className="secondary" type="button" onClick={onSelectAllVisible} disabled={runs.length === 0}>
              Select all visible
            </button>
            <button className="secondary" type="button" onClick={onClearSelection} disabled={selectedRunIds.length === 0}>
              Clear selection
            </button>
          </div>
        </div>
        <div className="run-cleanup-bar">
          <div>
            <strong>Run cleanup</strong>
            <p className="subtle">Local only. This hides runs in this browser and does not delete database records.</p>
          </div>
          <div className="button-row">
            <button type="button" onClick={onArchiveSelected} disabled={selectedRunIds.length === 0}>
              Archive selected ({selectedRunIds.length})
            </button>
            <button className="secondary" type="button" onClick={onArchiveFailedRuns}>
              Archive failed
            </button>
            <button className="secondary" type="button" onClick={onArchiveOldAwaitingReviewRuns}>
              Archive old awaiting review
            </button>
            <button className="secondary" type="button" onClick={onArchiveOldCorsRuns}>
              Archive old test CORS
            </button>
          </div>
        </div>
      </div>
      <div className="stack scroll-panel run-list-scroll">
        {STATUS_GROUPS.map((group) => {
          const items = activeRuns.filter((run) => group.statuses.includes(run.status));
          if (items.length === 0) {
            return null;
          }
          const isFailedGroup = group.title === "Failed";
          const content = (
            <div className="list">
              {items.map((run) => (
                <div
                  key={run.id}
                  className={`run-card run-card-${run.status} ${selectedRunId === run.id ? "active" : ""}`}
                >
                  <div className="panel-header run-card-toolbar">
                    <label className="select-row">
                      <input
                        type="checkbox"
                        checked={selectedRunIds.includes(run.id)}
                        onChange={(event) => onSelectionChange(run.id, event.target.checked)}
                      />
                      <span className="subtle">Select</span>
                    </label>
                    <button
                      className="text-link"
                      type="button"
                      onClick={() => archivedSet.has(run.id) ? onUnarchiveRun(run.id) : onArchiveRun(run.id)}
                    >
                      {archivedSet.has(run.id) ? "Unarchive" : "Archive"}
                    </button>
                  </div>
                  <button className="run-card-button" type="button" onClick={() => onSelect(run.id)}>
                    <div className="content-meta">
                      <strong>{run.topic}</strong>
                      <span>{formatCreatedAt(run.created_at)}</span>
                    </div>
                    <div className="run-card-badges">
                      <span className="status-pill">{formatProvider(run.provider)}</span>
                      <span className="status-pill muted">{formatRunStatus(run.status)}</span>
                      {archivedSet.has(run.id) ? <span className="status-pill warning">Archived</span> : null}
                    </div>
                    <span>{formatStage(run.current_stage)}</span>
                    {run.video_status ? <span className="subtle">Video: {formatVideoStatus(run.video_status)}</span> : null}
                    {run.error_message ? <span className="error">{run.error_message}</span> : null}
                  </button>
                </div>
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
        {archivedRuns.length > 0 && (statusFilter === "archived" || showArchived) ? (
          <section className="stack compact">
            <div className="section-kicker">
              <strong>Archived</strong>
              <span>{archivedRuns.length}</span>
            </div>
            <div className="list">
              {archivedRuns.map((run) => (
                <div
                  key={run.id}
                  className={`run-card run-card-${run.status} ${selectedRunId === run.id ? "active" : ""}`}
                >
                  <div className="panel-header run-card-toolbar">
                    <label className="select-row">
                      <input
                        type="checkbox"
                        checked={selectedRunIds.includes(run.id)}
                        onChange={(event) => onSelectionChange(run.id, event.target.checked)}
                      />
                      <span className="subtle">Select</span>
                    </label>
                    <button className="text-link" type="button" onClick={() => onUnarchiveRun(run.id)}>
                      Unarchive
                    </button>
                  </div>
                  <button className="run-card-button" type="button" onClick={() => onSelect(run.id)}>
                    <div className="content-meta">
                      <strong>{run.topic}</strong>
                      <span>{formatCreatedAt(run.created_at)}</span>
                    </div>
                    <div className="run-card-badges">
                      <span className="status-pill">{formatProvider(run.provider)}</span>
                      <span className="status-pill muted">{formatRunStatus(run.status)}</span>
                      <span className="status-pill warning">Archived</span>
                    </div>
                    <span>{formatStage(run.current_stage)}</span>
                    {run.video_status ? <span className="subtle">Video: {formatVideoStatus(run.video_status)}</span> : null}
                    {run.error_message ? <span className="error">{run.error_message}</span> : null}
                  </button>
                </div>
              ))}
            </div>
          </section>
        ) : null}
        {runs.length === 0 ? <p className="subtle">No runs match the current filters.</p> : null}
      </div>
    </div>
  );
}
