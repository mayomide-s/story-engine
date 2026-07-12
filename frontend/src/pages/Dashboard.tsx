import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { api, AccountDefaults, HealthDetails, PipelineRunDetail, PipelineRunSummary } from "../api/client";
import { EventTimeline } from "../components/EventTimeline";
import { RunList, RunProviderFilter, RunStatusFilter } from "../components/RunList";
import { AUDIENCE_LEVELS, CONTENT_FORMATS, STYLE_PRESETS, TARGET_PLATFORMS } from "../constants";
import { getArchivedRunsStorageKey, loadArchivedRunIds, saveArchivedRunIds } from "../utils/archivedRuns";
import { clearDashboardPrefill, readDashboardPrefillCapture } from "../utils/batchPlanner";
import { formatProvider, formatRunStatus, formatStage } from "../utils/display";

const videoProvider = import.meta.env.VITE_VIDEO_PROVIDER ?? "mock";
const storageProvider = import.meta.env.VITE_STORAGE_PROVIDER ?? "local";
const GOLDEN_DEMO_VIDEO_KEY = "videos/30ea2e8e-780a-471b-b85e-80ff8d84fe51.mp4";
const GOLDEN_DEMO_THUMBNAIL_KEY = "thumbnails/30ea2e8e-780a-471b-b85e-80ff8d84fe51.jpg";
const OLD_AWAITING_REVIEW_DAYS = 7;
const OLD_TEST_CORS_DAYS = 3;

const BUILT_IN_DASHBOARD_DEFAULTS = {
  topic: "CORS",
  stylePreset: "clean_3d_cartoon",
  targetPlatforms: ["instagram", "tiktok", "youtube"],
  captionTone: "playful explainer",
  durationPreferenceSeconds: 18,
  audienceLevel: "beginner",
  contentFormat: "coding metaphor",
};

type DashboardDefaultsControlledField =
  | "stylePreset"
  | "targetPlatforms"
  | "captionTone"
  | "durationPreferenceSeconds"
  | "audienceLevel"
  | "contentFormat";

type DashboardEditedFields = Record<DashboardDefaultsControlledField, boolean>;

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

function isOlderThanDays(value: string, days: number) {
  const createdAt = new Date(value).getTime();
  if (Number.isNaN(createdAt)) {
    return false;
  }
  return Date.now() - createdAt >= days * 24 * 60 * 60 * 1000;
}

function matchesStatusFilter(run: PipelineRunSummary, statusFilter: RunStatusFilter) {
  if (statusFilter === "all" || statusFilter === "archived") {
    return true;
  }
  if (statusFilter === "awaiting_review") {
    return run.status === "awaiting_review";
  }
  if (statusFilter === "completed") {
    return ["completed", "cancelled"].includes(run.status);
  }
  if (statusFilter === "failed") {
    return run.status === "failed";
  }
  return true;
}

function matchesProviderFilter(run: PipelineRunSummary, providerFilter: RunProviderFilter) {
  if (providerFilter === "all") {
    return true;
  }
  return String(run.provider ?? "").toLowerCase() === providerFilter;
}

function matchesTopicSearch(run: PipelineRunSummary, topicSearch: string) {
  if (!topicSearch.trim()) {
    return true;
  }
  return run.topic.toLowerCase().includes(topicSearch.trim().toLowerCase());
}

