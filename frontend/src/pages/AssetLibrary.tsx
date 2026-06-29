import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { api, AssetLibraryDetail, AssetLibraryItem } from "../api/client";

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

const PROVIDERS = ["all", "mock", "runway"];
const STATUSES = ["all", "approved", "rejected", "needs_review"];
const STYLES = ["all", "clean_3d_cartoon", "neon_club_metaphor", "whiteboard_character", "bug_monster", "office_comedy"];
const PLATFORMS = ["all", "instagram", "tiktok", "youtube"];

export function AssetLibraryPage() {
  const [items, setItems] = useState<AssetLibraryItem[]>([]);
  const [selectedRunId, setSelectedRunId] = useState("");
  const [detail, setDetail] = useState<AssetLibraryDetail | null>(null);
  const [provider, setProvider] = useState("all");
  const [status, setStatus] = useState("all");
  const [stylePreset, setStylePreset] = useState("all");
  const [platform, setPlatform] = useState("all");
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");

  async function loadItems() {
    const params: Record<string, string> = {};
    if (provider !== "all") params.provider = provider;
    if (status !== "all") params.status = status;
    if (stylePreset !== "all") params.style_preset = stylePreset;
    if (platform !== "all") params.platform = platform;
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

  useEffect(() => {
    loadItems().catch((requestError: Error) => setError(requestError.message));
  }, [provider, status, stylePreset, platform]);

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      loadItems().catch((requestError: Error) => setError(requestError.message));
    }, 250);
    return () => window.clearTimeout(timeout);
  }, [query]);

  useEffect(() => {
    if (!selectedRunId) return;
    api.getAssetLibraryItem(selectedRunId).then(setDetail).catch((requestError: Error) => setError(requestError.message));
  }, [selectedRunId]);

  const selectedItem = useMemo(() => items.find((item) => item.run_id === selectedRunId) ?? null, [items, selectedRunId]);
  const manualPackage = detail?.manual_post_package as Record<string, unknown> | null;
  const platformVariants = (manualPackage?.platform_variants_json as Record<string, unknown> | undefined) ?? {};
  const instagramVariant = platformVariants.instagram as Record<string, unknown> | undefined;
  const tiktokVariant = platformVariants.tiktok as Record<string, unknown> | undefined;
  const youtubeVariant = platformVariants.youtube as Record<string, unknown> | undefined;
  const alternativeCaptions = Array.isArray(platformVariants.alternative_captions) ? platformVariants.alternative_captions : [];
  const alternativeHooks = Array.isArray(platformVariants.alternative_hooks) ? platformVariants.alternative_hooks : [];
  const qualityCheck = detail?.quality_check as Record<string, unknown> | null;
  const qualityEntries =
    qualityCheck?.checks_json && typeof qualityCheck.checks_json === "object"
      ? Object.entries(qualityCheck.checks_json as Record<string, unknown>)
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
        </div>
        {error ? <p className="error">{error}</p> : null}
        <div className="asset-grid">
          {items.map((item) => (
            <button
              key={item.run_id}
              className={`run-card ${selectedRunId === item.run_id ? "active" : ""}`}
              onClick={() => setSelectedRunId(item.run_id)}
            >
              {item.thumbnail_url ? <img className="thumb-preview" src={item.thumbnail_url} alt={item.topic} /> : null}
              <div className="content-meta">
                <strong>{item.topic}</strong>
                <span>{formatCreatedAt(item.created_at)}</span>
              </div>
              <div className="run-card-badges">
                <span className="status-pill">{item.style_preset}</span>
                <span className="status-pill muted">{item.provider}</span>
                {item.target_platform ? <span className="status-pill muted">{item.target_platform}</span> : null}
              </div>
              <span>run: {item.run_status}</span>
              <span>video: {item.video_status}</span>
              <span>quality: {item.quality_score ?? "n/a"}</span>
            </button>
          ))}
        </div>
      </section>

      <section className="panel">
        {selectedItem && detail ? (
          <div className="stack">
            <div className="panel-header">
              <h2>{selectedItem.topic}</h2>
              <Link className="inline-link" to={`/review?run=${selectedItem.run_id}`}>Open Video Review</Link>
            </div>
            <video
              className="video-player large"
              controls
              preload="metadata"
              poster={detail.thumbnail_asset ? String(detail.thumbnail_asset.public_url) : undefined}
              src={String(detail.video_asset.public_url)}
            >
              Your browser does not support the video preview.
            </video>
            <div className="copy-block">
              <div className="content-meta">
                <strong>Video URL</strong>
                <CopyButton text={String(detail.video_asset.public_url)} label="video URL" />
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
              <div><span>Provider</span><strong>{String(detail.video.provider)}</strong></div>
              <div><span>Quality Score</span><strong>{String(detail.video.quality_score ?? "n/a")}</strong></div>
              <div><span>Run Status</span><strong>{String(detail.pipeline_run.status)}</strong></div>
              <div><span>Video Status</span><strong>{String(detail.video.status)}</strong></div>
            </div>
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
                <div className="quality-list">
                  {qualityEntries.map(([key, value]) => (
                    <div key={key} className={`quality-item ${Boolean(value) ? "pass" : "fail"}`}>
                      <strong>{key.split("_").join(" ")}</strong>
                      <span>{String(value)}</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
            <div className="key-grid">
              <div><span>Linked Pipeline Run</span><strong>{String(detail.pipeline_run.id)}</strong></div>
              <div><span>Linked Idea Queue Item</span><strong>{String(detail.idea_queue_item?.id ?? "none")}</strong></div>
              <div><span>Target Platform</span><strong>{String(detail.idea_queue_item?.target_platform ?? "n/a")}</strong></div>
            </div>
          </div>
        ) : (
          <p className="subtle">Select a generated asset to inspect its full archive detail.</p>
        )}
      </section>
    </div>
  );
}
