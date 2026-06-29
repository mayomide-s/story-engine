import { PipelineRunSummary } from "../api/client";

type Props = {
  runs: PipelineRunSummary[];
  selectedRunId: string | null;
  onSelect: (runId: string) => void;
};

export function RunList({ runs, selectedRunId, onSelect }: Props) {
  return (
    <div className="panel">
      <div className="panel-header">
        <h2>Pipeline Runs</h2>
        <span>{runs.length} total</span>
      </div>
      <div className="list">
        {runs.map((run) => (
          <button
            key={run.id}
            className={`run-card ${selectedRunId === run.id ? "active" : ""}`}
            onClick={() => onSelect(run.id)}
          >
            <strong>{run.topic}</strong>
            <span>{run.status}</span>
            <span>{run.current_stage}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
