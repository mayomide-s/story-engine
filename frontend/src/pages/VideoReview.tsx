import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api, PipelineRunDetail, PipelineRunSummary } from "../api/client";
import { EventTimeline } from "../components/EventTimeline";

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
  const qualityEntries = latestQualityCheck?.checks_json && typeof latestQualityCheck.checks_json === "object"
    ? Object.entries(latestQualityCheck.checks_json as Record<string, unknown>)
    : [];
  const canRecheck = Boolean(
    selectedRunId &&
    videoAsset &&
    video &&
    (String(run?.status ?? "") === "needs_review" || String(video.status ?? "") === "rejected"),
  );

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

  return (
    <div className="page grid review-grid">
      <section className="panel">
        <div className="panel-header">
          <h2>Video Review</h2>
          <select value={selectedRunId} onChange={(event) => setSelectedRunId(event.target.value)}>
            <option value="">Select a run</option>
            {runs.map((run) => (
              <option key={run.id} value={run.id}>
                {run.topic}
              </option>
            ))}
          </select>
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
            </div>
            <div className="panel inset">
              <h3>Generated Assets</h3>
              <div className="stack">
                {videoAsset ? (
                  <div className="content-card">
                    <div className="content-meta">
                      <strong>Video MP4</strong>
                      <span>{String(videoAsset.public_url)}</span>
                    </div>
                    <video
                      className="video-player"
                      controls
                      preload="metadata"
                      poster={thumbnailAsset ? String(thumbnailAsset.public_url) : undefined}
                      src={String(videoAsset.public_url)}
                    >
                      Your browser does not support the video preview.
                    </video>
                    <p><strong>Storage Key:</strong> {String(videoAsset.storage_key)}</p>
                    <p><strong>Mime Type:</strong> {String(videoAsset.mime_type)}</p>
                    <p><strong>Dimensions:</strong> {String(videoAsset.width)} x {String(videoAsset.height)}</p>
                  </div>
                ) : null}
                {thumbnailAsset ? (
                  <div className="content-card">
                    <div className="content-meta">
                      <strong>Thumbnail</strong>
                      <span>{String(thumbnailAsset.public_url)}</span>
                    </div>
                    <p><strong>Storage Key:</strong> {String(thumbnailAsset.storage_key)}</p>
                    <p><strong>Mime Type:</strong> {String(thumbnailAsset.mime_type)}</p>
                  </div>
                ) : null}
              </div>
            </div>
            <div className="panel inset">
              <h3>Quality Check Result</h3>
              {latestQualityCheck ? (
                <div className="stack">
                  <div className="key-grid">
                    <div><span>Passed</span><strong>{String(latestQualityCheck.passed)}</strong></div>
                    <div><span>Score</span><strong>{String(latestQualityCheck.score)}</strong></div>
                  </div>
                  <p>{String(latestQualityCheck.llm_critique)}</p>
                  <div className="stack compact">
                    {qualityEntries.map(([key, value]) => (
                      <div key={key} className="content-card">
                        <div className="content-meta">
                          <strong>{key}</strong>
                          <span>{String(value)}</span>
                        </div>
                      </div>
                    ))}
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
                  <p><strong>Caption:</strong> {String(manualPackage.caption)}</p>
                  <p><strong>Hashtags:</strong> {Array.isArray(manualPackage.hashtags_json) ? manualPackage.hashtags_json.join(" ") : ""}</p>
                  <p><strong>Target Platforms:</strong> {Array.isArray(manualPackage.target_platforms_json) ? manualPackage.target_platforms_json.join(", ") : ""}</p>
                  <div className="stack compact">
                    {Object.entries(platformVariants).map(([platform, variant]) => {
                      const typedVariant = variant as Record<string, unknown>;
                      return (
                        <div key={platform} className="content-card">
                          <div className="content-meta">
                            <strong>{platform}</strong>
                          </div>
                          {"title" in typedVariant ? <p><strong>Title:</strong> {String(typedVariant.title)}</p> : null}
                          {"caption" in typedVariant ? <p><strong>Caption:</strong> {String(typedVariant.caption)}</p> : null}
                          {"description" in typedVariant ? <p><strong>Description:</strong> {String(typedVariant.description)}</p> : null}
                          <p><strong>Hashtags:</strong> {Array.isArray(typedVariant.hashtags) ? typedVariant.hashtags.join(" ") : ""}</p>
                        </div>
                      );
                    })}
                  </div>
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
