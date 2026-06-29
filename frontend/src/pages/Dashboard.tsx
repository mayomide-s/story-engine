import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { api, PipelineRunDetail, PipelineRunSummary } from "../api/client";
import { EventTimeline } from "../components/EventTimeline";
import { RunList } from "../components/RunList";

const videoProvider = import.meta.env.VITE_VIDEO_PROVIDER ?? "mock";
const storageProvider = import.meta.env.VITE_STORAGE_PROVIDER ?? "local";
const providerBadge = `${videoProvider}/${storageProvider.toUpperCase()}`;
const isRunwayMode = videoProvider === "runway";
const STYLE_PRESETS = [
  "clean_3d_cartoon",
  "neon_club_metaphor",
  "whiteboard_character",
  "bug_monster",
  "office_comedy",
];

export function DashboardPage() {
  const [topic, setTopic] = useState("CORS");
  const [stylePreset, setStylePreset] = useState("clean_3d_cartoon");
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
      const created = await api.createRun(topic, false, stylePreset);
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
        "VIDEO_PROVIDER=runway is active. Continuing this run may spend Runway credits if a provider job has not already been submitted. Continue?",
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

  const run = detail?.pipeline_run as Record<string, unknown> | null;
  const video = detail?.video as Record<string, unknown> | null;
  const runStatus = typeof run?.status === "string" ? run.status : "";
  const hasExistingProviderJob = Boolean(video?.provider_job_id);
  const canResume = runStatus === "awaiting_review" || (runStatus === "running" && hasExistingProviderJob);
  const canCancel = ["queued", "running", "awaiting_review", "needs_review"].includes(runStatus);
  const resumeLabel = hasExistingProviderJob ? "Continue Existing Generation" : "Resume";

  const nextAction = useMemo(() => {
    if (!selectedRunId) {
      return null;
    }
    if (runStatus === "needs_review") {
      return { label: "Open Video Review", href: `/review?run=${selectedRunId}` };
    }
    if (runStatus === "failed") {
      return { label: "Create New Run", href: "/" };
    }
    if (runStatus === "awaiting_review") {
      return { label: "Open Ideas", href: `/ideas?run=${selectedRunId}` };
    }
    return null;
  }, [runStatus, selectedRunId]);

  return (
    <div className="page">
      <section className="hero panel">
        <div>
          <p className="eyebrow">Dashboard</p>
          <div className="title-row">
            <h2>Build the next coding mini-story</h2>
            <span className={`status-pill ${isRunwayMode ? "warning" : "success"}`}>{providerBadge}</span>
          </div>
          <p className="subtle">The first slice pauses after storyboard review so you can fix ideas before spending video credits.</p>
          <p className="subtle">
            Active video provider: <strong>{videoProvider}</strong>
            {isRunwayMode ? " - Resume can spend real Runway credits." : " - Safe mock generation mode."}
          </p>
        </div>
        <div className="hero-actions">
          <input value={topic} onChange={(event) => setTopic(event.target.value)} placeholder="Topic" />
          <select value={stylePreset} onChange={(event) => setStylePreset(event.target.value)}>
            {STYLE_PRESETS.map((preset) => (
              <option key={preset} value={preset}>
                {preset}
              </option>
            ))}
          </select>
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
              <div className="stack">
                <div className="key-grid">
                  <div><span>Topic</span><strong>{String(run.topic)}</strong></div>
                  <div><span>Status</span><strong>{String(run.status)}</strong></div>
                  <div><span>Stage</span><strong>{String(run.current_stage)}</strong></div>
                  <div><span>Provider</span><strong>{String(video?.provider ?? "not started")}</strong></div>
                  <div><span>Style Preset</span><strong>{String(run.style_preset ?? "clean_3d_cartoon")}</strong></div>
                </div>
                {run.error_message ? (
                  <div className="notice-card danger">
                    <strong>Latest Error</strong>
                    <p>{String(run.error_message)}</p>
                  </div>
                ) : null}
              </div>
            ) : (
              <p className="subtle">Select or create a run to inspect it.</p>
            )}
            {selectedRunId ? (
              <div className="stack">
                <div className="button-row">
                  {canResume ? (
                    <button onClick={handleResume} disabled={isResuming}>
                      {isResuming ? "Processing..." : resumeLabel}
                    </button>
                  ) : null}
                  {canCancel ? <button className="secondary" onClick={handleCancel}>Cancel</button> : null}
                </div>
                {canResume && isRunwayMode ? (
                  <div className="notice-card warning">
                    <strong>Paid generation warning</strong>
                    <p>
                      {hasExistingProviderJob
                        ? "This run already has a Runway job. Continuing will not create a second job."
                        : "This resume action can submit a real Runway job and spend credits."}
                    </p>
                  </div>
                ) : null}
                {runStatus === "needs_review" ? (
                  <div className="notice-card">
                    <strong>Needs review</strong>
                    <p>Open Video Review to inspect the quality check and re-run review logic without spending new Runway credits.</p>
                  </div>
                ) : null}
                {nextAction ? (
                  <div className="link-row">
                    <Link className="inline-link" to={nextAction.href}>{nextAction.label}</Link>
                  </div>
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
