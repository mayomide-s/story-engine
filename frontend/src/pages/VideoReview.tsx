import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api, PipelineRunDetail, PipelineRunSummary } from "../api/client";
import { ExportPackPanel } from "../components/ExportPackPanel";
import { EventTimeline } from "../components/EventTimeline";
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
  const [showFullPrompt, setShowFullPrompt] = useState(false);

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

  async function refreshDetail() {
    if (!selectedRunId) return;
    const data = await api.getRun(selectedRunId);
    setDetail(data);
  }

  const manualPackage = detail?.manual_post_package as Record<string, unknown> | null;
  const video = detail?.video as Record<string, unknown> | null;
  const run = detail?.pipeline_run as Record<string, unknown> | null;
  const qualityChecks = detail?.quality_checks ?? [];
  const latestQualityCheck = qualityChecks[qualityChecks.length - 1] as Record<string, unknown> | undefined;
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

  const packageCaption = String(manualPackage?.caption ?? "");
  const packageHashtags = Array.isArray(manualPackage?.hashtags_json) ? manualPackage.hashtags_json.join(" ") : "";
  const instagramVariant = platformVariants.instagram as Record<string, unknown> | undefined;
  const tiktokVariant = platformVariants.tiktok as Record<string, unknown> | undefined;
  const youtubeVariant = platformVariants.youtube as Record<string, unknown> | undefined;
  const alternativeCaptions = Array.isArray(platformVariants.alternative_captions) ? platformVariants.alternative_captions : [];
  const alternativeHooks = Array.isArray(platformVariants.alternative_hooks) ? platformVariants.alternative_hooks : [];

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
            <div><span>Quality Score</span><strong>{String(latestQualityCheck?.score ?? "n/a")}</strong></div>
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
                  {selectedRunId ? <Link className="inline-link" to={`/ideas?run=${selectedRunId}`}>Back To Ideas</Link> : null}
                </div>
              </div>
              <div className="key-grid">
                <div><span>Status</span><strong>{formatVideoStatus(String(video.status))}</strong></div>
                <div><span>Provider</span><strong>{formatProvider(String(video.provider))}</strong></div>
                <div><span>Duration</span><strong>{String(video.duration_seconds)}s</strong></div>
                <div><span>Run Status</span><strong>{formatRunStatus(String(run?.status ?? ""))}</strong></div>
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
                <h3>Generated Video</h3>
                <div className="button-row">
                  <CopyButton text={String(videoAsset.public_url)} label="video URL" />
                </div>
              </div>
              <video
                className="video-player large"
                  controls
                  preload="metadata"
                  poster={thumbnailAsset ? String(thumbnailAsset.public_url) : undefined}
                  src={String(videoAsset.public_url)}
                >
                  Your browser does not support the video preview.
                </video>
              </div>
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
              <h3>Quality Check</h3>
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
