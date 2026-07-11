import { FormEvent, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api, PlatformPost, RunPerformance } from "../api/client";

const PLATFORM_OPTIONS = [
  { value: "tiktok", label: "TikTok" },
  { value: "instagram", label: "Instagram" },
  { value: "youtube", label: "YouTube" },
  { value: "other", label: "Other" },
] as const;

type PlatformValue = (typeof PLATFORM_OPTIONS)[number]["value"];

type SnapshotFormState = {
  capturedAt: string;
  views: string;
  likes: string;
  comments: string;
  shares: string;
  saves: string;
  averageWatchTimeSeconds: string;
  completionRatePercent: string;
  followersGained: string;
  notes: string;
};

function createLocalDateTimeValue(date = new Date()) {
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 16);
}

function toIsoFromLocalDateTime(value: string) {
  return new Date(value).toISOString();
}

function formatTimestamp(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function formatPlatformLabel(post: PlatformPost) {
  if (post.platform === "other") {
    return post.custom_platform_name || "Other";
  }
  return PLATFORM_OPTIONS.find((option) => option.value === post.platform)?.label ?? post.platform;
}

function formatCompletionRate(value?: number | null) {
  if (value === null || value === undefined) return "—";
  return `${(value * 100).toFixed(1)}%`;
}

function formatMetric(value?: number | null) {
  if (value === null || value === undefined) return "—";
  return String(value);
}

function createEmptySnapshotForm(): SnapshotFormState {
  return {
    capturedAt: createLocalDateTimeValue(),
    views: "",
    likes: "",
    comments: "",
    shares: "",
    saves: "",
    averageWatchTimeSeconds: "",
    completionRatePercent: "",
    followersGained: "",
    notes: "",
  };
}

export function PerformancePage() {
  const { runId = "" } = useParams();
  const [data, setData] = useState<RunPerformance | null>(null);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSavingPost, setIsSavingPost] = useState(false);
  const [savingSnapshotPostId, setSavingSnapshotPostId] = useState<string | null>(null);
  const [editingPostId, setEditingPostId] = useState<string | null>(null);
  const [savingEditPostId, setSavingEditPostId] = useState<string | null>(null);
  const [postForm, setPostForm] = useState({
    platform: "tiktok" as PlatformValue,
    customPlatformName: "",
    postUrl: "",
    postedAt: createLocalDateTimeValue(),
    notes: "",
  });
  const [postFormError, setPostFormError] = useState("");
  const [snapshotFormErrors, setSnapshotFormErrors] = useState<Record<string, string>>({});
  const [snapshotForms, setSnapshotForms] = useState<Record<string, SnapshotFormState>>({});
  const [editForms, setEditForms] = useState<Record<string, typeof postForm>>({});

  async function loadPerformance() {
    if (!runId) return;
    setIsLoading(true);
    try {
      const response = await api.getRunPerformance(runId);
      setData(response);
      setError("");
      setSnapshotForms((current) => {
        const next = { ...current };
        for (const post of response.platform_posts) {
          if (!next[post.id]) {
            next[post.id] = createEmptySnapshotForm();
          }
        }
        return next;
      });
      setEditForms((current) => {
        const next = { ...current };
        for (const post of response.platform_posts) {
          if (!next[post.id]) {
            next[post.id] = {
              platform: post.platform,
              customPlatformName: post.custom_platform_name ?? "",
              postUrl: post.post_url,
              postedAt: createLocalDateTimeValue(new Date(post.posted_at)),
              notes: post.notes ?? "",
            };
          }
        }
        return next;
      });
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to load performance data.");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    loadPerformance().catch(() => undefined);
  }, [runId]);

  const currentFinalSelection = data?.current_final_asset_selection ?? null;
  const canTrackPerformance = Boolean(data?.run_id);

  const sortedPosts = useMemo(() => data?.platform_posts ?? [], [data]);

  function updateSnapshotForm(postId: string, patch: Partial<SnapshotFormState>) {
    setSnapshotForms((current) => ({
      ...current,
      [postId]: {
        ...(current[postId] ?? createEmptySnapshotForm()),
        ...patch,
      },
    }));
  }

  function updateEditForm(postId: string, patch: Partial<typeof postForm>) {
    setEditForms((current) => ({
      ...current,
      [postId]: {
        ...(current[postId] ?? postForm),
        ...patch,
      },
    }));
  }

  function validatePostForm(form: typeof postForm) {
    if (!form.postUrl.trim()) return "Post URL is required.";
    if (form.platform === "other" && !form.customPlatformName.trim()) return "Custom platform name is required for Other.";
    if (form.platform !== "other" && form.customPlatformName.trim()) return "Custom platform name is only allowed for Other.";
    return "";
  }

  function buildPostPayload(form: typeof postForm) {
    return {
      platform: form.platform,
      custom_platform_name: form.platform === "other" ? form.customPlatformName.trim() : null,
      post_url: form.postUrl.trim(),
      posted_at: toIsoFromLocalDateTime(form.postedAt),
      notes: form.notes.trim() || null,
    };
  }

  function parseOptionalNumber(value: string) {
    if (!value.trim()) return null;
    return Number(value);
  }

  function validateSnapshotForm(form: SnapshotFormState) {
    const numericFields: Array<[keyof SnapshotFormState, string]> = [
      ["views", "Views"],
      ["likes", "Likes"],
      ["comments", "Comments"],
      ["shares", "Shares"],
      ["saves", "Saves"],
      ["averageWatchTimeSeconds", "Average watch time"],
      ["completionRatePercent", "Completion rate"],
      ["followersGained", "Followers gained"],
    ];

    let hasMetric = false;
    for (const [field, label] of numericFields) {
      const raw = form[field].trim();
      if (!raw) continue;
      const numeric = Number(raw);
      if (Number.isNaN(numeric)) return `${label} must be a number.`;
      if (numeric < 0) return `${label} may not be negative.`;
      if (field === "completionRatePercent" && numeric > 100) return "Completion rate must be between 0 and 100.";
      hasMetric = true;
    }
    if (!hasMetric) return "At least one metric value is required.";
    return "";
  }

  function buildSnapshotPayload(form: SnapshotFormState) {
    const completionPercent = parseOptionalNumber(form.completionRatePercent);
    return {
      captured_at: toIsoFromLocalDateTime(form.capturedAt),
      views: parseOptionalNumber(form.views),
      likes: parseOptionalNumber(form.likes),
      comments: parseOptionalNumber(form.comments),
      shares: parseOptionalNumber(form.shares),
      saves: parseOptionalNumber(form.saves),
      average_watch_time_seconds: parseOptionalNumber(form.averageWatchTimeSeconds),
      completion_rate: completionPercent === null ? null : completionPercent / 100,
      followers_gained: parseOptionalNumber(form.followersGained),
      notes: form.notes.trim() || null,
    };
  }

  async function handleCreatePost(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const validationError = validatePostForm(postForm);
    setPostFormError(validationError);
    if (validationError || !runId) return;

    setIsSavingPost(true);
    setError("");
    try {
      await api.createPlatformPost(runId, buildPostPayload(postForm));
      setPostForm({
        platform: "tiktok",
        customPlatformName: "",
        postUrl: "",
        postedAt: createLocalDateTimeValue(),
        notes: "",
      });
      await loadPerformance();
    } catch (requestError) {
      setPostFormError(requestError instanceof Error ? requestError.message : "Failed to create platform post.");
    } finally {
      setIsSavingPost(false);
    }
  }

  async function handleUpdatePost(postId: string) {
    if (!runId) return;
    const form = editForms[postId];
    const validationError = validatePostForm(form);
    setError(validationError);
    if (validationError) return;

    setSavingEditPostId(postId);
    try {
      await api.updatePlatformPost(runId, postId, buildPostPayload(form));
      setEditingPostId(null);
      setError("");
      await loadPerformance();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to update platform post.");
    } finally {
      setSavingEditPostId(null);
    }
  }

  async function handleAddSnapshot(postId: string, event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!runId) return;
    const form = snapshotForms[postId] ?? createEmptySnapshotForm();
    const validationError = validateSnapshotForm(form);
    setSnapshotFormErrors((current) => ({ ...current, [postId]: validationError }));
    if (validationError) return;

    setSavingSnapshotPostId(postId);
    setError("");
    try {
      await api.addPerformanceSnapshot(runId, postId, buildSnapshotPayload(form));
      setSnapshotForms((current) => ({ ...current, [postId]: createEmptySnapshotForm() }));
      await loadPerformance();
    } catch (requestError) {
      setSnapshotFormErrors((current) => ({
        ...current,
        [postId]: requestError instanceof Error ? requestError.message : "Failed to add performance snapshot.",
      }));
    } finally {
      setSavingSnapshotPostId(null);
    }
  }

  return (
    <div className="page stack">
      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Performance</p>
            <h2>{data?.topic ?? "Loading run..."}</h2>
          </div>
          <div className="button-row">
            {runId ? <Link className="inline-link" to={`/assets`}>Back to Asset Library</Link> : null}
            {runId ? <Link className="inline-link" to={`/review?run=${runId}`}>Back to Video Review</Link> : null}
          </div>
        </div>
        {currentFinalSelection ? (
          <div className="stack">
            <div className="key-grid">
              <div><span>Current final asset source</span><strong>{currentFinalSelection.source === "narration_render" ? "Narrated" : "Original"}</strong></div>
              <div><span>Current final asset ID</span><strong>{String(currentFinalSelection.asset?.id ?? "n/a")}</strong></div>
              <div><span>Selection revision</span><strong>{String(currentFinalSelection.selection_revision ?? 1)}</strong></div>
            </div>
            <p className="subtle">Each platform post keeps the exact final asset attribution that existed when that post was created, even if the run’s current final selection changes later.</p>
          </div>
        ) : null}
      </section>

      {error ? <p className="error">{error}</p> : null}

      <section className="panel">
        <div className="panel-header">
          <h3>Create Platform Post</h3>
          {!canTrackPerformance ? <span className="status-pill muted">Unavailable</span> : null}
        </div>
        <form className="stack" onSubmit={handleCreatePost}>
          <div className="form-grid">
            <label className="field">
              <span>Platform</span>
              <select
                value={postForm.platform}
                onChange={(event) => setPostForm((current) => ({ ...current, platform: event.target.value as PlatformValue, customPlatformName: current.platform === "other" ? current.customPlatformName : "" }))}
              >
                {PLATFORM_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>
            {postForm.platform === "other" ? (
              <label className="field">
                <span>Custom Platform Name</span>
                <input
                  value={postForm.customPlatformName}
                  onChange={(event) => setPostForm((current) => ({ ...current, customPlatformName: event.target.value }))}
                  maxLength={80}
                />
              </label>
            ) : null}
            <label className="field">
              <span>Post URL</span>
              <input
                value={postForm.postUrl}
                onChange={(event) => setPostForm((current) => ({ ...current, postUrl: event.target.value }))}
                placeholder="https://..."
              />
            </label>
            <label className="field">
              <span>Posted At</span>
              <input
                type="datetime-local"
                value={postForm.postedAt}
                onChange={(event) => setPostForm((current) => ({ ...current, postedAt: event.target.value }))}
              />
            </label>
            <label className="field field-wide">
              <span>Notes</span>
              <textarea
                value={postForm.notes}
                onChange={(event) => setPostForm((current) => ({ ...current, notes: event.target.value }))}
                rows={3}
              />
            </label>
          </div>
          {postFormError ? <p className="error-text">{postFormError}</p> : null}
          <div className="button-row">
            <button type="submit" disabled={isSavingPost || !canTrackPerformance}>
              {isSavingPost ? "Saving..." : "Create Platform Post"}
            </button>
          </div>
        </form>
      </section>

      <section className="panel">
        <div className="panel-header">
          <h3>Existing Platform Posts</h3>
          <span>{sortedPosts.length} post{sortedPosts.length === 1 ? "" : "s"}</span>
        </div>
        {isLoading ? <p className="subtle">Loading performance data...</p> : null}
        {!isLoading && sortedPosts.length === 0 ? <p className="subtle">No platform posts recorded yet.</p> : null}
        <div className="stack">
          {sortedPosts.map((post) => {
            const snapshotForm = snapshotForms[post.id] ?? createEmptySnapshotForm();
            const editForm = editForms[post.id] ?? {
              platform: post.platform,
              customPlatformName: post.custom_platform_name ?? "",
              postUrl: post.post_url,
              postedAt: createLocalDateTimeValue(new Date(post.posted_at)),
              notes: post.notes ?? "",
            };
            const isEditing = editingPostId === post.id;
            return (
              <div key={post.id} className="panel inset stack">
                <div className="panel-header">
                  <div>
                    <strong>{formatPlatformLabel(post)}</strong>
                    <p className="subtle">{formatTimestamp(post.posted_at)}</p>
                  </div>
                  <div className="button-row">
                    <a className="inline-link" href={post.post_url} target="_blank" rel="noreferrer">Open Post</a>
                    <button className="secondary" type="button" onClick={() => setEditingPostId(isEditing ? null : post.id)}>
                      {isEditing ? "Close Edit" : "Edit"}
                    </button>
                  </div>
                </div>
                <div className="key-grid">
                  <div><span>Attributed source</span><strong>{post.final_asset_source === "narration_render" ? "Narrated" : "Original"}</strong></div>
                  <div><span>Attributed asset ID</span><strong>{post.final_asset_id}</strong></div>
                  <div><span>Narration render</span><strong>{post.final_narration_render_id ?? "—"}</strong></div>
                  <div><span>Selection revision</span><strong>{String(post.final_asset_selection_revision ?? "—")}</strong></div>
                </div>
                {post.notes ? <p><strong>Notes:</strong> {post.notes}</p> : null}

                {isEditing ? (
                  <div className="stack">
                    <div className="form-grid">
                      <label className="field">
                        <span>Platform</span>
                        <select value={editForm.platform} onChange={(event) => updateEditForm(post.id, { platform: event.target.value as PlatformValue, customPlatformName: event.target.value === "other" ? editForm.customPlatformName : "" })}>
                          {PLATFORM_OPTIONS.map((option) => (
                            <option key={option.value} value={option.value}>{option.label}</option>
                          ))}
                        </select>
                      </label>
                      {editForm.platform === "other" ? (
                        <label className="field">
                          <span>Custom Platform Name</span>
                          <input value={editForm.customPlatformName} onChange={(event) => updateEditForm(post.id, { customPlatformName: event.target.value })} />
                        </label>
                      ) : null}
                      <label className="field">
                        <span>Post URL</span>
                        <input value={editForm.postUrl} onChange={(event) => updateEditForm(post.id, { postUrl: event.target.value })} />
                      </label>
                      <label className="field">
                        <span>Posted At</span>
                        <input type="datetime-local" value={editForm.postedAt} onChange={(event) => updateEditForm(post.id, { postedAt: event.target.value })} />
                      </label>
                      <label className="field field-wide">
                        <span>Notes</span>
                        <textarea value={editForm.notes} rows={2} onChange={(event) => updateEditForm(post.id, { notes: event.target.value })} />
                      </label>
                    </div>
                    <div className="button-row">
                      <button type="button" onClick={() => handleUpdatePost(post.id)} disabled={savingEditPostId === post.id}>
                        {savingEditPostId === post.id ? "Saving..." : "Save Post Metadata"}
                      </button>
                    </div>
                  </div>
                ) : null}

                <form className="stack" onSubmit={(event) => handleAddSnapshot(post.id, event)}>
                  <div className="panel inset">
                    <div className="panel-header">
                      <h4>Add Snapshot</h4>
                    </div>
                    <div className="form-grid">
                      <label className="field">
                        <span>Captured At</span>
                        <input type="datetime-local" value={snapshotForm.capturedAt} onChange={(event) => updateSnapshotForm(post.id, { capturedAt: event.target.value })} />
                      </label>
                      <label className="field">
                        <span>Views</span>
                        <input type="number" min={0} value={snapshotForm.views} onChange={(event) => updateSnapshotForm(post.id, { views: event.target.value })} />
                      </label>
                      <label className="field">
                        <span>Likes</span>
                        <input type="number" min={0} value={snapshotForm.likes} onChange={(event) => updateSnapshotForm(post.id, { likes: event.target.value })} />
                      </label>
                      <label className="field">
                        <span>Comments</span>
                        <input type="number" min={0} value={snapshotForm.comments} onChange={(event) => updateSnapshotForm(post.id, { comments: event.target.value })} />
                      </label>
                      <label className="field">
                        <span>Shares</span>
                        <input type="number" min={0} value={snapshotForm.shares} onChange={(event) => updateSnapshotForm(post.id, { shares: event.target.value })} />
                      </label>
                      <label className="field">
                        <span>Saves</span>
                        <input type="number" min={0} value={snapshotForm.saves} onChange={(event) => updateSnapshotForm(post.id, { saves: event.target.value })} />
                      </label>
                      <label className="field">
                        <span>Average Watch Time (s)</span>
                        <input type="number" min={0} step="0.01" value={snapshotForm.averageWatchTimeSeconds} onChange={(event) => updateSnapshotForm(post.id, { averageWatchTimeSeconds: event.target.value })} />
                      </label>
                      <label className="field">
                        <span>Completion Rate (%)</span>
                        <input type="number" min={0} max={100} step="0.1" value={snapshotForm.completionRatePercent} onChange={(event) => updateSnapshotForm(post.id, { completionRatePercent: event.target.value })} />
                      </label>
                      <label className="field">
                        <span>Followers Gained</span>
                        <input type="number" min={0} value={snapshotForm.followersGained} onChange={(event) => updateSnapshotForm(post.id, { followersGained: event.target.value })} />
                      </label>
                      <label className="field field-wide">
                        <span>Notes</span>
                        <textarea value={snapshotForm.notes} rows={2} onChange={(event) => updateSnapshotForm(post.id, { notes: event.target.value })} />
                      </label>
                    </div>
                    {snapshotFormErrors[post.id] ? <p className="error-text">{snapshotFormErrors[post.id]}</p> : null}
                    <div className="button-row">
                      <button type="submit" disabled={savingSnapshotPostId === post.id}>
                        {savingSnapshotPostId === post.id ? "Saving..." : "Add Snapshot"}
                      </button>
                    </div>
                  </div>
                </form>

                <div className="stack">
                  <h4>Snapshots</h4>
                  {post.snapshots.length === 0 ? <p className="subtle">No snapshots recorded yet.</p> : null}
                  {post.snapshots.map((snapshot) => (
                    <div key={snapshot.id} className="panel inset">
                      <div className="panel-header">
                        <strong>{formatTimestamp(snapshot.captured_at)}</strong>
                      </div>
                      <div className="key-grid">
                        <div><span>Views</span><strong>{formatMetric(snapshot.views)}</strong></div>
                        <div><span>Likes</span><strong>{formatMetric(snapshot.likes)}</strong></div>
                        <div><span>Comments</span><strong>{formatMetric(snapshot.comments)}</strong></div>
                        <div><span>Shares</span><strong>{formatMetric(snapshot.shares)}</strong></div>
                        <div><span>Saves</span><strong>{formatMetric(snapshot.saves)}</strong></div>
                        <div><span>Avg watch time</span><strong>{formatMetric(snapshot.average_watch_time_seconds)}</strong></div>
                        <div><span>Completion</span><strong>{formatCompletionRate(snapshot.completion_rate)}</strong></div>
                        <div><span>Followers gained</span><strong>{formatMetric(snapshot.followers_gained)}</strong></div>
                      </div>
                      {snapshot.notes ? <p><strong>Notes:</strong> {snapshot.notes}</p> : null}
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </section>
    </div>
  );
}
