import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { api, AssetLibraryDetail, AssetLibraryItem } from "../api/client";
import { PerformanceLearningsSummary } from "../components/PerformanceLearningsSummary";
import { PerformanceWinnerSummary } from "../components/PerformanceWinnerSummary";
import { YouTubePublicationPanel } from "../components/YouTubePublicationPanel";
import { ExportPackPanel } from "../components/ExportPackPanel";
import { normalizeQualityChecklist } from "../qualityChecklist";
import { formatProvider, formatRunStatus, formatVideoStatus } from "../utils/display";

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

function formatCreatedAt(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(date);
}

function ThumbnailPreview({ src, topic }: { src?: string | null; topic: string }) {
  const [failed, setFailed] = useState(false);

  if (!src || failed) {
    return (
      <div className="thumb-preview thumb-fallback" aria-label={`${topic} thumbnail unavailable`}>
        <strong>{topic.slice(0, 1).toUpperCase()}</strong>
      </div>
    );
  }

  return <img className="thumb-preview" src={src} alt={topic} onError={() => setFailed(true)} />;
}

const PROVIDERS = ["all", "mock", "runway"];
const STATUSES = ["all", "approved", "rejected", "needs_review"];
const STYLES = ["all", "clean_3d_cartoon", "neon_club_metaphor", "whiteboard_character", "bug_monster", "office_comedy"];
const PLATFORMS = ["all", "instagram", "tiktok", "youtube"];
const POSTING_STATUSES = ["all", "not_posted", "posted_tiktok", "posted_instagram", "posted_youtube", "posted_multiple"];

