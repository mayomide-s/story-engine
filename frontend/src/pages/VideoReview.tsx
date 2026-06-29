import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api, PipelineRunDetail, PipelineRunSummary } from "../api/client";
import { EventTimeline } from "../components/EventTimeline";

const videoProvider = import.meta.env.VITE_VIDEO_PROVIDER ?? "mock";
const storageProvider = import.meta.env.VITE_STORAGE_PROVIDER ?? "local";

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

  useEffect(() => {
    const requestedRunId = searchParams.get("run");
    api.listRuns().then((data) => {
      setRuns(data);
      if (requestedRunId && data.some((run) => run.id === requestedRunId)) {
        setSelectedRunId(requestedRunId);
      } else if (data[0]) {
        setSelectedRunId(data[0].id);
      }
    });
  }, [searchParams]);

  useEffect(() => {
    if (selectedRunId) {
      api.getRun(selectedRunId).then(setDetail).catch((requestError: Error) => setError(requestError.message));
    }
  }, [selectedRunId]);

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
  const qualityChecklist = Object.entries(rawQualityChecks).filter(([key]) => !key.endsWith("_seconds"));
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
  const badgeLabel = `${videoProvider}/${storageProvider.toUpperCase()}`;

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

  return (
    <div className="page grid review-grid">
      <section className="panel">
        <div className="panel-header">
          <h2>Video Review</h2>
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
                <div><span>Status</span><strong>{String(video.status)}</strong></div>
                <div><span>Provider</span><strong>{String(video.provider)}</strong></div>
                <div><span>Duration</span><strong>{String(video.duration_seconds)}s</strong></div>
                <div><span>Requested</span><strong>{String(video.requested_duration_seconds ?? "n/a")}s</strong></div>
                <div><span>Run Status</span><strong>{String(run?.status ?? "")}</strong></div>
              </div>
              <p className="subtle">{String(video.prompt_text)}</p>
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
                  <span className="subtle">{String(videoAsset.public_url)}</span>
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

            <div className="panel inset">
              <h3>Generated Assets</h3>
              <div className="asset-grid">
                {videoAsset ? (
                  <div className="content-card">
                    <div className="content-meta">
                      <strong>Video MP4</strong>
                      <span>{String(videoAsset.mime_type)}</span>
                    </div>
                    <p><strong>Storage Key:</strong> {String(videoAsset.storage_key)}</p>
                    <p><strong>Dimensions:</strong> {String(videoAsset.width)} x {String(videoAsset.height)}</p>
                    <p><strong>Duration:</strong> {String(videoAsset.duration_seconds)}s</p>
                  </div>
                ) : null}
                {thumbnailAsset ? (
                  <div className="content-card">
                    <div className="content-meta">
                      <strong>Thumbnail</strong>
                      <span>{String(thumbnailAsset.mime_type)}</span>
                    </div>
                    <p><strong>Storage Key:</strong> {String(thumbnailAsset.storage_key)}</p>
                    <p><strong>URL:</strong> {String(thumbnailAsset.public_url)}</p>
                  </div>
                ) : null}
              </div>
            </div>

            <div className="panel inset">
              <h3>Quality Check</h3>
              {latestQualityCheck ? (
                <div className="stack">
                  <div className="key-grid">
                    <div><span>Result</span><strong>{latestQualityCheck.passed ? "Pass" : "Fail"}</strong></div>
                    <div><span>Score</span><strong>{String(latestQualityCheck.score)}</strong></div>
                    <div><span>Requested</span><strong>{String(durationInfo.requested ?? "n/a")}s</strong></div>
                    <div><span>Actual</span><strong>{String(durationInfo.actual ?? "n/a")}s</strong></div>
                  </div>
                  <p>{String(latestQualityCheck.llm_critique)}</p>
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
                </div>
              ) : (
                <p className="subtle">No manual posting package available yet.</p>
              )}
            </div>
          </div>
        ) : (
          <p className="subtle">Resume a run from the dashboard to generate the video and review package.</p>
        )}
      </section>
      <EventTimeline events={detail?.pipeline_events ?? []} />
    </div>
  );
}
