import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { api, AccountDefaults, HealthDetails, PipelineRunDetail, PipelineRunSummary } from "../api/client";
import { EventTimeline } from "../components/EventTimeline";
import { RunList } from "../components/RunList";
import { AUDIENCE_LEVELS, CONTENT_FORMATS, STYLE_PRESETS, TARGET_PLATFORMS } from "../constants";
import { formatProvider, formatRunStatus, formatStage } from "../utils/display";

const videoProvider = import.meta.env.VITE_VIDEO_PROVIDER ?? "mock";
const storageProvider = import.meta.env.VITE_STORAGE_PROVIDER ?? "local";
const GOLDEN_DEMO_VIDEO_KEY = "videos/30ea2e8e-780a-471b-b85e-80ff8d84fe51.mp4";
const GOLDEN_DEMO_THUMBNAIL_KEY = "thumbnails/30ea2e8e-780a-471b-b85e-80ff8d84fe51.jpg";

function toFriendlyResumeError(error: unknown) {
  const message = error instanceof Error ? error.message : "Failed to resume run.";
  if (message.includes("Runway generation requires explicit paid confirmation")) {
    return "Tick the paid Runway confirmation checkbox, then use Resume with paid Runway generation.";
  }
  return message;
}

function formatQualityScore(value: unknown) {
  const score = typeof value === "number" ? value : Number(value);
  return Number.isFinite(score) ? score.toFixed(2) : "n/a";
}

