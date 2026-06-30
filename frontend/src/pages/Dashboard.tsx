import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { api, AccountDefaults, PipelineRunDetail, PipelineRunSummary } from "../api/client";
import { EventTimeline } from "../components/EventTimeline";
import { RunList } from "../components/RunList";
import { AUDIENCE_LEVELS, CONTENT_FORMATS, STYLE_PRESETS, TARGET_PLATFORMS } from "../constants";

const videoProvider = import.meta.env.VITE_VIDEO_PROVIDER ?? "mock";
const storageProvider = import.meta.env.VITE_STORAGE_PROVIDER ?? "local";
const providerBadge = `${videoProvider}/${storageProvider.toUpperCase()}`;
const isRunwayMode = videoProvider === "runway";
export function DashboardPage() {
  const [topic, setTopic] = useState("CORS");
  const [stylePreset, setStylePreset] = useState("clean_3d_cartoon");
  const [targetPlatforms, setTargetPlatforms] = useState<string[]>(["instagram", "tiktok", "youtube"]);
  const [captionTone, setCaptionTone] = useState("playful explainer");
  const [durationPreferenceSeconds, setDurationPreferenceSeconds] = useState(18);
  const [audienceLevel, setAudienceLevel] = useState("beginner");
  const [contentFormat, setContentFormat] = useState("coding metaphor");
  const [runs, setRuns] = useState<PipelineRunSummary[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [detail, setDetail] = useState<PipelineRunDetail | null>(null);
  const [defaults, setDefaults] = useState<AccountDefaults | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isResuming, setIsResuming] = useState(false);

  function applyDefaults(config: AccountDefaults["account_config_json"]) {
    setStylePreset(String(config.default_style_preset ?? "clean_3d_cartoon"));
    setTargetPlatforms(Array.isArray(config.target_platforms) ? config.target_platforms : ["instagram"]);
    setCaptionTone(String(config.default_caption_tone ?? "playful explainer"));
    setDurationPreferenceSeconds(Number(config.default_duration_seconds ?? 18));
    setAudienceLevel(String(config.default_audience_level ?? "beginner"));
    setContentFormat(String(config.default_content_format ?? "coding metaphor"));
  }

  function togglePlatform(platform: string) {
    setTargetPlatforms((current) => {
      if (current.includes(platform)) {
        const next = current.filter((item) => item !== platform);
        return next.length > 0 ? next : current;
      }
      return [...current, platform];
    });
  }

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
    api.getAccountDefaults().then((data) => {
      setDefaults(data);
      applyDefaults(data.account_config_json);
    }).catch((err) => setError(err.message));
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
      const created = await api.createRun({
        topic,
        auto_mode: false,
        style_preset: stylePreset,
        target_platforms: targetPlatforms,
        caption_tone: captionTone,
        duration_preference_seconds: durationPreferenceSeconds,
        audience_level: audienceLevel,
        content_format: contentFormat,
      });
      setDetail(created);
      setSelectedRunId(String(created.pipeline_run.id));
      await loadRuns();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create run.");
    }
  }

  async function handleResume() {
    if (!selectedRunId) return;
    let confirmPaidGeneration = false;
    if (isRunwayMode) {
      const confirmed = window.confirm(
        "This will submit one video to Runway and may spend real provider credits. Continue?",
      );
      if (!confirmed) {
        return;
      }
      confirmPaidGeneration = true;
    }
    try {
      setError(null);
      setIsResuming(true);
      const resumed = await api.resumeRun(selectedRunId, "Approved from dashboard", confirmPaidGeneration);
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
  const preflight = detail?.review_preflight ?? null;
  const preflightPromptTooLong = Boolean(preflight?.prompt_length?.too_long);
  const preflightPromptInvalid = preflight?.prompt_valid === false;
  const lowPreflight = Boolean(preflight?.low_score_warning);
  const canResume = runStatus === "awaiting_review";
  const canCancel = ["queued", "running", "awaiting_review", "needs_review"].includes(runStatus);
  const resumeLabel = "Resume";
  const defaultConfig = defaults?.account_config_json;

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
            {isRunwayMode ? " - Resume one reviewed run only. Each resume can spend real Runway credits." : " - Safe mock generation mode."}
          </p>
          <p className="subtle">
            Brand defaults come from Settings and can be overridden per run before creation.
            {" "}
            <Link className="inline-link" to="/settings">Open Settings</Link>
          </p>
        </div>
      </section>
      <section className="panel">
        <div className="panel-header">
          <h2>Create Run</h2>
          <div className="button-row">
            <button className="secondary" type="button" onClick={() => defaultConfig ? applyDefaults(defaultConfig) : undefined}>
              Reset To Defaults
            </button>
            <button onClick={handleCreateRun}>Create Run</button>
          </div>
        </div>
        <div className="form-grid">
          <label className="field">
            <span>Topic</span>
            <input value={topic} onChange={(event) => setTopic(event.target.value)} placeholder="Topic" />
          </label>
          <label className="field">
            <span>Style Preset</span>
            <select value={stylePreset} onChange={(event) => setStylePreset(event.target.value)}>
              {STYLE_PRESETS.map((preset) => (
                <option key={preset} value={preset}>
                  {preset}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Caption Tone</span>
            <input value={captionTone} onChange={(event) => setCaptionTone(event.target.value)} />
          </label>
          <label className="field">
            <span>Duration Preference</span>
            <input
              type="number"
              min={5}
              max={30}
              value={durationPreferenceSeconds}
              onChange={(event) => setDurationPreferenceSeconds(Number(event.target.value))}
            />
          </label>
          <label className="field">
            <span>Audience Level</span>
            <select value={audienceLevel} onChange={(event) => setAudienceLevel(event.target.value)}>
              {AUDIENCE_LEVELS.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
          </label>
          <label className="field">
            <span>Content Format</span>
            <select value={contentFormat} onChange={(event) => setContentFormat(event.target.value)}>
              {CONTENT_FORMATS.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
          </label>
          <div className="field field-wide">
            <span>Target Platforms</span>
            <div className="toggle-row">
              {TARGET_PLATFORMS.map((platform) => (
                <label key={platform} className="toggle-chip">
                  <input
                    type="checkbox"
                    checked={targetPlatforms.includes(platform)}
                    onChange={() => togglePlatform(platform)}
                  />
                  <span>{platform}</span>
                </label>
              ))}
            </div>
          </div>
        </div>
        {defaultConfig ? (
          <div className="notice-card">
            <strong>Applied Defaults</strong>
            <p>
              Style: {defaultConfig.default_style_preset} | Platforms: {defaultConfig.target_platforms.join(", ")} | Tone: {defaultConfig.default_caption_tone}
            </p>
            <p>
              Audience: {defaultConfig.default_audience_level} | Format: {defaultConfig.default_content_format} | Duration: {defaultConfig.default_duration_seconds}s
            </p>
          </div>
        ) : null}
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
                    <button onClick={handleResume} disabled={isResuming || preflightPromptTooLong || preflightPromptInvalid}>
                      {isResuming ? "Processing..." : resumeLabel}
                    </button>
                  ) : null}
                  {canCancel ? <button className="secondary" onClick={handleCancel}>Cancel</button> : null}
                </div>
                {canResume && (lowPreflight || preflightPromptTooLong || preflightPromptInvalid) ? (
                  <div className={`notice-card ${preflightPromptTooLong || preflightPromptInvalid || lowPreflight ? "warning" : ""}`}>
                    <strong>{preflightPromptTooLong || preflightPromptInvalid ? "Fix review before Resume" : "Low preflight warning"}</strong>
                    <p>{preflight?.summary ?? "Review the Ideas page before spending credits."}</p>
                  </div>
                ) : null}
                {canResume && isRunwayMode ? (
                  <div className="notice-card warning">
                    <strong>Paid generation warning</strong>
                    <p>
                      This resume action can submit one real Runway job and spend credits. Resume one reviewed run only.
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
