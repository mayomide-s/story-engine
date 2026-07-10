import { useEffect, useMemo, useState } from "react";

import { api, AssetExportPack } from "../api/client";

const POSTING_STATUSES = ["not_posted", "posted_tiktok", "posted_instagram", "posted_youtube", "posted_multiple"];

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

function downloadExportPack(pack: AssetExportPack) {
  const blob = new Blob([JSON.stringify(pack, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${pack.topic.toLowerCase().replace(/[^a-z0-9]+/g, "-")}-export-pack.json`;
  link.click();
  URL.revokeObjectURL(url);
}

export function ExportPackPanel({
  runId,
  onUpdated,
}: {
  runId: string;
  onUpdated?: () => Promise<void> | void;
}) {
  const [pack, setPack] = useState<AssetExportPack | null>(null);
  const [error, setError] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [status, setStatus] = useState("not_posted");
  const [tiktokUrl, setTiktokUrl] = useState("");
  const [instagramUrl, setInstagramUrl] = useState("");
  const [youtubeUrl, setYoutubeUrl] = useState("");

  useEffect(() => {
    api.getAssetExportPack(runId)
      .then((data) => {
        setPack(data);
        setStatus(data.manual_posting_status);
        setTiktokUrl(data.manual_post_urls.tiktok ?? "");
        setInstagramUrl(data.manual_post_urls.instagram ?? "");
        setYoutubeUrl(data.manual_post_urls.youtube ?? "");
        setError("");
      })
      .catch((requestError: Error) => setError(requestError.message));
  }, [runId]);

  const qualityEntries = useMemo(
    () => (pack ? Object.entries(pack.quality_checklist).filter(([key]) => !key.endsWith("_seconds")) : []),
    [pack],
  );

  async function handleSave() {
    setIsSaving(true);
    setError("");
    try {
      const updated = await api.updateAssetManualPosting(runId, {
        manual_posting_status: status,
        tiktok_post_url: tiktokUrl || null,
        instagram_post_url: instagramUrl || null,
        youtube_post_url: youtubeUrl || null,
      });
      setPack(updated);
      setStatus(updated.manual_posting_status);
      setTiktokUrl(updated.manual_post_urls.tiktok ?? "");
      setInstagramUrl(updated.manual_post_urls.instagram ?? "");
      setYoutubeUrl(updated.manual_post_urls.youtube ?? "");
      await onUpdated?.();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to update manual posting info.");
    } finally {
      setIsSaving(false);
    }
  }

  if (!pack) {
    return <div className="panel inset"><p className="subtle">{error || "Loading export pack..."}</p></div>;
  }

  return (
    <div className="panel inset stack">
      <div className="panel-header">
        <h3>Export Pack</h3>
        <div className="panel-actions">
          <span className="status-pill muted">{pack.manual_posting_status}</span>
          <button type="button" onClick={() => downloadExportPack(pack)}>Download Export Pack</button>
        </div>
      </div>
      {error ? <p className="error-text">{error}</p> : null}
      <div className="key-grid">
        <div><span>Created</span><strong>{formatCreatedAt(pack.created_at)}</strong></div>
        <div><span>Topic</span><strong>{pack.topic}</strong></div>
        <div><span>Style Preset</span><strong>{pack.style_preset}</strong></div>
        <div><span>Quality Score</span><strong>{String(pack.quality_score ?? "n/a")}</strong></div>
        <div><span>Final Video</span><strong>{pack.final_asset_source === "narration_render" ? "Narrated" : "Original"}</strong></div>
        <div><span>Selection Revision</span><strong>{String(pack.final_asset_selection_revision ?? 1)}</strong></div>
      </div>
      <div className="copy-block">
        <div className="content-meta">
          <strong>Final Video URL</strong>
          <CopyButton text={pack.video_public_url} label="final video URL" />
        </div>
        <pre>{pack.video_public_url}</pre>
      </div>
      {pack.original_video_public_url ? (
        <div className="copy-block">
          <div className="content-meta">
            <strong>Original Video URL</strong>
            <CopyButton text={pack.original_video_public_url} label="original video URL" />
          </div>
          <pre>{pack.original_video_public_url}</pre>
        </div>
      ) : null}
      {pack.final_asset_source === "narration_render" ? (
        <div className="copy-block">
          <div className="content-meta">
            <strong>Narration Selection</strong>
          </div>
          <pre>{[
            `Narration render ID: ${pack.final_narration_render_id ?? "n/a"}`,
            `AI voice disclosure: ${pack.ai_voice_disclosure ?? "n/a"}`,
            `Voice is AI generated: ${pack.voice_is_ai_generated ? "Yes" : "No"}`,
            "",
            "Transcript:",
            pack.narration_transcript ?? "",
          ].join("\n")}</pre>
        </div>
      ) : null}
      {pack.final_asset_source === "narration_render" && pack.caption_cues.length > 0 ? (
        <div className="copy-block">
          <div className="content-meta">
            <strong>Caption Cues</strong>
          </div>
          <pre>{JSON.stringify(pack.caption_cues, null, 2)}</pre>
        </div>
      ) : null}
      <div className="copy-block">
        <div className="content-meta">
          <strong>Final Prompt Used</strong>
          <CopyButton text={pack.final_prompt_used} label="prompt" />
        </div>
        <pre>{pack.final_prompt_used}</pre>
      </div>
      <div className="copy-block">
        <div className="content-meta">
          <strong>Quality Checklist</strong>
        </div>
        <div className="quality-list">
          {qualityEntries.map(([key, value]) => (
            <div key={key} className={`quality-item ${Boolean(value) ? "pass" : "fail"}`}>
              <strong>{key.split("_").join(" ")}</strong>
              <span>{String(value)}</span>
            </div>
          ))}
        </div>
      </div>
      <div className="form-grid">
        <label className="field">
          <span>Manual Posting Status</span>
          <select value={status} onChange={(event) => setStatus(event.target.value)}>
            {POSTING_STATUSES.map((itemStatus) => (
              <option key={itemStatus} value={itemStatus}>{itemStatus}</option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>TikTok URL</span>
          <input value={tiktokUrl} onChange={(event) => setTiktokUrl(event.target.value)} placeholder="https://tiktok.com/..." />
        </label>
        <label className="field">
          <span>Instagram URL</span>
          <input value={instagramUrl} onChange={(event) => setInstagramUrl(event.target.value)} placeholder="https://instagram.com/reel/..." />
        </label>
        <label className="field">
          <span>YouTube URL</span>
          <input value={youtubeUrl} onChange={(event) => setYoutubeUrl(event.target.value)} placeholder="https://youtube.com/shorts/..." />
        </label>
      </div>
      <div className="button-row">
        <button type="button" onClick={handleSave} disabled={isSaving}>
          {isSaving ? "Saving..." : "Save Manual Posting"}
        </button>
      </div>
      <div className="platform-grid">
        <div className="copy-block">
          <div className="content-meta">
            <strong>TikTok</strong>
            <CopyButton text={pack.platform_sections.tiktok.full_post_text} label="TikTok post" />
          </div>
          <pre>{pack.platform_sections.tiktok.full_post_text}</pre>
          <p><strong>Manual URL:</strong> {pack.platform_sections.tiktok.manual_post_url ?? "Not saved yet"}</p>
          <ul className="steps-list">
            {pack.platform_sections.tiktok.checklist.map((step) => <li key={step}>{step}</li>)}
          </ul>
        </div>
        <div className="copy-block">
          <div className="content-meta">
            <strong>Instagram Reels</strong>
            <CopyButton text={pack.platform_sections.instagram_reels.full_post_text} label="Instagram post" />
          </div>
          <pre>{pack.platform_sections.instagram_reels.full_post_text}</pre>
          <p><strong>Manual URL:</strong> {pack.platform_sections.instagram_reels.manual_post_url ?? "Not saved yet"}</p>
          <ul className="steps-list">
            {pack.platform_sections.instagram_reels.checklist.map((step) => <li key={step}>{step}</li>)}
          </ul>
        </div>
        <div className="copy-block">
          <div className="content-meta">
            <strong>YouTube Shorts</strong>
            <CopyButton text={pack.platform_sections.youtube_shorts.full_post_text} label="YouTube post" />
          </div>
          <pre>{pack.platform_sections.youtube_shorts.full_post_text}</pre>
          <p><strong>Manual URL:</strong> {pack.platform_sections.youtube_shorts.manual_post_url ?? "Not saved yet"}</p>
          <ul className="steps-list">
            {pack.platform_sections.youtube_shorts.checklist.map((step) => <li key={step}>{step}</li>)}
          </ul>
        </div>
      </div>
      <div className="copy-block">
        <div className="content-meta">
          <strong>Alternative Captions</strong>
        </div>
        <pre>{pack.alternative_captions.map((caption, index) => `${index + 1}. ${caption}`).join("\n\n")}</pre>
      </div>
      <div className="copy-block">
        <div className="content-meta">
          <strong>Alternative Hooks</strong>
        </div>
        <pre>{pack.alternative_hooks.map((hook, index) => `${index + 1}. ${hook}`).join("\n\n")}</pre>
      </div>
    </div>
  );
}