function formatDuration(value: unknown) {
  const seconds = typeof value === "number" ? value : Number(value);
  return Number.isFinite(seconds) ? `${seconds}s` : "n/a";
}

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
  const [healthDetails, setHealthDetails] = useState<HealthDetails | null>(null);
  const [featuredDemo, setFeaturedDemo] = useState<PipelineRunDetail | null>(null);
  const [defaults, setDefaults] = useState<AccountDefaults | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isResuming, setIsResuming] = useState(false);
  const [paidRunwayConfirmed, setPaidRunwayConfirmed] = useState(false);
  const [captionPackageCopied, setCaptionPackageCopied] = useState(false);

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
    await loadFeaturedDemo(data);
  }

  async function loadDetail(runId: string) {
    const data = await api.getRun(runId);
    setDetail(data);
  }

  async function loadFeaturedDemo(runList: PipelineRunSummary[]) {
    const candidates = runList
      .filter((run) => run.status === "completed" || run.video_status === "approved" || run.video_status === "completed")
      .sort((left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime());

    if (candidates.length === 0) {
      setFeaturedDemo(null);
      return;
    }

    let fallback: PipelineRunDetail | null = null;
    for (const candidate of candidates) {
      try {
        const payload = await api.getRun(candidate.id);
        const assets = payload.assets ?? [];
        const videoAsset = assets.find((asset) => asset.asset_type === "video_mp4");
        const thumbnailAsset = assets.find((asset) => asset.asset_type === "thumbnail");
        const video = payload.video as Record<string, unknown> | null;
        const run = payload.pipeline_run as Record<string, unknown> | null;
        const videoStatus = String(video?.status ?? "");
        const provider = String(video?.provider ?? candidate.provider ?? "");
        const videoStorageKey = String(videoAsset?.storage_key ?? "");
        const thumbnailStorageKey = String(thumbnailAsset?.storage_key ?? "");

        if (videoStorageKey === GOLDEN_DEMO_VIDEO_KEY || thumbnailStorageKey === GOLDEN_DEMO_THUMBNAIL_KEY) {
          setFeaturedDemo(payload);
          return;
        }

        if (!fallback && provider === "runway" && videoAsset && ["approved", "completed"].includes(videoStatus) && String(run?.status ?? "") === "completed") {
          fallback = payload;
        }
      } catch {
        // ignore demo candidate failures
      }
    }

    setFeaturedDemo(fallback);
  }

  useEffect(() => {
    api.getAccountDefaults().then((data) => {
      setDefaults(data);
      applyDefaults(data.account_config_json);
    }).catch((err) => setError(err.message));
    api.getHealthDetails().then(setHealthDetails).catch(() => undefined);
    loadRuns().catch((err) => setError(err.message));
  }, []);

  useEffect(() => {
    if (selectedRunId) {
      loadDetail(selectedRunId).catch((err) => setError(err.message));
    }
    setPaidRunwayConfirmed(false);
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
    const confirmPaidGeneration = isRunwayMode;
    try {
      setError(null);
      setIsResuming(true);
      const resumed = await api.resumeRun(selectedRunId, "Approved from dashboard", confirmPaidGeneration);
      setDetail(resumed);
      await loadRuns();
    } catch (err) {
      setError(toFriendlyResumeError(err));
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

  async function handleCopyCaptionPackage() {
    if (!featuredDemo?.manual_post_package) {
      return;
    }
    const manualPackage = featuredDemo.manual_post_package as Record<string, unknown>;
    const caption = String(manualPackage.caption ?? "");
    const hashtags = Array.isArray(manualPackage.hashtags_json) ? manualPackage.hashtags_json.join(" ") : "";
    const packageText = [caption, hashtags].filter(Boolean).join("\n\n");
    if (!packageText) {
      return;
    }
    try {
      await navigator.clipboard.writeText(packageText);
      setCaptionPackageCopied(true);
      window.setTimeout(() => setCaptionPackageCopied(false), 1500);
    } catch {
      setCaptionPackageCopied(false);
    }
  }

  const run = detail?.pipeline_run as Record<string, unknown> | null;
  const video = detail?.video as Record<string, unknown> | null;
  const runStatus = typeof run?.status === "string" ? run.status : "";
  const activeVideoProvider = healthDetails?.video_provider ?? videoProvider;
  const isRunwayMode = activeVideoProvider === "runway" && Boolean(healthDetails?.runway_mode_enabled);
  const preflight = detail?.review_preflight ?? null;
  const preflightPromptTooLong = Boolean(preflight?.prompt_length?.too_long);
  const preflightPromptInvalid = preflight?.prompt_valid === false;
  const lowPreflight = Boolean(preflight?.low_score_warning);
  const canResume = runStatus === "awaiting_review";
  const canCancel = ["queued", "running", "awaiting_review", "needs_review"].includes(runStatus);
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
  const featuredRun = featuredDemo?.pipeline_run as Record<string, unknown> | null;
  const featuredVideo = featuredDemo?.video as Record<string, unknown> | null;
  const featuredQualityCheck = featuredDemo?.quality_checks?.[featuredDemo.quality_checks.length - 1] as Record<string, unknown> | undefined;

  return (
    <div className="page">
      {featuredDemo && featuredRun && featuredVideo ? (
        <section className="panel featured-demo-card">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Featured Demo</p>
              <h2>{String(featuredRun.topic ?? "CORS")}</h2>
            </div>
            <span className="status-pill success">Runway generated</span>
          </div>
          <div className="key-grid">
            <div><span>Provider</span><strong>{formatProvider(String(featuredVideo.provider ?? "runway"))}</strong></div>
            <div><span>Duration</span><strong>{formatDuration(featuredVideo.duration_seconds)}</strong></div>
            <div><span>Quality Score</span><strong>{formatQualityScore(featuredQualityCheck?.score)}</strong></div>
            <div><span>Status</span><strong>Completed / Approved</strong></div>
          </div>
          <p className="subtle">A completed coding explainer ready for review and posting.</p>
          <div className="button-row">
            <Link className="inline-link" to={`/review?run=${String(featuredRun.id)}`}>Open Review</Link>
            <button className="secondary" type="button" onClick={handleCopyCaptionPackage} disabled={!featuredDemo.manual_post_package}>
              {captionPackageCopied ? "Posting copy copied" : "Copy Posting Copy"}
            </button>
          </div>
        </section>
      ) : null}
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
          <details className="technical-disclosure inline-technical">
            <summary>Applied defaults</summary>
            <p className="subtle">
              {defaultConfig.default_style_preset} | {defaultConfig.target_platforms.join(", ")} | {defaultConfig.default_caption_tone} | {defaultConfig.default_audience_level} | {defaultConfig.default_content_format} | {defaultConfig.default_duration_seconds}s
            </p>
          </details>
        ) : null}
      </section>
      {error ? <p className="error">{error}</p> : null}
      <div className="dashboard-grid">
        <RunList runs={runs} selectedRunId={selectedRunId} onSelect={setSelectedRunId} />
        <div className="stack">
          <div className="panel detail-panel">
            <div className="panel-header">
              <h2>Run Details</h2>
            </div>
            <div className="scroll-panel detail-scroll">
            {run ? (
              <div className="stack">
                <div className="key-grid">
                  <div><span>Topic</span><strong>{String(run.topic)}</strong></div>
                  <div><span>Status</span><strong>{formatRunStatus(String(run.status))}</strong></div>
                  <div><span>Stage</span><strong>{formatStage(String(run.current_stage))}</strong></div>
                  <div><span>Provider</span><strong>{formatProvider(String(video?.provider ?? ""))}</strong></div>
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
                  {canResume && !isRunwayMode ? (
                    <button onClick={handleResume} disabled={isResuming || preflightPromptTooLong || preflightPromptInvalid}>
                      {isResuming ? "Processing..." : "Resume"}
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
                    <strong>Runway paid generation is enabled</strong>
                    <p>
                      Resuming this run may spend real Runway credits.
                    </p>
                    <label className="toggle-chip paid-confirmation">
                      <input
                        type="checkbox"
                        checked={paidRunwayConfirmed}
                        onChange={(event) => setPaidRunwayConfirmed(event.target.checked)}
                      />
                      <span>I understand this may spend Runway credits.</span>
                    </label>
                    <div className="button-row">
                      <button
                        onClick={handleResume}
                        disabled={isResuming || !paidRunwayConfirmed || preflightPromptTooLong || preflightPromptInvalid}
                      >
                        {isResuming ? "Processing..." : "Resume with paid Runway generation"}
                      </button>
                    </div>
                    <p className="subtle">Resume one reviewed run only. Each resume can spend real Runway credits.</p>
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
          </div>
          <EventTimeline events={detail?.pipeline_events ?? []} summary="Show technical timeline" />
        </div>
      </div>
    </div>
  );
}