export function AssetLibraryPage() {
  const [items, setItems] = useState<AssetLibraryItem[]>([]);
  const [selectedRunId, setSelectedRunId] = useState("");
  const [detail, setDetail] = useState<AssetLibraryDetail | null>(null);
  const [provider, setProvider] = useState("all");
  const [status, setStatus] = useState("all");
  const [stylePreset, setStylePreset] = useState("all");
  const [platform, setPlatform] = useState("all");
  const [manualPostingStatus, setManualPostingStatus] = useState("all");
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");

  async function loadItems() {
    const params: Record<string, string> = {};
    if (provider !== "all") params.provider = provider;
    if (status !== "all") params.status = status;
    if (stylePreset !== "all") params.style_preset = stylePreset;
    if (platform !== "all") params.platform = platform;
    if (manualPostingStatus !== "all") params.manual_posting_status = manualPostingStatus;
    if (query.trim()) params.q = query.trim();
    const data = await api.listAssetLibrary(params);
    setItems(data);
    if (data[0] && !data.some((item) => item.run_id === selectedRunId)) {
      setSelectedRunId(data[0].run_id);
    }
    if (!data.length) {
      setSelectedRunId("");
      setDetail(null);
    }
  }

  async function loadDetail(runId: string) {
    const data = await api.getAssetLibraryItem(runId);
    setDetail(data);
  }

  useEffect(() => {
    loadItems().catch((requestError: Error) => setError(requestError.message));
  }, [provider, status, stylePreset, platform, manualPostingStatus]);

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      loadItems().catch((requestError: Error) => setError(requestError.message));
    }, 250);
    return () => window.clearTimeout(timeout);
  }, [query]);

  useEffect(() => {
    if (!selectedRunId) return;
    loadDetail(selectedRunId).catch((requestError: Error) => setError(requestError.message));
  }, [selectedRunId]);

  const selectedItem = useMemo(() => items.find((item) => item.run_id === selectedRunId) ?? null, [items, selectedRunId]);
  const manualPackage = detail?.manual_post_package as Record<string, unknown> | null;
  const finalSelection = detail?.final_asset_selection ?? null;
  const winnerSelection = detail?.winner_selection ?? null;
  const learningsSummary = detail?.performance_learnings_summary ?? null;
  const platformVariants = (manualPackage?.platform_variants_json as Record<string, unknown> | undefined) ?? {};
  const instagramVariant = platformVariants.instagram as Record<string, unknown> | undefined;
  const tiktokVariant = platformVariants.tiktok as Record<string, unknown> | undefined;
  const youtubeVariant = platformVariants.youtube as Record<string, unknown> | undefined;
  const alternativeCaptions = Array.isArray(platformVariants.alternative_captions) ? platformVariants.alternative_captions : [];
  const alternativeHooks = Array.isArray(platformVariants.alternative_hooks) ? platformVariants.alternative_hooks : [];
  const qualityCheck = detail?.quality_check as Record<string, unknown> | null;
  const qualityEntries =
    qualityCheck?.checks_json && typeof qualityCheck.checks_json === "object"
      ? normalizeQualityChecklist(
        qualityCheck.checks_json as Record<string, unknown>,
        typeof detail?.video?.provider === "string" ? detail.video.provider : null,
      )
      : [];

  return (
    <div className="page grid review-grid">
      <section className="panel">
        <div className="panel-header">
          <h2>Asset Library</h2>
          <span>{items.length} generated videos</span>
        </div>
        <div className="form-grid compact">
          <label className="field">
            <span>Search</span>
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Topic, caption, prompt" />
          </label>
          <label className="field">
            <span>Provider</span>
            <select value={provider} onChange={(event) => setProvider(event.target.value)}>
              {PROVIDERS.map((itemProvider) => (
                <option key={itemProvider} value={itemProvider}>{itemProvider}</option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Status</span>
            <select value={status} onChange={(event) => setStatus(event.target.value)}>
              {STATUSES.map((itemStatus) => (
                <option key={itemStatus} value={itemStatus}>{itemStatus}</option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Style</span>
            <select value={stylePreset} onChange={(event) => setStylePreset(event.target.value)}>
              {STYLES.map((itemStyle) => (
                <option key={itemStyle} value={itemStyle}>{itemStyle}</option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Platform</span>
            <select value={platform} onChange={(event) => setPlatform(event.target.value)}>
              {PLATFORMS.map((itemPlatform) => (
                <option key={itemPlatform} value={itemPlatform}>{itemPlatform}</option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Posting</span>
            <select value={manualPostingStatus} onChange={(event) => setManualPostingStatus(event.target.value)}>
              {POSTING_STATUSES.map((itemStatus) => (
                <option key={itemStatus} value={itemStatus}>{itemStatus}</option>
              ))}
            </select>
          </label>
        </div>
        {error ? <p className="error">{error}</p> : null}
        <div className="asset-grid scroll-panel asset-library-scroll">
          {items.map((item) => (
            <button
              key={item.run_id}
              className={`run-card ${selectedRunId === item.run_id ? "active" : ""}`}
              onClick={() => setSelectedRunId(item.run_id)}
            >
              <ThumbnailPreview src={item.thumbnail_url} topic={item.topic} />
              <div className="content-meta">
                <strong>{item.topic}</strong>
                <span>{formatCreatedAt(item.created_at)}</span>
              </div>
              <div className="run-card-badges">
                <span className="status-pill">{item.style_preset}</span>
                <span className="status-pill muted">{formatProvider(item.provider)}</span>
                {item.target_platform ? <span className="status-pill muted">{item.target_platform}</span> : null}
                {item.manual_posting_status ? <span className="status-pill muted">{item.manual_posting_status}</span> : null}
              </div>
              <span>Run: {formatRunStatus(item.run_status)}</span>
              <span>Video: {formatVideoStatus(item.video_status)}</span>
              <span>Quality: {item.quality_score ?? "n/a"}</span>
            </button>
          ))}
        </div>
      </section>

      <section className="panel">
        {selectedItem && detail ? (
          <div className="stack scroll-panel asset-detail-scroll">
            <div className="panel-header">
              <h2>{selectedItem.topic}</h2>
              <div className="button-row">
                <Link className="inline-link" to={`/review?run=${selectedItem.run_id}`}>Open Video Review</Link>
                {String(detail.pipeline_run.status ?? "") === "completed" && detail.manual_post_package ? (
                  <Link className="inline-link" to={`/performance/${selectedItem.run_id}`}>Open Performance</Link>
                ) : null}
              </div>
            </div>
            <video
              className="video-player large"
              controls
              preload="metadata"
              poster={detail.thumbnail_asset ? String(detail.thumbnail_asset.public_url) : undefined}
              src={String(detail.final_video_asset.public_url)}
            >
              Your browser does not support the video preview.
            </video>
            <div className="copy-block">
              <div className="content-meta">
                <strong>Final Video URL</strong>
                <CopyButton text={String(detail.final_video_asset.public_url)} label="video URL" />
              </div>
              <pre>{String(detail.final_video_asset.public_url)}</pre>
            </div>
            <div className="copy-block">
              <div className="content-meta">
                <strong>Original Video URL</strong>
                <CopyButton text={String(detail.video_asset.public_url)} label="original video URL" />
              </div>
              <pre>{String(detail.video_asset.public_url)}</pre>
            </div>
            {detail.thumbnail_asset ? (
              <div className="copy-block">
                <div className="content-meta">
                  <strong>Thumbnail URL</strong>
                  <CopyButton text={String(detail.thumbnail_asset.public_url)} label="thumbnail URL" />
                </div>
                <pre>{String(detail.thumbnail_asset.public_url)}</pre>
              </div>
            ) : null}
            <div className="key-grid">
              <div><span>Original Topic</span><strong>{String(detail.pipeline_run.topic)}</strong></div>
              <div><span>Style Preset</span><strong>{String(detail.pipeline_run.style_preset)}</strong></div>
              <div><span>Provider</span><strong>{formatProvider(String(detail.video.provider))}</strong></div>
              <div><span>Quality Score</span><strong>{String(detail.video.quality_score ?? "n/a")}</strong></div>
              <div><span>Run Status</span><strong>{formatRunStatus(String(detail.pipeline_run.status))}</strong></div>
              <div><span>Video Status</span><strong>{formatVideoStatus(String(detail.video.status))}</strong></div>
              <div><span>Manual Posting</span><strong>{String(detail.manual_post_package?.manual_posting_status ?? "not_posted")}</strong></div>
              <div><span>Final Video</span><strong>{finalSelection?.source === "narration_render" ? "Narrated" : "Original"}</strong></div>
            </div>
            <div className="button-row">
              <CopyButton text={String(detail.final_video_asset.public_url)} label="video URL" />
              <CopyButton text={String(detail.video_asset.public_url)} label="original video URL" />
              {detail.thumbnail_asset ? <CopyButton text={String(detail.thumbnail_asset.public_url)} label="thumbnail URL" /> : null}
            </div>
            {finalSelection?.source === "narration_render" ? (
              <div className="notice-card">
                <strong>Selected final video</strong>
                <p>
                  Narrated render {String(finalSelection.narration_render_id ?? "")} is the current final asset.
                  {finalSelection.ai_voice_disclosure ? ` ${String(finalSelection.ai_voice_disclosure)}` : ""}
                </p>
              </div>
            ) : (
              <div className="notice-card">
                <strong>Selected final video</strong>
                <p>The original silent source video is currently selected as the final asset.</p>
              </div>
            )}
            <PerformanceWinnerSummary
              winnerSelection={winnerSelection}
              performanceHref={selectedItem ? `/performance/${selectedItem.run_id}` : undefined}
              heading="Manual winner"
              compact
            />
            <PerformanceLearningsSummary
              summary={learningsSummary}
              performanceHref={selectedItem ? `/performance/${selectedItem.run_id}` : undefined}
              compact
            />
            <YouTubePublicationPanel
              runId={selectedItem.run_id}
              runStatus={String(detail.pipeline_run.status ?? "")}
              finalAssetSelection={finalSelection}
              manualPostPackage={manualPackage}
            />
            {detail.idea ? (
              <div className="copy-block">
                <div className="content-meta">
                  <strong>Idea Title / Hook</strong>
                </div>
                <pre>{`Title: ${String(detail.idea.title)}\n\nHook: ${String(detail.idea.hook)}`}</pre>
              </div>
            ) : null}
            <div className="copy-block">
              <div className="content-meta">
                <strong>Final Prompt</strong>
                <CopyButton text={String(detail.video.prompt_text)} label="prompt" />
              </div>
              <pre>{String(detail.video.prompt_text)}</pre>
            </div>
            <details className="technical-disclosure">
              <summary>Show technical details</summary>
              <div className="stack compact technical-stack">
                <div className="copy-block">
                  <div className="content-meta">
                    <strong>Video URL</strong>
                  </div>
                  <pre>{String(detail.final_video_asset.public_url)}</pre>
                </div>
                {detail.thumbnail_asset ? (
                  <div className="copy-block">
                    <div className="content-meta">
                      <strong>Thumbnail URL</strong>
                    </div>
                    <pre>{String(detail.thumbnail_asset.public_url)}</pre>
                  </div>
                ) : null}
                <div className="copy-block">
                  <div className="content-meta">
                    <strong>Storage Keys</strong>
                  </div>
                  <pre>{`Final video: ${String(detail.final_video_asset.storage_key)}\nOriginal video: ${String(detail.video_asset.storage_key)}${detail.thumbnail_asset ? `\nThumbnail: ${String(detail.thumbnail_asset.storage_key)}` : ""}`}</pre>
                </div>
              </div>
            </details>
            {manualPackage ? (
              <div className="stack">
                <div className="copy-block">
                  <div className="content-meta">
                    <strong>Caption</strong>
                    <CopyButton text={String(manualPackage.caption ?? "")} label="caption" />
                  </div>
                  <pre>{String(manualPackage.caption ?? "")}</pre>
                </div>
                <div className="copy-block">
                  <div className="content-meta">
                    <strong>Hashtags</strong>
                    <CopyButton text={Array.isArray(manualPackage.hashtags_json) ? manualPackage.hashtags_json.join(" ") : ""} label="hashtags" />
                  </div>
                  <pre>{Array.isArray(manualPackage.hashtags_json) ? manualPackage.hashtags_json.join(" ") : ""}</pre>
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
                      <CopyButton text={`Title: ${String(youtubeVariant.title ?? "")}\n\nDescription:\n${String(youtubeVariant.description ?? "")}`} label="YouTube variant" />
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
            ) : null}
            {qualityCheck ? (
              <div className="panel inset">
                <h3>Quality Checklist</h3>
                <details className="technical-disclosure">
                  <summary>Show technical quality details</summary>
                  <div className="quality-list technical-stack">
                    {qualityEntries.map(([key, value]) => (
                      <div key={key} className={`quality-item ${Boolean(value) ? "pass" : "fail"}`}>
                        <strong>{key.split("_").join(" ")}</strong>
                        <span>{String(value)}</span>
                      </div>
                    ))}
                  </div>
                </details>
              </div>
            ) : null}
            <div className="key-grid">
              <div><span>Linked Pipeline Run</span><strong>{String(detail.pipeline_run.id)}</strong></div>
              <div><span>Linked Idea Queue Item</span><strong>{String(detail.idea_queue_item?.id ?? "none")}</strong></div>
              <div><span>Target Platform</span><strong>{String(detail.idea_queue_item?.target_platform ?? "n/a")}</strong></div>
            </div>
            <ExportPackPanel
              runId={selectedItem.run_id}
              onUpdated={async () => {
                await loadItems();
                await loadDetail(selectedItem.run_id);
              }}
            />
          </div>
        ) : (
          <p className="subtle">Select a generated asset to inspect its full archive detail.</p>
        )}
      </section>
    </div>
  );
}
