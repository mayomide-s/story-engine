import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { api, AssetLibraryItem } from "../api/client";
import { formatProvider, formatVideoStatus } from "../utils/display";

type PostedStatus = "not_posted" | "posted" | "reposted";
type ResultLabel = "untested" | "weak" | "okay" | "winner";
type PlatformKey = "tiktok" | "instagram_reels" | "youtube_shorts";

type ContentOpsTracking = {
  postedStatus: PostedStatus;
  platforms: PlatformKey[];
  postedDate: string;
  views24h: string;
  views72h: string;
  views7d: string;
  likes: string;
  comments: string;
  shares: string;
  saves: string;
  followsGained: string;
  hookNotes: string;
  resultLabel: ResultLabel;
};

const STORAGE_KEY = "story-engine-content-ops-tracking";

const POSTED_STATUS_OPTIONS: Array<{ value: PostedStatus; label: string }> = [
  { value: "not_posted", label: "Not posted" },
  { value: "posted", label: "Posted" },
  { value: "reposted", label: "Reposted" },
];

const RESULT_LABEL_OPTIONS: Array<{ value: ResultLabel; label: string }> = [
  { value: "untested", label: "Untested" },
  { value: "weak", label: "Weak" },
  { value: "okay", label: "Okay" },
  { value: "winner", label: "Winner" },
];

const PLATFORM_OPTIONS: Array<{ value: PlatformKey; label: string }> = [
  { value: "tiktok", label: "TikTok" },
  { value: "instagram_reels", label: "Instagram Reels" },
  { value: "youtube_shorts", label: "YouTube Shorts" },
];

function createDefaultTracking(item: AssetLibraryItem): ContentOpsTracking {
  return {
    postedStatus: "not_posted",
    platforms: inferInitialPlatforms(item),
    postedDate: "",
    views24h: "",
    views72h: "",
    views7d: "",
    likes: "",
    comments: "",
    shares: "",
    saves: "",
    followsGained: "",
    hookNotes: "",
    resultLabel: "untested",
  };
}

function inferInitialPlatforms(item: AssetLibraryItem): PlatformKey[] {
  if (item.target_platform === "tiktok") return ["tiktok"];
  if (item.target_platform === "instagram") return ["instagram_reels"];
  if (item.target_platform === "youtube") return ["youtube_shorts"];
  return [];
}

function loadStoredTracking() {
  if (typeof window === "undefined") {
    return {} as Record<string, ContentOpsTracking>;
  }
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) as Record<string, ContentOpsTracking> : {};
  } catch {
    return {} as Record<string, ContentOpsTracking>;
  }
}

function saveStoredTracking(value: Record<string, ContentOpsTracking>) {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
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

function formatPostedStatus(value: PostedStatus) {
  return POSTED_STATUS_OPTIONS.find((option) => option.value === value)?.label ?? "Not posted";
}

function formatResultLabel(value: ResultLabel) {
  return RESULT_LABEL_OPTIONS.find((option) => option.value === value)?.label ?? "Untested";
}

function formatPlatforms(platforms: PlatformKey[]) {
  if (!platforms.length) {
    return "No platforms set";
  }
  return PLATFORM_OPTIONS
    .filter((option) => platforms.includes(option.value))
    .map((option) => option.label)
    .join(", ");
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
    <button type="button" className="secondary" onClick={handleCopy} disabled={!text.trim()}>
      {copied ? `${label} copied` : `Copy ${label}`}
    </button>
  );
}