export function DashboardPage() {
  const [handoffCapture] = useState(() => readDashboardPrefillCapture());
  const handoffPrefill = handoffCapture.prefill;
  const handoffProtectedFields = useMemo(
    () => ({
      audienceLevel: Boolean(handoffPrefill?.audienceLevel),
      contentFormat: Boolean(handoffPrefill?.contentFormat),
    }),
    [handoffPrefill],
  );
  const editedFieldsRef = useRef<DashboardEditedFields>({
    stylePreset: false,
    targetPlatforms: false,
    captionTone: false,
    durationPreferenceSeconds: false,
    audienceLevel: false,
    contentFormat: false,
  });

  const [topic, setTopic] = useState(handoffPrefill?.topic ?? BUILT_IN_DASHBOARD_DEFAULTS.topic);
  const [stylePreset, setStylePreset] = useState(BUILT_IN_DASHBOARD_DEFAULTS.stylePreset);
  const [targetPlatforms, setTargetPlatforms] = useState<string[]>(BUILT_IN_DASHBOARD_DEFAULTS.targetPlatforms);
  const [captionTone, setCaptionTone] = useState(BUILT_IN_DASHBOARD_DEFAULTS.captionTone);
  const [durationPreferenceSeconds, setDurationPreferenceSeconds] = useState(BUILT_IN_DASHBOARD_DEFAULTS.durationPreferenceSeconds);
  const [audienceLevel, setAudienceLevel] = useState(
    handoffPrefill?.audienceLevel ?? BUILT_IN_DASHBOARD_DEFAULTS.audienceLevel,
  );
  const [contentFormat, setContentFormat] = useState(
    handoffPrefill?.contentFormat ?? BUILT_IN_DASHBOARD_DEFAULTS.contentFormat,
  );
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
  const [archivedRunIds, setArchivedRunIds] = useState<string[]>([]);
  const [selectedRunIds, setSelectedRunIds] = useState<string[]>([]);
  const [statusFilter, setStatusFilter] = useState<RunStatusFilter>("all");
  const [providerFilter, setProviderFilter] = useState<RunProviderFilter>("all");
  const [topicSearch, setTopicSearch] = useState("");
  const [showArchived, setShowArchived] = useState(false);
  const [handoffNotice, setHandoffNotice] = useState<{ topic: string; sourceBatchName: string } | null>(
    handoffPrefill?.sourceBatchName
      ? {
          topic: handoffPrefill.topic,
          sourceBatchName: handoffPrefill.sourceBatchName,
        }
      : null,
  );

  function markFieldEdited(field: DashboardDefaultsControlledField) {
    editedFieldsRef.current[field] = true;
  }

  function applyDefaults(config: AccountDefaults["account_config_json"], options?: { respectHandoffAndEdits?: boolean }) {
    const nextStylePreset = String(config.default_style_preset ?? BUILT_IN_DASHBOARD_DEFAULTS.stylePreset);
    const nextTargetPlatforms = Array.isArray(config.target_platforms)
      ? config.target_platforms
      : BUILT_IN_DASHBOARD_DEFAULTS.targetPlatforms;
    const nextCaptionTone = String(config.default_caption_tone ?? BUILT_IN_DASHBOARD_DEFAULTS.captionTone);
    const nextDurationPreferenceSeconds = Number(
      config.default_duration_seconds ?? BUILT_IN_DASHBOARD_DEFAULTS.durationPreferenceSeconds,
    );
    const nextAudienceLevel = String(config.default_audience_level ?? BUILT_IN_DASHBOARD_DEFAULTS.audienceLevel);
    const nextContentFormat = String(config.default_content_format ?? BUILT_IN_DASHBOARD_DEFAULTS.contentFormat);

    if (options?.respectHandoffAndEdits) {
      const editedFields = editedFieldsRef.current;
      if (!editedFields.stylePreset) {
        setStylePreset(nextStylePreset);
      }
      if (!editedFields.targetPlatforms) {
        setTargetPlatforms(nextTargetPlatforms);
      }
      if (!editedFields.captionTone) {
        setCaptionTone(nextCaptionTone);
      }
      if (!editedFields.durationPreferenceSeconds) {
        setDurationPreferenceSeconds(nextDurationPreferenceSeconds);
      }
      if (!handoffProtectedFields.audienceLevel && !editedFields.audienceLevel) {
        setAudienceLevel(nextAudienceLevel);
      }
      if (!handoffProtectedFields.contentFormat && !editedFields.contentFormat) {
        setContentFormat(nextContentFormat);
      }
      return;
    }

    setStylePreset(nextStylePreset);
    setTargetPlatforms(nextTargetPlatforms);
    setCaptionTone(nextCaptionTone);
    setDurationPreferenceSeconds(nextDurationPreferenceSeconds);
    if (!handoffPrefill?.audienceLevel) {
      setAudienceLevel(nextAudienceLevel);
    }
    if (!handoffPrefill?.contentFormat) {
      setContentFormat(nextContentFormat);
    }
  }

  function togglePlatform(platform: string) {
    markFieldEdited("targetPlatforms");
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
    setArchivedRunIds(loadArchivedRunIds());
  }, []);

  useEffect(() => {
    if (!handoffCapture.shouldClearStorage) {
      return;
    }
    clearDashboardPrefill();
  }, [handoffCapture]);

  useEffect(() => {
    api.getAccountDefaults().then((data) => {
      setDefaults(data);
      applyDefaults(data.account_config_json, { respectHandoffAndEdits: true });
    }).catch((err) => setError(err.message));
    api.getHealthDetails().then(setHealthDetails).catch(() => undefined);
    loadRuns().catch((err) => setError(err.message));
  }, []);

  useEffect(() => {
    if (selectedRunId) {
      loadDetail(selectedRunId).catch((err) => setError(err.message));
    } else {
      setDetail(null);
    }
    setPaidRunwayConfirmed(false);
  }, [selectedRunId]);

  const sortedRuns = useMemo(() => {
    return [...runs].sort((left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime());
  }, [runs]);

  const visibleRuns = useMemo(() => {
    return sortedRuns.filter((run) => {
      const isArchived = archivedRunIds.includes(run.id);
      if (statusFilter === "archived") {
        if (!isArchived) {
          return false;
        }
      } else if (!showArchived && isArchived) {
        return false;
      }
      return matchesStatusFilter(run, statusFilter)
        && matchesProviderFilter(run, providerFilter)
        && matchesTopicSearch(run, topicSearch);
    });
  }, [archivedRunIds, providerFilter, showArchived, sortedRuns, statusFilter, topicSearch]);

  const visibleRunIds = useMemo(() => visibleRuns.map((run) => run.id), [visibleRuns]);

  useEffect(() => {
    setSelectedRunIds((current) => current.filter((runId) => visibleRunIds.includes(runId)));
  }, [visibleRunIds]);

  useEffect(() => {
    if (visibleRuns.length === 0) {
      setSelectedRunId(null);
      return;
    }
    if (!selectedRunId || !visibleRunIds.includes(selectedRunId)) {
      setSelectedRunId(visibleRuns[0].id);
    }
  }, [selectedRunId, visibleRunIds, visibleRuns]);

  function persistArchivedRunIds(nextRunIds: string[]) {
    setArchivedRunIds(nextRunIds);
    saveArchivedRunIds(nextRunIds);
  }

  function archiveRuns(runIds: string[]) {
    if (runIds.length === 0) {
      return;
    }
    persistArchivedRunIds([...archivedRunIds, ...runIds]);
  }

  function unarchiveRuns(runIds: string[]) {
    if (runIds.length === 0) {
      return;
    }
    persistArchivedRunIds(archivedRunIds.filter((runId) => !runIds.includes(runId)));
  }

  function getSelectedVisibleRunIds() {
    return selectedRunIds.filter((runId) => visibleRunIds.includes(runId));
  }

  function confirmArchive(runIds: string[], title: string) {
    if (runIds.length === 0) {
      return false;
    }
    return window.confirm(
      `${title}\n\nThis only hides ${runIds.length} run${runIds.length === 1 ? "" : "s"} locally in this browser. It does not delete database records or change backend data.`,
    );
  }

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
      setHandoffNotice(null);
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

  function handleArchiveRun(runId: string) {
    archiveRuns([runId]);
    setSelectedRunIds((current) => current.filter((item) => item !== runId));
  }

  function handleUnarchiveRun(runId: string) {
    unarchiveRuns([runId]);
  }

  function handleSelectionChange(runId: string, selected: boolean) {
    setSelectedRunIds((current) => {
      if (selected) {
        return current.includes(runId) ? current : [...current, runId];
      }
      return current.filter((item) => item !== runId);
    });
  }

  function handleSelectAllVisible() {
    setSelectedRunIds(visibleRunIds);
  }

  function handleClearSelection() {
    setSelectedRunIds([]);
  }

  function handleArchiveSelected() {
    const runIds = getSelectedVisibleRunIds();
    if (!confirmArchive(runIds, "Archive the selected visible runs?")) {
      return;
    }
    archiveRuns(runIds);
    setSelectedRunIds([]);
  }

  function handleArchiveFailedRuns() {
    const runIds = sortedRuns
      .filter((run) => run.status === "failed" && !archivedRunIds.includes(run.id))
      .map((run) => run.id);
    if (!confirmArchive(runIds, "Archive all failed runs?")) {
      return;
    }
    archiveRuns(runIds);
  }

  function handleArchiveOldAwaitingReviewRuns() {
    const runIds = sortedRuns
      .filter((run) => run.status === "awaiting_review" && !archivedRunIds.includes(run.id) && isOlderThanDays(run.created_at, OLD_AWAITING_REVIEW_DAYS))
      .map((run) => run.id);
    if (!confirmArchive(runIds, `Archive awaiting-review runs older than ${OLD_AWAITING_REVIEW_DAYS} days?`)) {
      return;
    }
    archiveRuns(runIds);
  }

  function handleArchiveOldCorsRuns() {
    const runIds = sortedRuns
      .filter((run) => {
        const provider = String(run.provider ?? "").toLowerCase();
        return !archivedRunIds.includes(run.id)
          && provider === "mock"
          && run.topic.toLowerCase().includes("cors")
          && isOlderThanDays(run.created_at, OLD_TEST_CORS_DAYS);
      })
      .map((run) => run.id);
    if (!confirmArchive(runIds, `Archive mock CORS runs older than ${OLD_TEST_CORS_DAYS} days?`)) {
      return;
    }
    archiveRuns(runIds);
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
      <section className="panel create-run-panel">
        <div className="panel-header">
          <h2>Create Run</h2>
          <div className="button-row">
            <button className="secondary" type="button" onClick={() => defaults ? applyDefaults(defaults.account_config_json) : undefined}>
              Reset To Defaults
            </button>
            <button onClick={handleCreateRun}>Create Run</button>
          </div>
        </div>
        {handoffNotice ? (
          <div className="notice-card">
            <div className="panel-header">
              <strong>Dashboard handoff</strong>
              <button className="secondary" type="button" onClick={() => setHandoffNotice(null)}>
                Dismiss
              </button>
            </div>
            <p>
              Loaded '{handoffNotice.topic}' from {handoffNotice.sourceBatchName}. Review the settings, then create the run.
            </p>
          </div>
        ) : null}
        <div className="form-grid">
          <label className="field">
            <span>Topic</span>
            <input value={topic} onChange={(event) => setTopic(event.target.value)} placeholder="Topic" />
          </label>
          <label className="field">
            <span>Style Preset</span>
            <select
              value={stylePreset}
              onChange={(event) => {
                markFieldEdited("stylePreset");
                setStylePreset(event.target.value);
              }}
            >
              {STYLE_PRESETS.map((preset) => (
                <option key={preset} value={preset}>
                  {preset}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Caption Tone</span>
            <input
              value={captionTone}
              onChange={(event) => {
                markFieldEdited("captionTone");
                setCaptionTone(event.target.value);
              }}
            />
          </label>
          <label className="field">
            <span>Duration Preference</span>
            <input
              type="number"
              min={5}
              max={30}
              value={durationPreferenceSeconds}
              onChange={(event) => {
                markFieldEdited("durationPreferenceSeconds");
                setDurationPreferenceSeconds(Number(event.target.value));
              }}
            />
          </label>
          <label className="field">
            <span>Audience Level</span>
            <select
              value={audienceLevel}
              onChange={(event) => {
                markFieldEdited("audienceLevel");
                setAudienceLevel(event.target.value);
              }}
            >
              {AUDIENCE_LEVELS.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
          </label>
          <label className="field">
            <span>Content Format</span>
            <select
              value={contentFormat}
              onChange={(event) => {
                markFieldEdited("contentFormat");
                setContentFormat(event.target.value);
              }}
            >
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
      </section>
      {error ? <p className="error">{error}</p> : null}
      <div className="dashboard-grid">
        <RunList
          runs={visibleRuns}
          totalRuns={runs.length}
          selectedRunId={selectedRunId}
          selectedRunIds={selectedRunIds}
          statusFilter={statusFilter}
          providerFilter={providerFilter}
          topicSearch={topicSearch}
          showArchived={showArchived}
          archivedRunIds={archivedRunIds}
          onSelect={setSelectedRunId}
          onSelectionChange={handleSelectionChange}
          onSelectAllVisible={handleSelectAllVisible}
          onClearSelection={handleClearSelection}
          onStatusFilterChange={setStatusFilter}
          onProviderFilterChange={setProviderFilter}
          onTopicSearchChange={setTopicSearch}
          onShowArchivedChange={setShowArchived}
          onArchiveRun={handleArchiveRun}
          onUnarchiveRun={handleUnarchiveRun}
          onArchiveSelected={handleArchiveSelected}
          onArchiveFailedRuns={handleArchiveFailedRuns}
          onArchiveOldAwaitingReviewRuns={handleArchiveOldAwaitingReviewRuns}
          onArchiveOldCorsRuns={handleArchiveOldCorsRuns}
        />
        <div className="stack">
          <div className="panel detail-panel">
            <div className="panel-header">
              <h2>Run Details</h2>
              {selectedRunId ? (
                archivedRunIds.includes(selectedRunId) ? (
                  <button className="secondary" type="button" onClick={() => handleUnarchiveRun(selectedRunId)}>
                    Unarchive run
                  </button>
                ) : (
                  <button className="secondary" type="button" onClick={() => handleArchiveRun(selectedRunId)}>
                    Archive run
                  </button>
                )
              ) : null}
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
                  <div><span>Archive State</span><strong>{selectedRunId && archivedRunIds.includes(selectedRunId) ? "Archived locally" : "Visible"}</strong></div>
                </div>
                <p className="subtle">Archive state is stored locally in <code>{getArchivedRunsStorageKey()}</code> and does not change backend records.</p>
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
                  {runStatus !== "awaiting_review" ? <Link className="inline-link" to={`/ideas?run=${selectedRunId}`}>Open Ideas</Link> : null}
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
