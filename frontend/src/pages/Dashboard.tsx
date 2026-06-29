import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api, PipelineRunDetail, PipelineRunSummary } from "../api/client";
import { EventTimeline } from "../components/EventTimeline";
import { RunList } from "../components/RunList";

const videoProvider = import.meta.env.VITE_VIDEO_PROVIDER ?? "mock";
const isRunwayMode = videoProvider === "runway";

export function DashboardPage() {
  const [topic, setTopic] = useState("CORS");
  const [runs, setRuns] = useState<PipelineRunSummary[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [detail, setDetail] = useState<PipelineRunDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isResuming, setIsResuming] = useState(false);

  async function loadRuns() {
    const data = await api.listRuns();
    setRuns(data);
    if (!selectedRunId && data.length > 0) {
      setSelectedRunId(data[0].id);
    }
  }

  async function loadDetail(runId: string) {
    const data = await api.getRun(runId);
    setDetail(data);
  }

  useEffect(() => {
    loadRuns().catch((err) => setError(err.message));
  }, []);

  useEffect(() => {
    if (selectedRunId) {
      loadDetail(selectedRunId).catch((err) => setError(err.message));
    }
  }, [selectedRunId]);

  async function handleCreateRun() {
    try {
      setError(null);
      const created = await api.createRun(topic, false);
      setDetail(created);
      setSelectedRunId(String(created.pipeline_run.id));
      await loadRuns();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create run.");
    }
  }

  async function handleResume() {
    if (!selectedRunId) return;
    if (isRunwayMode) {
      const confirmed = window.confirm(
        "VIDEO_PROVIDER=runway is active. Resuming this run can spend Runway credits. Continue?",
      );
      if (!confirmed) {
        return;
      }
    }
    try {
      setError(null);
      setIsResuming(true);
      const resumed = await api.resumeRun(selectedRunId, "Approved from dashboard");
      setDetail(resumed);
      await loadRuns();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to resume run.");
      await loadDetail(selectedRunId).catch(() => undefined);
    } finally {
      setIsResuming(false);
    }
  }

  async function handleCancel() {
    if (!selectedRunId) return;
    try {
      setError(null);
      const cancelled = await api.cancelRun(selectedRunId, "Cancelled from dashboard");
      setDetail(cancelled);
      await loadRuns();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to cancel run.");
    }
  }

  const run = detail?.pipeline_run ?? null;
  const runStatus = typeof run?.status === "string" ? run.status : "";
  const canResume = runStatus === "awaiting_review";
  const canCancel = ["queued", "running", "awaiting_review", "needs_review"].includes(runStatus);

  return (
    <div className="page">
      <section className="hero panel">
        <div>
          <p className="eyebrow">Dashboard</p>
          <h2>Build the next coding mini-story</h2>
          <p className="subtle">The first slice pauses after storyboard review so you can fix ideas before spending video credits.</p>
          <p className="subtle">
            Active video provider: <strong>{videoProvider}</strong>
            {isRunwayMode ? " - Resume will trigger paid Runway generation." : " - Safe local/mock mode."}
          </p>
        </div>
        <div className="hero-actions">
          <input value={topic} onChange={(event) => setTopic(event.target.value)} placeholder="Topic" />
          <button onClick={handleCreateRun}>Create Run</button>
        </div>
      </section>
      {error ? <p className="error">{error}</p> : null}
      <div className="grid">
        <RunList runs={runs} selectedRunId={selectedRunId} onSelect={setSelectedRunId} />
        <div className="stack">
          <div className="panel">
            <div className="panel-header">
              <h2>Run Details</h2>
            </div>
            {run ? (
              <div className="key-grid">
                <div><span>Topic</span><strong>{String(run.topic)}</strong></div>
                <div><span>Status</span><strong>{String(run.status)}</strong></div>
                <div><span>Stage</span><strong>{String(run.current_stage)}</strong></div>
                <div><span>Priority</span><strong>{String(run.priority)}</strong></div>
              </div>
            ) : (
              <p className="subtle">Select or create a run to inspect it.</p>
            )}
            {selectedRunId ? (
              <div className="stack">
                <div className="button-row">
                  {canResume ? <button onClick={handleResume} disabled={isResuming}>{isResuming ? "Resuming..." : "Resume"}</button> : null}
                  {canCancel ? <button className="secondary" onClick={handleCancel}>Cancel</button> : null}
                </div>
                {canResume && isRunwayMode ? (
                  <p className="subtle">Warning: this Resume action will submit or continue a real Runway job if one has not already been submitted.</p>
                ) : null}
                <div className="link-row">
                  <Link className="inline-link" to={`/ideas?run=${selectedRunId}`}>Open Ideas</Link>
                  <Link className="inline-link" to={`/review?run=${selectedRunId}`}>Open Video Review</Link>
                </div>
              </div>
            ) : null}
          </div>
          <EventTimeline events={detail?.pipeline_events ?? []} />
        </div>
      </div>
    </div>
  );
}