export function ContentOpsPage() {
  const [items, setItems] = useState<AssetLibraryItem[]>([]);
  const [selectedRunId, setSelectedRunId] = useState("");
  const [trackingByRunId, setTrackingByRunId] = useState<Record<string, ContentOpsTracking>>(() => loadStoredTracking());
  const [draft, setDraft] = useState<ContentOpsTracking | null>(null);
  const [postedStatusFilter, setPostedStatusFilter] = useState<"all" | PostedStatus>("all");
  const [platformFilter, setPlatformFilter] = useState<"all" | PlatformKey>("all");
  const [resultFilter, setResultFilter] = useState<"all" | ResultLabel>("all");
  const [error, setError] = useState("");

  async function loadItems() {
    const data = await api.listAssetLibrary();
    const completedItems = data.filter((item) => ["approved", "completed"].includes(item.video_status) || item.run_status === "completed");
    setItems(completedItems);
    if (!selectedRunId && completedItems[0]) {
      setSelectedRunId(completedItems[0].run_id);
    }
  }

  useEffect(() => {
    loadItems().catch((requestError: Error) => setError(requestError.message));
  }, []);

  useEffect(() => {
    saveStoredTracking(trackingByRunId);
  }, [trackingByRunId]);

  const mergedItems = useMemo(() => {
    return items.map((item) => ({
      item,
      tracking: trackingByRunId[item.run_id] ?? createDefaultTracking(item),
    }));
  }, [items, trackingByRunId]);

  const filteredItems = useMemo(() => {
    return mergedItems.filter(({ tracking }) => {
      if (postedStatusFilter !== "all" && tracking.postedStatus !== postedStatusFilter) return false;
      if (platformFilter !== "all" && !tracking.platforms.includes(platformFilter)) return false;
      if (resultFilter !== "all" && tracking.resultLabel !== resultFilter) return false;
      return true;
    });
  }, [mergedItems, platformFilter, postedStatusFilter, resultFilter]);

  const selectedEntry = useMemo(
    () => filteredItems.find((entry) => entry.item.run_id === selectedRunId) ?? mergedItems.find((entry) => entry.item.run_id === selectedRunId) ?? null,
    [filteredItems, mergedItems, selectedRunId],
  );

  useEffect(() => {
    if (!selectedEntry) {
      setDraft(null);
      return;
    }
    setDraft({ ...selectedEntry.tracking });
  }, [selectedEntry]);

  function updateDraft<K extends keyof ContentOpsTracking>(key: K, value: ContentOpsTracking[K]) {
    setDraft((current) => current ? { ...current, [key]: value } : current);
  }

  function toggleDraftPlatform(platform: PlatformKey) {
    setDraft((current) => {
      if (!current) return current;
      return {
        ...current,
        platforms: current.platforms.includes(platform)
          ? current.platforms.filter((item) => item !== platform)
          : [...current.platforms, platform],
      };
    });
  }

  function handleSaveDraft() {
    if (!selectedEntry || !draft) return;
    setTrackingByRunId((current) => ({
      ...current,
      [selectedEntry.item.run_id]: draft,
    }));
  }

  function handleMarkPosted() {
    if (!selectedEntry) return;
    const current = trackingByRunId[selectedEntry.item.run_id] ?? createDefaultTracking(selectedEntry.item);
    const next: ContentOpsTracking = {
      ...current,
      postedStatus: current.postedStatus === "posted" ? "reposted" : "posted",
      postedDate: current.postedDate || new Date().toISOString().slice(0, 10),
    };
    setTrackingByRunId((existing) => ({
      ...existing,
      [selectedEntry.item.run_id]: next,
    }));
    setDraft(next);
  }

  function handleMarkWinner() {
    if (!selectedEntry) return;
    const current = trackingByRunId[selectedEntry.item.run_id] ?? createDefaultTracking(selectedEntry.item);
    const next: ContentOpsTracking = {
      ...current,
      resultLabel: "winner",
    };
    setTrackingByRunId((existing) => ({
      ...existing,
      [selectedEntry.item.run_id]: next,
    }));
    setDraft(next);
  }

  return (
    <div className="page stack">
      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Content Ops</p>
            <h2>Track posting performance for completed videos.</h2>
          </div>
          <span className="status-pill muted">{filteredItems.length} tracked videos</span>
        </div>
        <div className="form-grid compact">
          <label className="field">
            <span>Posted Status</span>
            <select value={postedStatusFilter} onChange={(event) => setPostedStatusFilter(event.target.value as "all" | PostedStatus)}>
              <option value="all">All</option>
              {POSTED_STATUS_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Platform</span>
            <select value={platformFilter} onChange={(event) => setPlatformFilter(event.target.value as "all" | PlatformKey)}>
              <option value="all">All</option>
              {PLATFORM_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Result Label</span>
            <select value={resultFilter} onChange={(event) => setResultFilter(event.target.value as "all" | ResultLabel)}>
              <option value="all">All</option>
              {RESULT_LABEL_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </label>
        </div>
      </section>

      {error ? <p className="error">{error}</p> : null}

      <div className="review-grid">
        <section className="panel">
          <div className="panel-header">
            <h2>Completed Videos</h2>
            <span>{items.length} available</span>
          </div>
          <div className="content-ops-list scroll-panel">
            {filteredItems.map(({ item, tracking }) => (
              <button
                key={item.run_id}
                className={`run-card ${selectedRunId === item.run_id ? "active" : ""}`}
                onClick={() => setSelectedRunId(item.run_id)}
              >
                <div className="content-meta">
                  <strong>{item.topic}</strong>
                  <span>{formatCreatedAt(item.created_at)}</span>
                </div>
                <div className="run-card-badges">
                  <span className="status-pill">{formatProvider(item.provider)}</span>
                  <span className="status-pill muted">{formatVideoStatus(item.video_status)}</span>
                  <span className="status-pill muted">{formatResultLabel(tracking.resultLabel)}</span>
                </div>
                <span>Posted: {formatPostedStatus(tracking.postedStatus)}</span>
                <span>Platforms: {formatPlatforms(tracking.platforms)}</span>
                <span className="subtle">24h views: {tracking.views24h || "-"}</span>
              </button>
            ))}
            {!filteredItems.length ? <p className="subtle">No completed videos match the selected filters.</p> : null}
          </div>
        </section>

        <section className="panel">
          {selectedEntry && draft ? (
            <div className="stack scroll-panel content-ops-detail-scroll">
              <div className="panel-header">
                <h2>{selectedEntry.item.topic}</h2>
                <Link className="inline-link" to={`/review?run=${selectedEntry.item.run_id}`}>Open Review</Link>
              </div>

              <div className="key-grid">
                <div><span>Video Status</span><strong>{formatVideoStatus(selectedEntry.item.video_status)}</strong></div>
                <div><span>Provider</span><strong>{formatProvider(selectedEntry.item.provider)}</strong></div>
                <div><span>Posted Status</span><strong>{formatPostedStatus(draft.postedStatus)}</strong></div>
                <div><span>Result</span><strong>{formatResultLabel(draft.resultLabel)}</strong></div>
              </div>

              <div className="button-row">
                <CopyButton text={selectedEntry.item.caption ?? ""} label="caption" />
                <button type="button" className="secondary" onClick={handleMarkPosted}>Mark as posted</button>
                <button type="button" className="secondary" onClick={handleMarkWinner}>Mark as winner</button>
              </div>

              <div className="copy-block">
                <div className="content-meta">
                  <strong>Caption / Posting Copy</strong>
                </div>
                <pre>{selectedEntry.item.caption || "No caption found for this video yet."}</pre>
              </div>

              <div className="form-grid">
                <label className="field">
                  <span>Posted Status</span>
                  <select value={draft.postedStatus} onChange={(event) => updateDraft("postedStatus", event.target.value as PostedStatus)}>
                    {POSTED_STATUS_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>{option.label}</option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  <span>Posted Date</span>
                  <input type="date" value={draft.postedDate} onChange={(event) => updateDraft("postedDate", event.target.value)} />
                </label>
                <label className="field">
                  <span>24h Views</span>
                  <input value={draft.views24h} onChange={(event) => updateDraft("views24h", event.target.value)} placeholder="0" />
                </label>
                <label className="field">
                  <span>72h Views</span>
                  <input value={draft.views72h} onChange={(event) => updateDraft("views72h", event.target.value)} placeholder="0" />
                </label>
                <label className="field">
                  <span>7d Views</span>
                  <input value={draft.views7d} onChange={(event) => updateDraft("views7d", event.target.value)} placeholder="0" />
                </label>
                <label className="field">
                  <span>Follows Gained</span>
                  <input value={draft.followsGained} onChange={(event) => updateDraft("followsGained", event.target.value)} placeholder="0" />
                </label>
                <label className="field">
                  <span>Likes</span>
                  <input value={draft.likes} onChange={(event) => updateDraft("likes", event.target.value)} placeholder="0" />
                </label>
                <label className="field">
                  <span>Comments</span>
                  <input value={draft.comments} onChange={(event) => updateDraft("comments", event.target.value)} placeholder="0" />
                </label>
                <label className="field">
                  <span>Shares</span>
                  <input value={draft.shares} onChange={(event) => updateDraft("shares", event.target.value)} placeholder="0" />
                </label>
                <label className="field">
                  <span>Saves</span>
                  <input value={draft.saves} onChange={(event) => updateDraft("saves", event.target.value)} placeholder="0" />
                </label>
                <label className="field">
                  <span>Result Label</span>
                  <select value={draft.resultLabel} onChange={(event) => updateDraft("resultLabel", event.target.value as ResultLabel)}>
                    {RESULT_LABEL_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>{option.label}</option>
                    ))}
                  </select>
                </label>
                <div className="field field-wide">
                  <span>Platforms</span>
                  <div className="toggle-row">
                    {PLATFORM_OPTIONS.map((option) => (
                      <label key={option.value} className="toggle-chip">
                        <input
                          type="checkbox"
                          checked={draft.platforms.includes(option.value)}
                          onChange={() => toggleDraftPlatform(option.value)}
                        />
                        <span>{option.label}</span>
                      </label>
                    ))}
                  </div>
                </div>
                <label className="field field-wide">
                  <span>Hook Notes</span>
                  <textarea value={draft.hookNotes} onChange={(event) => updateDraft("hookNotes", event.target.value)} rows={5} />
                </label>
              </div>

              <div className="button-row">
                <button type="button" onClick={handleSaveDraft}>Save Metrics</button>
              </div>
            </div>
          ) : (
            <p className="subtle">Select a completed video to track posting and performance.</p>
          )}
        </section>
      </div>
    </div>
  );
}
