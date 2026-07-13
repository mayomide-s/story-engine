import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api, PipelineRunDetail, PipelineRunSummary } from "../api/client";
import { ExportPackPanel } from "../components/ExportPackPanel";
import { EventTimeline } from "../components/EventTimeline";
import { PerformanceLearningsSummary } from "../components/PerformanceLearningsSummary";
import { PerformanceWinnerSummary } from "../components/PerformanceWinnerSummary";
import { YouTubePublicationPanel } from "../components/YouTubePublicationPanel";
import { normalizeQualityChecklist } from "../qualityChecklist";
import { formatProvider, formatRunStatus, formatVideoStatus } from "../utils/display";

const videoProvider = import.meta.env.VITE_VIDEO_PROVIDER ?? "mock";
const storageProvider = import.meta.env.VITE_STORAGE_PROVIDER ?? "local";

function pickPreferredRunId(runs: PipelineRunSummary[]) {
  const preferredRun =
    runs.find((run) => run.status === "completed") ??
    runs.find((run) => run.video_status === "approved") ??
    runs.find((run) => run.video_status === "completed") ??
    runs.find((run) => run.status === "needs_review") ??
    runs.find((run) => run.provider_job_id || run.video_status) ??
    runs[0];
  return preferredRun?.id ?? "";
}

function inferStorageLabel(publicUrl: unknown, fallback: string) {
  const url = String(publicUrl ?? "");
  if (url.includes("r2.dev") || url.includes(".r2.")) {
    return "r2";
  }
  if (url.includes("/assets/")) {
    return "local";
  }
  return fallback;
}

function buildPromptPreview(prompt: string) {
  if (prompt.length <= 240) {
    return prompt;
  }
  return `${prompt.slice(0, 240).trim()}...`;
}

function formatAdherenceValue(value: unknown) {
  if (value === null || value === undefined || value === "") {
    return "Unavailable";
  }
  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
  }
  return String(value);
}

function formatStoryReviewStatus(value: unknown) {
  const label = String(value ?? "unavailable");
  return label.replace(/_/g, " ");
}

function formatCriterionValue(value: unknown) {
  const normalized = String(value ?? "uncertain");
  if (normalized === "true") return "Yes";
  if (normalized === "false") return "No";
  return "Uncertain";
}

function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  }

  return (
    <button type="button" className="secondary" onClick={handleCopy}>
      {copied ? `${label} copied` : `Copy ${label}`}
    </button>
  );
}

export function VideoReviewPage() {
  const [searchParams] = useSearchParams();
  const [runs, setRuns] = useState<PipelineRunSummary[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string>("");
  const [detail, setDetail] = useState<PipelineRunDetail | null>(null);
  const [error, setError] = useState<string>("");
  const [isRechecking, setIsRechecking] = useState(false);
  const [isRecheckingStory, setIsRecheckingStory] = useState(false);
  const [showFullPrompt, setShowFullPrompt] = useState(false);
  const [isNarrationBusy, setIsNarrationBusy] = useState(false);
  const [draftSegments, setDraftSegments] = useState<Record<string, unknown>[]>([]);
  const [draftFullText, setDraftFullText] = useState("");
  const [narrationVoice, setNarrationVoice] = useState("alloy");

  useEffect(() => {
    const requestedRunId = searchParams.get("run");
    api.listRuns()
      .then((data) => {
        setRuns(data);
        setError("");
        if (requestedRunId && data.some((run) => run.id === requestedRunId)) {
          setSelectedRunId(requestedRunId);
        } else if (data.length > 0) {
          setSelectedRunId(pickPreferredRunId(data));
        }
      })
      .catch((requestError: Error) => setError(requestError.message));
  }, [searchParams]);

  useEffect(() => {
    if (selectedRunId) {
      api.getRun(selectedRunId).then(setDetail).catch((requestError: Error) => setError(requestError.message));
    }
    setShowFullPrompt(false);
  }, [selectedRunId]);

  useEffect(() => {
    const narrationDraft = detail?.narration_draft as Record<string, unknown> | null | undefined;
    const scriptJson = narrationDraft?.script_json as { segments?: unknown[] } | undefined;
    const nextSegments = Array.isArray(scriptJson?.segments) ? scriptJson.segments as Record<string, unknown>[] : [];
    setDraftSegments(nextSegments.map((segment) => ({ ...segment })));
    setDraftFullText(String(narrationDraft?.full_spoken_text ?? ""));
    const latestNarrationRender = detail?.latest_narration_render as Record<string, unknown> | null | undefined;
    setNarrationVoice(String(latestNarrationRender?.voice ?? narrationDraft?.voice ?? "alloy"));
  }, [detail]);

  async function refreshDetail() {
    if (!selectedRunId) return;
    const data = await api.getRun(selectedRunId);
    setDetail(data);
  }

  const manualPackage = detail?.manual_post_package as Record<string, unknown> | null;
  const finalAssetSelection = detail?.final_asset_selection ?? null;
  const winnerSelection = detail?.winner_selection ?? null;
  const learningsSummary = detail?.performance_learnings_summary ?? null;
  const video = detail?.video as Record<string, unknown> | null;
  const run = detail?.pipeline_run as Record<string, unknown> | null;
  const narrationDraft = detail?.narration_draft as Record<string, unknown> | null;
  const latestNarrationRender = detail?.latest_narration_render as Record<string, unknown> | null;
  const qualityChecks = detail?.quality_checks ?? [];
  const latestQualityCheck = qualityChecks[qualityChecks.length - 1] as Record<string, unknown> | undefined;
  const storyAdherence = detail?.story_adherence_review as Record<string, unknown> | null;
  const assets = detail?.assets ?? [];
  const videoAsset = assets.find((asset) => asset.asset_type === "video_mp4");
  const thumbnailAsset = assets.find((asset) => asset.asset_type === "thumbnail");
  const platformVariants = (manualPackage?.platform_variants_json as Record<string, unknown> | undefined) ?? {};
  const rawQualityChecks = latestQualityCheck?.checks_json && typeof latestQualityCheck.checks_json === "object"
    ? latestQualityCheck.checks_json as Record<string, unknown>
    : {};
  const qualityChecklist = normalizeQualityChecklist(rawQualityChecks, String(video?.provider ?? ""));
  const durationInfo = {
    requested: rawQualityChecks.requested_duration_seconds,
    actual: rawQualityChecks.actual_duration_seconds,
  };
  const canRecheck = Boolean(
    selectedRunId &&
    videoAsset &&
    video &&
    (String(run?.status ?? "") === "needs_review" || String(video.status ?? "") === "rejected"),
  );
  const canRecheckStory = Boolean(selectedRunId && videoAsset && video && String(run?.status ?? "") === "completed");
  const generatedProvider = String(video?.provider ?? videoProvider);
  const generatedStorage = inferStorageLabel(videoAsset?.public_url, storageProvider);
  const badgeLabel = `${generatedProvider}/${generatedStorage.toUpperCase()}`;
  const promptText = String(video?.prompt_text ?? "");
  const promptPreview = buildPromptPreview(promptText);

  async function handleRecheck() {
    if (!selectedRunId) {
      return;
    }
    setIsRechecking(true);
    setError("");
    try {
      const refreshed = await api.recheckRun(selectedRunId, "Rechecked after duration alignment");
      setDetail(refreshed);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to re-run quality check.");
    } finally {
      setIsRechecking(false);
    }
  }

  async function handleStoryRecheck() {
    if (!selectedRunId) {
      return;
    }
    setIsRecheckingStory(true);
    setError("");
    try {
      const refreshed = await api.recheckStoryAdherence(selectedRunId, "Re-run sampled-frame story review");
      setDetail(refreshed);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to re-run story adherence review.");
    } finally {
      setIsRecheckingStory(false);
    }
  }

  const packageCaption = String(manualPackage?.caption ?? "");
  const packageHashtags = Array.isArray(manualPackage?.hashtags_json) ? manualPackage.hashtags_json.join(" ") : "";
  const instagramVariant = platformVariants.instagram as Record<string, unknown> | undefined;
  const tiktokVariant = platformVariants.tiktok as Record<string, unknown> | undefined;
  const youtubeVariant = platformVariants.youtube as Record<string, unknown> | undefined;
  const alternativeCaptions = Array.isArray(platformVariants.alternative_captions) ? platformVariants.alternative_captions : [];
  const alternativeHooks = Array.isArray(platformVariants.alternative_hooks) ? platformVariants.alternative_hooks : [];
  const narrationAudioAsset = latestNarrationRender?.audio_asset as Record<string, unknown> | undefined;
  const narrationCaptionAsset = latestNarrationRender?.caption_asset as Record<string, unknown> | undefined;
  const narratedVideoAsset = latestNarrationRender?.rendered_video_asset as Record<string, unknown> | undefined;
  const selectedFinalAsset = finalAssetSelection?.asset as Record<string, unknown> | undefined;
  const storyHumanReview = (storyAdherence?.human_review as Record<string, unknown> | null) ?? null;
  const storyApproved = Boolean(
    storyHumanReview?.decision === "approve" ||
    (!storyHumanReview?.decision && String(storyAdherence?.review_status ?? "") === "accept")
  );
  const narrationDraftUsable = Boolean(narrationDraft?.has_valid_content);
  const manualPostingStarted = Boolean(
    manualPackage &&
    (
      String(manualPackage.manual_posting_status ?? "not_posted") !== "not_posted" ||
      manualPackage.tiktok_post_url ||
      manualPackage.instagram_post_url ||
      manualPackage.youtube_post_url
    )
  );
  const narrationRenderApproved = latestNarrationRender?.status === "approved" && narratedVideoAsset;
  const narrationAlreadySelected =
    finalAssetSelection?.source === "narration_render" &&
    finalAssetSelection?.narration_render_id === latestNarrationRender?.id;

  async function handleSelectFinalAsset(source: "source_video" | "narration_render") {
    if (!selectedRunId) return;
    let confirmChangeAfterPosting = false;
    const changingSelection = source !== finalAssetSelection?.source;
    if (manualPostingStarted && changingSelection) {
      confirmChangeAfterPosting = window.confirm(
        "Manual posting has already started for this run. Change the selected final video anyway?"
      );
      if (!confirmChangeAfterPosting) return;
    }
    setIsNarrationBusy(true);
    setError("");
    try {
      const refreshed = await api.selectFinalAsset(selectedRunId, {
        source,
        narration_render_id: source === "narration_render" ? String(latestNarrationRender?.id ?? "") : null,
        confirm_change_after_posting: confirmChangeAfterPosting,
      });
      setDetail(refreshed);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to update the final video selection.");
    } finally {
      setIsNarrationBusy(false);
    }
  }

  async function handleCreateNarrationDraft(regenerate = false) {
    if (!selectedRunId) return;
    const needsPaidDraftConfirmation = window.confirm(
      "Continue creating a narration draft? If the writer provider is OpenAI, this will trigger a paid narration-writing call."
    );
    if (!needsPaidDraftConfirmation && regenerate) {
      return;
    }
    setIsNarrationBusy(true);
    setError("");
    try {
      const refreshed = regenerate
        ? await api.regenerateNarrationDraft(selectedRunId, needsPaidDraftConfirmation)
        : await api.createNarrationDraft(selectedRunId, needsPaidDraftConfirmation);
      setDetail(refreshed);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to create the narration draft.");
    } finally {
      setIsNarrationBusy(false);
    }
  }

  async function handleSaveNarrationDraft() {
    if (!selectedRunId || !narrationDraftUsable) return;
    setIsNarrationBusy(true);
    setError("");
    try {
      const refreshed = await api.patchNarrationDraft(selectedRunId, {
        segments: draftSegments,
        full_spoken_text: draftFullText,
        estimated_word_count: draftFullText.split(/\s+/).filter(Boolean).length,
      });
      setDetail(refreshed);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to save the narration draft.");
    } finally {
      setIsNarrationBusy(false);
    }
  }

  async function handleGenerateNarratedVideo() {
    if (!selectedRunId || !narrationDraftUsable) return;
    const confirmPaid = window.confirm("Generate narrated video now? This may trigger a paid OpenAI speech call.");
    if (!confirmPaid) return;
    let confirmUnapprovedStory = false;
    if (!storyApproved) {
      confirmUnapprovedStory = window.confirm("This story is not fully approved yet. Continue and spend narration credits anyway?");
      if (!confirmUnapprovedStory) return;
    }
    setIsNarrationBusy(true);
    setError("");
    try {
      const refreshed = await api.createNarrationRender(selectedRunId, {
        confirm_paid_narration: true,
        confirm_unapproved_story: confirmUnapprovedStory,
        voice: narrationVoice,
      });
      setDetail(refreshed);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to create the narrated render.");
    } finally {
      setIsNarrationBusy(false);
    }
  }

  async function handleRecomposeNarratedVideo() {
    if (!selectedRunId || !latestNarrationRender?.id) return;
    setIsNarrationBusy(true);
    setError("");
    try {
      const refreshed = await api.recomposeNarrationRender(selectedRunId, String(latestNarrationRender.id));
      setDetail(refreshed);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to recompose the narrated video.");
    } finally {
      setIsNarrationBusy(false);
    }
  }

  async function handleNarrationHumanReview(decision: "approve" | "needs_revision" | "reject") {
    if (!selectedRunId || !latestNarrationRender?.id) return;
    setIsNarrationBusy(true);
    setError("");
    try {
      const refreshed = await api.submitNarrationHumanReview(selectedRunId, String(latestNarrationRender.id), decision, "");
      setDetail(refreshed);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to save the narration review.");
    } finally {
      setIsNarrationBusy(false);
    }
  }

  function updateDraftSegment(index: number, key: string, value: string) {
    setDraftSegments((current) =>
      current.map((segment, segmentIndex) => (
        segmentIndex === index
          ? {
              ...segment,
              [key]: key.endsWith("_seconds") ? Number(value) : value,
            }
          : segment
      ))
    );
  }

  return (
    <div className="page stack">
      <section className="page-header-card panel">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Video Review</p>
            <h2>Review the generated explainer and posting package.</h2>
          </div>
          <div className="panel-actions">
            <span className="status-pill success">{badgeLabel}</span>
            <select value={selectedRunId} onChange={(event) => setSelectedRunId(event.target.value)}>
              <option value="">Select a run</option>
              {runs.map((run) => (
                <option key={run.id} value={run.id}>
                  {run.topic}
                </option>
              ))}
            </select>
          </div>
        </div>
        {video ? (
          <div className="key-grid">
            <div><span>Topic</span><strong>{String(run?.topic ?? "")}</strong></div>
            <div><span>Status</span><strong>{formatVideoStatus(String(video.status))}</strong></div>
            <div><span>Provider</span><strong>{formatProvider(generatedProvider)}</strong></div>
            <div><span>Technical Quality</span><strong>{String(latestQualityCheck?.score ?? "n/a")}</strong></div>
          </div>
        ) : null}
      </section>
      <div className="review-grid">
      <section className="panel">
        {error ? <p className="error-text">{error}</p> : null}
        {video ? (
          <div className="stack">
            <div className="panel inset">
              <div className="panel-header">
                <h3>Video Status</h3>
                <div className="panel-actions">
                  {canRecheck ? (
                    <button type="button" onClick={handleRecheck} disabled={isRechecking}>
                      {isRechecking ? "Rechecking..." : "Re-run Quality Check"}
                    </button>
                  ) : null}
                  {canRecheckStory ? (
                    <button type="button" className="secondary" onClick={handleStoryRecheck} disabled={isRecheckingStory}>
                      {isRecheckingStory ? "Reviewing..." : "Re-run Story Review"}
                    </button>
                  ) : null}
                  {selectedRunId ? <Link className="inline-link" to={`/ideas?run=${selectedRunId}`}>Back To Ideas</Link> : null}
                  {selectedRunId && String(run?.status ?? "") === "completed" && manualPackage ? (
                    <Link className="inline-link" to={`/performance/${selectedRunId}`}>Open Performance</Link>
                  ) : null}
                </div>
              </div>
              <div className="key-grid">
                <div><span>Status</span><strong>{formatVideoStatus(String(video.status))}</strong></div>
                <div><span>Provider</span><strong>{formatProvider(String(video.provider))}</strong></div>
                <div><span>Duration</span><strong>{String(video.duration_seconds)}s</strong></div>
                <div><span>Run Status</span><strong>{formatRunStatus(String(run?.status ?? ""))}</strong></div>
                <div><span>Story Review</span><strong>{formatStoryReviewStatus(storyAdherence?.review_status)}</strong></div>
              </div>
              <p className="subtle">Generated with {generatedProvider}, stored in {generatedStorage.toUpperCase()}.</p>
              <p><strong>Review Notes:</strong> {String(video.review_notes ?? run?.review_notes ?? "No review notes yet.")}</p>
              {run?.error_message ? (
                <div className="notice-card danger">
                  <strong>Latest Error</strong>
                  <p>{String(run.error_message)}</p>
                </div>
              ) : null}
            </div>

            {videoAsset ? (
              <div className="panel inset feature-video">
              <div className="panel-header">
                <h3>{finalAssetSelection?.source === "narration_render" ? "Selected Final Video" : "Generated Video"}</h3>
                <div className="button-row">
                  <CopyButton text={String((selectedFinalAsset ?? videoAsset).public_url)} label="video URL" />
                </div>
              </div>
              <video
                className="video-player large"
                  controls
                  preload="metadata"
                  poster={thumbnailAsset ? String(thumbnailAsset.public_url) : undefined}
                  src={String((selectedFinalAsset ?? videoAsset).public_url)}
                >
                  Your browser does not support the video preview.
                </video>
                <p className="subtle">
                  Final video: {finalAssetSelection?.source === "narration_render" ? "Narrated" : "Original"}
                  {finalAssetSelection?.selected_at ? ` · selected ${new Date(String(finalAssetSelection.selected_at)).toLocaleString()}` : ""}
                </p>
              </div>
            ) : null}

            <PerformanceWinnerSummary
              winnerSelection={winnerSelection}
              performanceHref={selectedRunId ? `/performance/${selectedRunId}` : undefined}
              heading="Manual winner"
              compact
            />
            <PerformanceLearningsSummary
              summary={learningsSummary}
              performanceHref={selectedRunId ? `/performance/${selectedRunId}` : undefined}
              compact
            />
            {selectedRunId ? (
              <YouTubePublicationPanel
                runId={selectedRunId}
                runStatus={String(run?.status ?? "")}
                finalAssetSelection={finalAssetSelection}
                manualPostPackage={manualPackage}
              />
            ) : null}

            <div className="panel inset scroll-panel-box">
              <h3>Generated Assets</h3>
              <div className="asset-grid">
                {videoAsset ? (
                  <div className="content-card">
                    <div className="content-meta">
                      <strong>Video</strong>
                      <span>{String(videoAsset.mime_type)}</span>
                    </div>
                    <p><strong>Dimensions:</strong> {String(videoAsset.width)} x {String(videoAsset.height)}</p>
                    <p><strong>Duration:</strong> {String(videoAsset.duration_seconds)}s</p>
                    <div className="button-row">
                      <CopyButton text={String(videoAsset.public_url)} label="video URL" />
                    </div>
                  </div>
                ) : null}
                {thumbnailAsset ? (
                  <div className="content-card">
                    <div className="content-meta">
                      <strong>Thumbnail</strong>
                      <span>{String(thumbnailAsset.mime_type)}</span>
                    </div>
                    <div className="button-row">
                      <CopyButton text={String(thumbnailAsset.public_url)} label="thumbnail URL" />
                    </div>
                  </div>
                ) : null}
              </div>
              <details className="technical-disclosure">
                <summary>Show technical asset details</summary>
                <div className="stack compact technical-stack">
                  {videoAsset ? (
                    <div className="copy-block">
                      <strong>Video asset</strong>
                      <pre>{`URL: ${String(videoAsset.public_url)}\nStorage key: ${String(videoAsset.storage_key)}`}</pre>
                    </div>
                  ) : null}
                  {thumbnailAsset ? (
                    <div className="copy-block">
                      <strong>Thumbnail asset</strong>
                      <pre>{`URL: ${String(thumbnailAsset.public_url)}\nStorage key: ${String(thumbnailAsset.storage_key)}`}</pre>
                    </div>
                  ) : null}
                </div>
              </details>
            </div>

            <div className="panel inset">
              <details className="technical-disclosure">
                <summary>Show final prompt</summary>
                <div className="panel-header technical-panel-header">
                  <h3>Final Prompt</h3>
                  <div className="button-row">
                    <CopyButton text={promptText} label="prompt" />
                    {promptText.length > promptPreview.length ? (
                      <button className="secondary" type="button" onClick={() => setShowFullPrompt((current) => !current)}>
                        {showFullPrompt ? "Hide full prompt" : "Show full prompt"}
                      </button>
                    ) : null}
                  </div>
                </div>
                <pre className="preview-block">{showFullPrompt ? promptText : promptPreview}</pre>
              </details>
            </div>

            <div className="panel inset">
              <h3>Technical Quality</h3>
              {latestQualityCheck ? (
                <div className="stack">
                  <div className="key-grid">
                    <div><span>Result</span><strong>{latestQualityCheck.passed ? "Pass" : "Fail"}</strong></div>
                    <div><span>Score</span><strong>{String(latestQualityCheck.score)}</strong></div>
                  </div>
                  <p>{String(latestQualityCheck.llm_critique)}</p>
                  <details className="technical-disclosure">
                    <summary>Show detailed quality checklist</summary>
                    <div className="stack compact technical-stack">
                      <div className="key-grid">
                        <div><span>Requested</span><strong>{String(durationInfo.requested ?? "n/a")}s</strong></div>
                        <div><span>Actual</span><strong>{String(durationInfo.actual ?? "n/a")}s</strong></div>
                      </div>
                      <div className="quality-list">
                        {qualityChecklist.map(([key, value]) => {
                          const passed = Boolean(value);
                          return (
                            <div key={key} className={`quality-item ${passed ? "pass" : "fail"}`}>
                              <strong>{key.split("_").join(" ")}</strong>
                              <span>{passed ? "Pass" : "Fail"}</span>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  </details>
                </div>
              ) : (
                <p className="subtle">No quality check found for this run.</p>
              )}
            </div>

            <div className="panel inset">
              <h3>Story Adherence</h3>
              {storyAdherence ? (
                <div className="stack">
                  <div className="key-grid">
                    <div><span>Automated Status</span><strong>{formatStoryReviewStatus(storyAdherence.review_status)}</strong></div>
                    <div><span>Score</span><strong>{formatAdherenceValue(storyAdherence.score)}</strong></div>
                    <div><span>Critic Version</span><strong>{String(storyAdherence.critic_version ?? "n/a")}</strong></div>
                    <div><span>Model</span><strong>{String(storyAdherence.model ?? "n/a")}</strong></div>
                  </div>
                  <p>{String(storyAdherence.explanation ?? "No story adherence review explanation available.")}</p>
                  {"failure_reason" in storyAdherence && storyAdherence.failure_reason ? <p><strong>Failure reason:</strong> {String(storyAdherence.failure_reason)}</p> : null}
                  {(storyAdherence.human_review as Record<string, unknown> | null)?.decision ? (
                    <div className="notice-card">
                      <strong>Human review</strong>
                      <p>
                        {String((storyAdherence.human_review as Record<string, unknown>).decision ?? "")}
                        {String((storyAdherence.human_review as Record<string, unknown>).notes ?? "") ? ` · ${String((storyAdherence.human_review as Record<string, unknown>).notes ?? "")}` : ""}
                      </p>
                    </div>
                  ) : null}
                  <div className="quality-list">
                    {Object.entries((storyAdherence.criteria as Record<string, unknown> | undefined) ?? {}).map(([key, value]) => {
                      const criterion = value as Record<string, unknown>;
                      return (
                        <div key={key} className="quality-item pass">
                          <strong>{key.split("_").join(" ")}</strong>
                          <span>{formatCriterionValue(criterion.value)}</span>
                          <small>{String(criterion.reason ?? "")}</small>
                        </div>
                      );
                    })}
                  </div>
                  <details className="technical-disclosure">
                    <summary>Show intended outcome contract</summary>
                    <div className="stack compact technical-stack">
                      <div className="copy-block">
                        <strong>Initial state</strong>
                        <pre>{String(storyAdherence.initial_state ?? "")}</pre>
                      </div>
                      <div className="copy-block">
                        <strong>Trigger</strong>
                        <pre>{String(storyAdherence.trigger ?? "")}</pre>
                      </div>
                      <div className="copy-block">
                        <strong>Required transformation</strong>
                        <pre>{String(storyAdherence.required_transformation ?? "")}</pre>
                      </div>
                      <div className="copy-block">
                        <strong>Required final state</strong>
                        <pre>{String(storyAdherence.required_final_state ?? "")}</pre>
                      </div>
                      <div className="copy-block">
                        <strong>Final-state hold</strong>
                        <pre>{String(storyAdherence.final_state_hold ?? "")}</pre>
                      </div>
                      <div className="copy-block">
                        <strong>Prohibited actions</strong>
                        <pre>{Array.isArray(storyAdherence.prohibited_actions) ? storyAdherence.prohibited_actions.map(String).join("\n") : String(storyAdherence.prohibited_actions ?? "")}</pre>
                      </div>
                      <div className="copy-block">
                        <strong>Sampled frames</strong>
                        <pre>{JSON.stringify(storyAdherence.sampled_frames ?? {}, null, 2)}</pre>
                      </div>
                    </div>
                  </details>
                </div>
              ) : (
                <p className="subtle">No story adherence review data found for this run.</p>
              )}
            </div>

            <div className="panel inset">
              <div className="panel-header">
                <h3>Narration and Captions</h3>
                <div className="button-row">
                  <button type="button" className="secondary" onClick={() => handleCreateNarrationDraft(false)} disabled={isNarrationBusy}>
                    {isNarrationBusy ? "Working..." : narrationDraft ? "Refresh Draft" : "Create Narration Draft"}
                  </button>
                  {narrationDraft ? (
                    <button type="button" className="secondary" onClick={() => handleCreateNarrationDraft(true)} disabled={isNarrationBusy}>
                      Regenerate Draft
                    </button>
                  ) : null}
                </div>
              </div>
              {!storyApproved ? (
                <div className="notice-card warning">
                  <strong>Story approval warning</strong>
                  <p>Narration can still be rendered for review, but an extra confirmation is required because the story is not approved yet.</p>
                </div>
              ) : null}
              {narrationDraft ? (
                <div className="stack">
                  <div className="key-grid">
                    <div><span>Draft status</span><strong>{String(narrationDraft.status ?? "n/a").replace(/_/g, " ")}</strong></div>
                    <div><span>Valid content</span><strong>{String(Boolean(narrationDraft.has_valid_content) ? "Yes" : "No")}</strong></div>
                    <div><span>Revision</span><strong>{String(narrationDraft.generation_revision ?? "n/a")}</strong></div>
                    <div><span>Word count</span><strong>{String(narrationDraft.estimated_word_count ?? "n/a")}</strong></div>
                  </div>
                  {narrationDraft.failure_reason ? (
                    <div className={`notice-card ${narrationDraftUsable ? "warning" : "danger"}`}>
                      <strong>Latest draft issue</strong>
                      <p>{String(narrationDraft.failure_reason)}</p>
                    </div>
                  ) : null}
                  {Boolean(narrationDraft.paid_call_outcome_uncertain) ? (
                    <div className="notice-card danger">
                      <strong>Manual recovery required</strong>
                      <p>A paid narration draft call may have completed before its result was fully persisted. Retrying may create another charge.</p>
                    </div>
                  ) : null}
                  <label>
                    <span>Full spoken text</span>
                    <textarea value={draftFullText} onChange={(event) => setDraftFullText(event.target.value)} rows={4} disabled={!narrationDraftUsable || isNarrationBusy} />
                  </label>
                  <div className="stack compact">
                    {draftSegments.map((segment, index) => (
                      <div key={index} className="panel inset">
                        <div className="key-grid">
                          <label>
                            <span>Start</span>
                            <input type="number" step="0.1" value={String(segment.start_seconds ?? "")} onChange={(event) => updateDraftSegment(index, "start_seconds", event.target.value)} disabled={!narrationDraftUsable || isNarrationBusy} />
                          </label>
                          <label>
                            <span>End</span>
                            <input type="number" step="0.1" value={String(segment.end_seconds ?? "")} onChange={(event) => updateDraftSegment(index, "end_seconds", event.target.value)} disabled={!narrationDraftUsable || isNarrationBusy} />
                          </label>
                        </div>
                        <label>
                          <span>Spoken text</span>
                          <textarea value={String(segment.spoken_text ?? "")} onChange={(event) => updateDraftSegment(index, "spoken_text", event.target.value)} rows={2} disabled={!narrationDraftUsable || isNarrationBusy} />
                        </label>
                        <label>
                          <span>Caption text</span>
                          <textarea value={String(segment.caption_text ?? "")} onChange={(event) => updateDraftSegment(index, "caption_text", event.target.value)} rows={2} disabled={!narrationDraftUsable || isNarrationBusy} />
                        </label>
                      </div>
                    ))}
                  </div>
                  <div className="button-row">
                    <button type="button" onClick={handleSaveNarrationDraft} disabled={!narrationDraftUsable || isNarrationBusy}>Save Narration</button>
                    <button type="button" className="secondary" onClick={handleGenerateNarratedVideo} disabled={!narrationDraftUsable || isNarrationBusy}>Generate Narrated Video</button>
                  </div>
                </div>
              ) : (
                <p className="subtle">Create a narration draft to review timing, captions, and speech before generating a narrated MP4.</p>
              )}
              {latestNarrationRender ? (
                <div className="stack">
                  <div className="key-grid">
                    <div><span>Render status</span><strong>{String(latestNarrationRender.status ?? "n/a").replace(/_/g, " ")}</strong></div>
                    <div><span>Voice</span><strong>{String(latestNarrationRender.voice ?? narrationVoice)}</strong></div>
                    <div><span>Speech model</span><strong>{String(latestNarrationRender.speech_model ?? "n/a")}</strong></div>
                    <div><span>Disclosure</span><strong>{Boolean(latestNarrationRender.voice_is_ai_generated) ? "AI-generated narration" : "Not set"}</strong></div>
                  </div>
                  <div className="key-grid">
                    <div><span>Source duration</span><strong>{String(latestNarrationRender.source_duration_seconds ?? "n/a")}s</strong></div>
                    <div><span>Final audio</span><strong>{String(latestNarrationRender.final_audio_duration_seconds ?? "n/a")}s</strong></div>
                    <div><span>Usable window</span><strong>{String(latestNarrationRender.usable_narration_window_seconds ?? "n/a")}s</strong></div>
                    <div><span>Atempo</span><strong>{String(latestNarrationRender.applied_atempo_factor ?? "1.0")}</strong></div>
                  </div>
                  {latestNarrationRender.failure_reason ? (
                    <div className="notice-card warning">
                      <strong>Latest render issue</strong>
                      <p>{String(latestNarrationRender.failure_reason)}</p>
                    </div>
                  ) : null}
                  {Boolean(latestNarrationRender.paid_call_outcome_uncertain) ? (
                    <div className="notice-card danger">
                      <strong>Manual recovery required</strong>
                      <p>A paid narration speech call may have completed before the audio asset was fully persisted. Retrying may create another charge.</p>
                    </div>
                  ) : null}
                  {narratedVideoAsset ? (
                    <div className="panel inset feature-video">
                      <div className="panel-header">
                        <h3>Narrated Video</h3>
                        <div className="button-row">
                          <CopyButton text={String(narratedVideoAsset.public_url)} label="narrated video URL" />
                        </div>
                      </div>
                      <video className="video-player large" controls preload="metadata" src={String(narratedVideoAsset.public_url)}>
                        Your browser does not support the narrated video preview.
                      </video>
                    </div>
                  ) : null}
                  <div className="asset-grid">
                    {narrationAudioAsset ? (
                      <div className="content-card">
                        <div className="content-meta">
                          <strong>Audio</strong>
                          <span>{String(narrationAudioAsset.mime_type ?? "")}</span>
                        </div>
                        <div className="button-row">
                          <CopyButton text={String(narrationAudioAsset.public_url)} label="audio URL" />
                        </div>
                      </div>
                    ) : null}
                    {narrationCaptionAsset ? (
                      <div className="content-card">
                        <div className="content-meta">
                          <strong>Captions</strong>
                          <span>{String(narrationCaptionAsset.mime_type ?? "")}</span>
                        </div>
                        <div className="button-row">
                          <CopyButton text={String(narrationCaptionAsset.public_url)} label="caption URL" />
                        </div>
                      </div>
                    ) : null}
                  </div>
                  <details className="technical-disclosure">
                    <summary>Show caption cues and metadata</summary>
                    <div className="stack compact technical-stack">
                      <div className="copy-block">
                        <strong>Caption cues</strong>
                        <pre>{JSON.stringify(latestNarrationRender.caption_cues_json ?? [], null, 2)}</pre>
                      </div>
                      <div className="copy-block">
                        <strong>AI voice disclosure</strong>
                        <pre>{String(latestNarrationRender.ai_voice_disclosure ?? "AI-generated narration")}</pre>
                      </div>
                    </div>
                  </details>
                  <div className="button-row">
                    <button type="button" className="secondary" onClick={handleRecomposeNarratedVideo} disabled={isNarrationBusy || !latestNarrationRender.audio_asset || Boolean(latestNarrationRender.rendered_video_asset_id)}>
                      Recompose Narrated Video
                    </button>
                    {narrationRenderApproved && !narrationAlreadySelected ? (
                      <button type="button" onClick={() => handleSelectFinalAsset("narration_render")} disabled={isNarrationBusy}>
                        Use as final video
                      </button>
                    ) : null}
                    {narrationAlreadySelected ? <span className="status-pill success">Selected final video</span> : null}
                    {finalAssetSelection?.source === "narration_render" ? (
                      <button type="button" className="secondary" onClick={() => handleSelectFinalAsset("source_video")} disabled={isNarrationBusy}>
                        Use original silent video
                      </button>
                    ) : null}
                    <button type="button" onClick={() => handleNarrationHumanReview("approve")} disabled={isNarrationBusy}>Approve</button>
                    <button type="button" className="secondary" onClick={() => handleNarrationHumanReview("needs_revision")} disabled={isNarrationBusy}>Needs Revision</button>
                    <button type="button" className="secondary" onClick={() => handleNarrationHumanReview("reject")} disabled={isNarrationBusy}>Reject</button>
                  </div>
                  <div className="key-grid">
                    <div><span>Final asset source</span><strong>{finalAssetSelection?.source === "narration_render" ? "Narrated" : "Original"}</strong></div>
                    <div><span>Selection revision</span><strong>{String(finalAssetSelection?.selection_revision ?? 1)}</strong></div>
                    <div><span>Can revert</span><strong>{finalAssetSelection?.can_revert_to_source ? "Yes" : "No"}</strong></div>
                    <div><span>Selected asset URL</span><strong>{String(selectedFinalAsset?.public_url ?? videoAsset?.public_url ?? "n/a")}</strong></div>
                  </div>
                </div>
              ) : null}
            </div>

            <div className="panel inset">
              <h3>Manual Posting Package</h3>
              {manualPackage ? (
                <div className="stack">
                  <div className="copy-block">
                    <div className="content-meta">
                      <strong>Shared Caption</strong>
                      <CopyButton text={packageCaption} label="caption" />
                    </div>
                    <pre>{packageCaption}</pre>
                  </div>
                  <div className="copy-block">
                    <div className="content-meta">
                      <strong>Shared Hashtags</strong>
                      <CopyButton text={packageHashtags} label="hashtags" />
                    </div>
                    <pre>{packageHashtags}</pre>
                  </div>
                  {instagramVariant ? (
                    <div className="copy-block">
                      <div className="content-meta">
                        <strong>Instagram</strong>
                        <CopyButton text={String(instagramVariant.caption ?? "")} label="Instagram caption" />
                      </div>
                      <pre>{String(instagramVariant.caption ?? "")}</pre>
                    </div>
                  ) : null}
                  {tiktokVariant ? (
                    <div className="copy-block">
                      <div className="content-meta">
                        <strong>TikTok</strong>
                        <CopyButton text={String(tiktokVariant.caption ?? "")} label="TikTok caption" />
                      </div>
                      <pre>{String(tiktokVariant.caption ?? "")}</pre>
                    </div>
                  ) : null}
                  {youtubeVariant ? (
                    <div className="copy-block">
                      <div className="content-meta">
                        <strong>YouTube</strong>
                        <CopyButton
                          text={`Title: ${String(youtubeVariant.title ?? "")}\n\nDescription:\n${String(youtubeVariant.description ?? "")}`}
                          label="YouTube title/description"
                        />
                      </div>
                      <pre>{`Title: ${String(youtubeVariant.title ?? "")}\n\nDescription:\n${String(youtubeVariant.description ?? "")}`}</pre>
                    </div>
                  ) : null}
                  {alternativeCaptions.length > 0 ? (
                    <div className="copy-block">
                      <div className="content-meta">
                        <strong>Alternative Captions</strong>
                      </div>
                      <pre>{alternativeCaptions.map((caption, index) => `${index + 1}. ${String(caption)}`).join("\n\n")}</pre>
                    </div>
                  ) : null}
                  {alternativeHooks.length > 0 ? (
                    <div className="copy-block">
                      <div className="content-meta">
                        <strong>Alternative Hooks</strong>
                      </div>
                      <pre>{alternativeHooks.map((hook, index) => `${index + 1}. ${String(hook)}`).join("\n\n")}</pre>
                    </div>
                  ) : null}
                </div>
              ) : (
                <p className="subtle">No manual posting package available yet.</p>
              )}
            </div>

            {selectedRunId ? <ExportPackPanel runId={selectedRunId} onUpdated={refreshDetail} /> : null}
          </div>
        ) : (
          <p className="subtle">Resume a run from the dashboard to generate the video and review package.</p>
        )}
      </section>
      <EventTimeline events={detail?.pipeline_events ?? []} summary="Show technical timeline" />
      </div>
    </div>
  );
}
