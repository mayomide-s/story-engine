import { FormEvent, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import {
  api,
  PerformanceComparisonMetricName,
  PerformanceLearning,
  PerformanceLearningPatchPayload,
  PerformanceLearningType,
  PlatformPost,
  RunPerformance,
} from "../api/client";
import {
  formatPerformanceLearningAssociatedPostLabel,
  getPerformanceLearningTypeLabel,
} from "../components/PerformanceLearningsSummary";
import { PerformanceWinnerSummary } from "../components/PerformanceWinnerSummary";

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

type LearningFormState = {
  learningType: PerformanceLearningType;
  observation: string;
  evidence: string;
  nextAction: string;
  platformPostId: string;
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

function formatCount(value?: number | null) {
  if (value === null || value === undefined) return "â€”";
  return value.toLocaleString();
}

function formatRate(value?: number | null) {
  if (value === null || value === undefined) return "â€”";
  return `${(value * 100).toFixed(1)}%`;
}

function formatRatio(value?: number | null) {
  if (value === null || value === undefined) return "â€”";
  return `${(value * 100).toFixed(1)}%`;
}

function formatAgeLabel(post: PlatformPost) {
  if (post.latest_snapshot_age_label) return post.latest_snapshot_age_label;
  if (post.latest_snapshot_age_status === "captured_before_posting") return "Captured before posting";
  return "â€”";
}

function metricIndicatorLabel(status?: string, isLeader = false) {
  if (status === "only_available") return "Only available result";
  if (!isLeader) return null;
  if (status === "tie") return "Tied leader";
  if (status === "leader") return "Leader";
  return null;
}

const COMPARISON_COLUMNS: Array<{
  key: PerformanceComparisonMetricName;
  label: string;
  render: (post: PlatformPost) => string;
}> = [
  { key: "views", label: "Views", render: (post) => formatCount(post.comparison_metrics.views) },
  { key: "engagement_rate", label: "Engagement", render: (post) => formatRate(post.comparison_metrics.engagement_rate) },
  { key: "like_rate", label: "Like rate", render: (post) => formatRate(post.comparison_metrics.like_rate) },
  { key: "comment_rate", label: "Comment rate", render: (post) => formatRate(post.comparison_metrics.comment_rate) },
  { key: "share_rate", label: "Share rate", render: (post) => formatRate(post.comparison_metrics.share_rate) },
  { key: "save_rate", label: "Save rate", render: (post) => formatRate(post.comparison_metrics.save_rate) },
  { key: "completion_rate", label: "Completion", render: (post) => formatRate(post.comparison_metrics.completion_rate) },
  { key: "follower_conversion_rate", label: "Follower conversion", render: (post) => formatRate(post.comparison_metrics.follower_conversion_rate) },
  { key: "average_watch_time_ratio", label: "Watch-time ratio", render: (post) => formatRatio(post.comparison_metrics.average_watch_time_ratio) },
];

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

function createEmptyLearningForm(): LearningFormState {
  return {
    learningType: "observation",
    observation: "",
    evidence: "",
    nextAction: "",
    platformPostId: "",
  };
}

function normalizeLearningText(value: string, blankToNull = false) {
  const trimmed = value.trim();
  if (!trimmed && blankToNull) return null;
  return trimmed;
}

function formatAssociatedPostOptionLabel(post: PlatformPost, winnerPostId?: string | null) {
  const baseLabel = formatPlatformLabel(post);
  const date = formatTimestamp(post.posted_at);
  const winnerSuffix = winnerPostId === post.id ? " — Current manual winner" : "";
  return `${baseLabel}${winnerSuffix} — ${date}`;
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
  const [winnerError, setWinnerError] = useState("");
  const [winnerMutation, setWinnerMutation] = useState<{ action: "select" | "replace" | "clear"; postId?: string } | null>(null);
  const [learningForm, setLearningForm] = useState<LearningFormState>(createEmptyLearningForm);
  const [learningFormError, setLearningFormError] = useState("");
  const [isSavingLearning, setIsSavingLearning] = useState(false);
  const [editingLearningId, setEditingLearningId] = useState<string | null>(null);
  const [editingLearningForm, setEditingLearningForm] = useState<LearningFormState>(createEmptyLearningForm);
  const [editingLearningError, setEditingLearningError] = useState("");
  const [savingLearningId, setSavingLearningId] = useState<string | null>(null);
  const [archivingLearningId, setArchivingLearningId] = useState<string | null>(null);
  const [learningActionError, setLearningActionError] = useState<{ learningId: string; message: string } | null>(null);
  const [showArchivedLearnings, setShowArchivedLearnings] = useState(false);
  const [isCompactComparison, setIsCompactComparison] = useState(() =>
    typeof window !== "undefined" ? window.innerWidth < 768 : false,
  );

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

  useEffect(() => {
    function handleResize() {
      setIsCompactComparison(window.innerWidth < 768);
    }

    handleResize();
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  const currentFinalSelection = data?.current_final_asset_selection ?? null;
  const winnerSelection = data?.winner_selection ?? null;
  const canTrackPerformance = Boolean(data?.run_id);
  const comparison = data?.comparison ?? null;
  const sortedPosts = useMemo(() => data?.platform_posts ?? [], [data]);
  const learnings = useMemo(() => data?.learnings ?? [], [data]);
  const activeLearnings = useMemo(() => learnings.filter((learning) => !learning.is_archived), [learnings]);
  const archivedLearnings = useMemo(() => learnings.filter((learning) => learning.is_archived), [learnings]);
  const winnerPostId = winnerSelection?.platform_post_id ?? null;
  const learningPostIds = useMemo(() => new Set(sortedPosts.map((post) => post.id)), [sortedPosts]);

  function getMetricIndicator(postId: string, metricName: PerformanceComparisonMetricName) {
    const summary = comparison?.metrics?.[metricName];
    const isLeader = Boolean(summary?.leader_post_ids?.includes(postId));
    return metricIndicatorLabel(summary?.status, isLeader);
  }

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

  function validateLearningForm(form: LearningFormState) {
    const observation = normalizeLearningText(form.observation);
    if (!observation) return "Observation is required.";
    if (observation.length > 2000) return "Observation must be 2000 characters or fewer.";

    const evidence = normalizeLearningText(form.evidence, true);
    if (evidence && evidence.length > 2000) return "Evidence must be 2000 characters or fewer.";

    const nextAction = normalizeLearningText(form.nextAction, true);
    if (nextAction && nextAction.length > 2000) return "Next action must be 2000 characters or fewer.";

    if (form.platformPostId && !learningPostIds.has(form.platformPostId)) {
      return "Select an associated post from this run.";
    }

    return "";
  }

  function buildLearningPayload(form: LearningFormState) {
    const observation = normalizeLearningText(form.observation) ?? "";
    return {
      learning_type: form.learningType,
      observation,
      evidence: normalizeLearningText(form.evidence, true),
      next_action: normalizeLearningText(form.nextAction, true),
      platform_post_id: form.platformPostId || null,
    };
  }

  function createLearningEditPayload(
    learning: PerformanceLearning,
    form: LearningFormState,
  ): PerformanceLearningPatchPayload | null {
    const normalized = buildLearningPayload(form);
    const currentObservation = learning.observation;
    const currentEvidence = learning.evidence ?? null;
    const currentNextAction = learning.next_action ?? null;
    const currentPlatformPostId = learning.platform_post_id ?? null;

    const payload: PerformanceLearningPatchPayload = {};
    if (normalized.learning_type !== learning.learning_type) payload.learning_type = normalized.learning_type;
    if (normalized.observation !== currentObservation) payload.observation = normalized.observation;
    if (normalized.evidence !== currentEvidence) payload.evidence = normalized.evidence;
    if (normalized.next_action !== currentNextAction) payload.next_action = normalized.next_action;
    if (normalized.platform_post_id !== currentPlatformPostId) payload.platform_post_id = normalized.platform_post_id;

    return Object.keys(payload).length ? payload : null;
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

  async function handleCreateLearning(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!runId) return;

    const validationError = validateLearningForm(learningForm);
    setLearningFormError(validationError);
    if (validationError) return;

    setIsSavingLearning(true);
    setLearningActionError(null);
    try {
      const response = await api.createPerformanceLearning(runId, buildLearningPayload(learningForm));
      setData(response);
      setLearningForm(createEmptyLearningForm());
      setLearningFormError("");
    } catch (requestError) {
      setLearningFormError(requestError instanceof Error ? requestError.message : "Failed to save the performance learning.");
    } finally {
      setIsSavingLearning(false);
    }
  }

  function handleStartEditLearning(learning: PerformanceLearning) {
    setEditingLearningId(learning.id);
    setEditingLearningError("");
    setLearningActionError(null);
    setEditingLearningForm({
      learningType: learning.learning_type,
      observation: learning.observation,
      evidence: learning.evidence ?? "",
      nextAction: learning.next_action ?? "",
      platformPostId: learning.platform_post_id ?? "",
    });
  }

  async function handleSaveLearning(learning: PerformanceLearning) {
    if (!runId) return;
    const validationError = validateLearningForm(editingLearningForm);
    setEditingLearningError(validationError);
    if (validationError) return;

    const payload = createLearningEditPayload(learning, editingLearningForm);
    if (!payload) {
      setEditingLearningError("");
      setEditingLearningId(null);
      return;
    }

    setSavingLearningId(learning.id);
    setLearningActionError(null);
    try {
      const response = await api.updatePerformanceLearning(runId, learning.id, payload);
      setData(response);
      setEditingLearningId(null);
      setEditingLearningError("");
    } catch (requestError) {
      setEditingLearningError(requestError instanceof Error ? requestError.message : "Failed to update the performance learning.");
    } finally {
      setSavingLearningId(null);
    }
  }

  async function handleArchiveLearning(learning: PerformanceLearning) {
    if (!runId) return;
    const confirmed = window.confirm(
      "Archive this performance learning? It will become read-only and remain available under archived learnings.",
    );
    if (!confirmed) return;

    setArchivingLearningId(learning.id);
    setEditingLearningError("");
    setLearningActionError(null);
    try {
      const response = await api.archivePerformanceLearning(runId, learning.id);
      setData(response);
      if (editingLearningId === learning.id) {
        setEditingLearningId(null);
      }
    } catch (requestError) {
      setLearningActionError({
        learningId: learning.id,
        message: requestError instanceof Error ? requestError.message : "Failed to archive the performance learning.",
      });
    } finally {
      setArchivingLearningId(null);
    }
  }

  async function handleSelectWinner(post: PlatformPost) {
    if (!runId) return;
    const currentWinnerPostId = winnerSelection?.platform_post_id ?? null;
    const isReplacing = Boolean(currentWinnerPostId && currentWinnerPostId !== post.id);
    if (isReplacing) {
      const confirmed = window.confirm("Replace the current manual winner with this post? Metric leaders will remain unchanged.");
      if (!confirmed) return;
    }

    setWinnerMutation({ action: isReplacing ? "replace" : "select", postId: post.id });
    setWinnerError("");
    try {
      const response = await api.selectPerformanceWinner(runId, post.id);
      setData(response);
    } catch (requestError) {
      setWinnerError(requestError instanceof Error ? requestError.message : "Failed to update the manual winner.");
    } finally {
      setWinnerMutation(null);
    }
  }

  async function handleClearWinner() {
    if (!runId || !winnerSelection?.platform_post_id) return;
    const confirmed = window.confirm("Clear the current manual winner? Comparison data and snapshots will remain unchanged.");
    if (!confirmed) return;

    setWinnerMutation({ action: "clear", postId: winnerSelection.platform_post_id });
    setWinnerError("");
    try {
      const response = await api.clearPerformanceWinner(runId);
      setData(response);
    } catch (requestError) {
      setWinnerError(requestError instanceof Error ? requestError.message : "Failed to clear the manual winner.");
    } finally {
      setWinnerMutation(null);
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
          <h3>Comparison Snapshot</h3>
          <span>{sortedPosts.length} post{sortedPosts.length === 1 ? "" : "s"}</span>
        </div>
        <PerformanceWinnerSummary
          winnerSelection={winnerSelection}
          performanceHref={runId ? `/performance/${runId}` : undefined}
          heading="Manual winner"
        />
        {winnerSelection?.post ? (
          <div className="button-row">
            <button
              type="button"
              className="secondary"
              onClick={handleClearWinner}
              disabled={winnerMutation !== null}
            >
              {winnerMutation?.action === "clear" ? "Clearing..." : "Clear winner"}
            </button>
          </div>
        ) : null}
        {winnerError ? <p className="error-text">{winnerError}</p> : null}
        <p className="subtle">These comparisons describe the recorded results. They do not prove that a specific topic, format, or creative choice caused the difference.</p>
        {comparison?.mixed_age_warning ? (
          <div className="notice-card">
            <strong>Mixed measurement ages</strong>
            <p>{comparison.mixed_age_warning_text}</p>
          </div>
        ) : null}
        {comparison?.has_invalid_capture_age ? (
          <div className="notice-card danger">
            <strong>Timestamp check needed</strong>
            <p>{comparison.invalid_capture_age_warning_text}</p>
          </div>
        ) : null}
        {!sortedPosts.length ? (
          <p className="subtle">Add at least one platform post and one snapshot to compare recorded performance.</p>
        ) : null}
        {sortedPosts.length > 0 && isCompactComparison ? (
          <div className="stack">
            {sortedPosts.map((post) => (
              <div key={`comparison-${post.id}`} className="panel inset stack">
                <div className="panel-header">
                  <strong>{formatPlatformLabel(post)}</strong>
                  <div className="button-row">
                    {winnerSelection?.platform_post_id === post.id ? <span className="status-pill success">Manual winner</span> : null}
                    <span>{formatTimestamp(post.latest_snapshot?.captured_at ?? null)}</span>
                  </div>
                </div>
                <div className="key-grid">
                  <div><span>Age at capture</span><strong>{formatAgeLabel(post)}</strong></div>
                  <div><span>Attributed duration</span><strong>{post.attributed_asset_duration_seconds ?? "â€”"}</strong></div>
                </div>
                {winnerSelection?.platform_post_id !== post.id ? (
                  <div className="button-row">
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => handleSelectWinner(post)}
                      disabled={winnerMutation !== null}
                    >
                      {winnerMutation?.postId === post.id
                        ? winnerMutation.action === "replace"
                          ? "Changing..."
                          : "Selecting..."
                        : winnerSelection?.platform_post_id
                          ? "Change winner"
                          : "Mark as winner"}
                    </button>
                  </div>
                ) : null}
                <div className="stack compact">
                  {COMPARISON_COLUMNS.map((column) => {
                    const indicator = getMetricIndicator(post.id, column.key);
                    return (
                      <div key={`${post.id}-${column.key}`} className="key-grid">
                        <div><span>{column.label}</span><strong>{column.render(post)}</strong></div>
                        <div><span>Status</span><strong>{indicator ?? "â€”"}</strong></div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        ) : null}
        {sortedPosts.length > 0 && !isCompactComparison ? (
          <div className="scroll-panel">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Post</th>
                  <th>Latest capture</th>
                  <th>Age at capture</th>
                  <th>Manual winner</th>
                  {COMPARISON_COLUMNS.map((column) => (
                    <th key={column.key}>{column.label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {sortedPosts.map((post) => (
                  <tr key={`comparison-row-${post.id}`}>
                    <td>{formatPlatformLabel(post)}</td>
                    <td>{formatTimestamp(post.latest_snapshot?.captured_at ?? null)}</td>
                    <td>{formatAgeLabel(post)}</td>
                    <td>
                      {winnerSelection?.platform_post_id === post.id ? (
                        <span className="status-pill success">Manual winner</span>
                      ) : (
                        <button
                          type="button"
                          className="secondary"
                          onClick={() => handleSelectWinner(post)}
                          disabled={winnerMutation !== null}
                        >
                          {winnerMutation?.postId === post.id
                            ? winnerMutation.action === "replace"
                              ? "Changing..."
                              : "Selecting..."
                            : winnerSelection?.platform_post_id
                              ? "Change winner"
                              : "Mark as winner"}
                        </button>
                      )}
                    </td>
                    {COMPARISON_COLUMNS.map((column) => {
                      const indicator = getMetricIndicator(post.id, column.key);
                      return (
                        <td key={`${post.id}-${column.key}`}>
                          <div>{column.render(post)}</div>
                          {indicator ? <span className="status-pill muted">{indicator}</span> : null}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>

      <section className="panel">
        <div className="panel-header">
          <h3>Performance learnings</h3>
          <span>{activeLearnings.length} active</span>
        </div>
        <p className="subtle">Saved observations describe the available evidence but do not prove causation.</p>
        <form className="stack" onSubmit={handleCreateLearning}>
          <div className="form-grid">
            <label className="field">
              <span>Category</span>
              <select
                value={learningForm.learningType}
                onChange={(event) =>
                  setLearningForm((current) => ({
                    ...current,
                    learningType: event.target.value as PerformanceLearningType,
                  }))}
              >
                <option value="worked">Worked</option>
                <option value="did_not_work">Did not work</option>
                <option value="next_test">Test next</option>
                <option value="observation">Observation</option>
              </select>
            </label>
            <label className="field">
              <span>Associated post</span>
              <select
                value={learningForm.platformPostId}
                onChange={(event) => setLearningForm((current) => ({ ...current, platformPostId: event.target.value }))}
              >
                <option value="">No specific post</option>
                {sortedPosts.map((post) => (
                  <option key={post.id} value={post.id}>
                    {formatAssociatedPostOptionLabel(post, winnerPostId)}
                  </option>
                ))}
              </select>
            </label>
            <label className="field field-wide">
              <span>Observation</span>
              <textarea
                value={learningForm.observation}
                rows={4}
                maxLength={2000}
                onChange={(event) => setLearningForm((current) => ({ ...current, observation: event.target.value }))}
              />
              <span className="subtle">{learningForm.observation.length}/2000</span>
            </label>
            <label className="field field-wide">
              <span>Evidence</span>
              <textarea
                value={learningForm.evidence}
                rows={3}
                maxLength={2000}
                onChange={(event) => setLearningForm((current) => ({ ...current, evidence: event.target.value }))}
              />
              <span className="subtle">{learningForm.evidence.length}/2000</span>
            </label>
            <label className="field field-wide">
              <span>Next action</span>
              <textarea
                value={learningForm.nextAction}
                rows={3}
                maxLength={2000}
                onChange={(event) => setLearningForm((current) => ({ ...current, nextAction: event.target.value }))}
              />
              <span className="subtle">{learningForm.nextAction.length}/2000</span>
            </label>
          </div>
          {learningFormError ? <p className="error-text">{learningFormError}</p> : null}
          <div className="button-row">
            <button type="submit" disabled={isSavingLearning}>
              {isSavingLearning ? "Saving..." : "Save learning"}
            </button>
          </div>
        </form>

        <div className="stack">
          <div className="panel-header">
            <h4>Active learnings</h4>
            {archivedLearnings.length ? (
              <button
                type="button"
                className="secondary"
                onClick={() => setShowArchivedLearnings((current) => !current)}
              >
                {showArchivedLearnings ? "Hide archived" : `Show archived (${archivedLearnings.length})`}
              </button>
            ) : null}
          </div>
          {!activeLearnings.length ? (
            <p className="subtle">
              {archivedLearnings.length
                ? "No active performance learnings."
                : "No performance learnings have been saved yet."}
            </p>
          ) : null}
          {activeLearnings.map((learning) => {
            const isEditing = editingLearningId === learning.id;
            const associatedLabel = formatPerformanceLearningAssociatedPostLabel(learning);
            const isCurrentWinner = winnerPostId !== null && learning.platform_post_id === winnerPostId;
            const updatedChanged = learning.updated_at !== learning.created_at;

            return (
              <div key={learning.id} className="panel inset stack">
                <div className="panel-header">
                  <div className="button-row">
                    <span className="status-pill muted">{getPerformanceLearningTypeLabel(learning.learning_type)}</span>
                    {learning.is_archived ? <span className="status-pill">Archived</span> : null}
                  </div>
                  {!learning.is_archived ? (
                    <div className="button-row">
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => {
                          if (isEditing) {
                            setEditingLearningId(null);
                            setEditingLearningError("");
                            return;
                          }
                          handleStartEditLearning(learning);
                        }}
                        disabled={savingLearningId === learning.id || archivingLearningId === learning.id}
                      >
                        {isEditing ? "Cancel" : "Edit"}
                      </button>
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => handleArchiveLearning(learning)}
                        disabled={savingLearningId === learning.id || archivingLearningId === learning.id}
                      >
                        {archivingLearningId === learning.id ? "Archiving..." : "Archive"}
                      </button>
                    </div>
                  ) : null}
                </div>

                {isEditing ? (
                  <div className="stack">
                    <div className="form-grid">
                      <label className="field">
                        <span>Category</span>
                        <select
                          value={editingLearningForm.learningType}
                          onChange={(event) =>
                            setEditingLearningForm((current) => ({
                              ...current,
                              learningType: event.target.value as PerformanceLearningType,
                            }))}
                        >
                          <option value="worked">Worked</option>
                          <option value="did_not_work">Did not work</option>
                          <option value="next_test">Test next</option>
                          <option value="observation">Observation</option>
                        </select>
                      </label>
                      <label className="field">
                        <span>Associated post</span>
                        <select
                          value={editingLearningForm.platformPostId}
                          onChange={(event) =>
                            setEditingLearningForm((current) => ({ ...current, platformPostId: event.target.value }))}
                        >
                          <option value="">No specific post</option>
                          {sortedPosts.map((post) => (
                            <option key={post.id} value={post.id}>
                              {formatAssociatedPostOptionLabel(post, winnerPostId)}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label className="field field-wide">
                        <span>Observation</span>
                        <textarea
                          value={editingLearningForm.observation}
                          rows={4}
                          maxLength={2000}
                          onChange={(event) =>
                            setEditingLearningForm((current) => ({ ...current, observation: event.target.value }))}
                        />
                        <span className="subtle">{editingLearningForm.observation.length}/2000</span>
                      </label>
                      <label className="field field-wide">
                        <span>Evidence</span>
                        <textarea
                          value={editingLearningForm.evidence}
                          rows={3}
                          maxLength={2000}
                          onChange={(event) =>
                            setEditingLearningForm((current) => ({ ...current, evidence: event.target.value }))}
                        />
                        <span className="subtle">{editingLearningForm.evidence.length}/2000</span>
                      </label>
                      <label className="field field-wide">
                        <span>Next action</span>
                        <textarea
                          value={editingLearningForm.nextAction}
                          rows={3}
                          maxLength={2000}
                          onChange={(event) =>
                            setEditingLearningForm((current) => ({ ...current, nextAction: event.target.value }))}
                        />
                        <span className="subtle">{editingLearningForm.nextAction.length}/2000</span>
                      </label>
                    </div>
                    {editingLearningError ? <p className="error-text">{editingLearningError}</p> : null}
                    <div className="button-row">
                      <button
                        type="button"
                        onClick={() => handleSaveLearning(learning)}
                        disabled={savingLearningId === learning.id}
                      >
                        {savingLearningId === learning.id ? "Saving..." : "Save changes"}
                      </button>
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => {
                          setEditingLearningId(null);
                          setEditingLearningError("");
                        }}
                        disabled={savingLearningId === learning.id}
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <>
                    <p style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{learning.observation}</p>
                    {learning.evidence ? (
                      <div>
                        <strong>Evidence</strong>
                        <p style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{learning.evidence}</p>
                      </div>
                    ) : null}
                    {learning.next_action ? (
                      <div>
                        <strong>Next action</strong>
                        <p style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{learning.next_action}</p>
                      </div>
                    ) : null}
                  </>
                )}

                {associatedLabel ? (
                  <div className="stack compact">
                    <div className="button-row">
                      <strong>Associated post</strong>
                      {isCurrentWinner ? <span className="status-pill muted">Current manual winner</span> : null}
                    </div>
                    <p>{associatedLabel}</p>
                    {learning.associated_post?.posted_at ? <p className="subtle">Posted {formatTimestamp(learning.associated_post.posted_at)}</p> : null}
                    {learning.associated_post?.post_url ? (
                      <a className="inline-link" href={learning.associated_post.post_url} target="_blank" rel="noreferrer">
                        Open associated post
                      </a>
                    ) : null}
                  </div>
                ) : null}

                <div className="key-grid">
                  <div><span>Created</span><strong>{formatTimestamp(learning.created_at)}</strong></div>
                  <div><span>Updated</span><strong>{updatedChanged ? formatTimestamp(learning.updated_at) : "—"}</strong></div>
                </div>
                {learningActionError?.learningId === learning.id ? <p className="error-text">{learningActionError.message}</p> : null}
              </div>
            );
          })}

          {showArchivedLearnings && archivedLearnings.length ? (
            <div className="stack">
              <h4>Archived learnings</h4>
              {archivedLearnings.map((learning) => {
                const associatedLabel = formatPerformanceLearningAssociatedPostLabel(learning);
                return (
                  <div key={learning.id} className="panel inset stack">
                    <div className="panel-header">
                      <div className="button-row">
                        <span className="status-pill muted">{getPerformanceLearningTypeLabel(learning.learning_type)}</span>
                        <span className="status-pill">Archived</span>
                      </div>
                      <span>{learning.archived_at ? formatTimestamp(learning.archived_at) : "Archived"}</span>
                    </div>
                    <p style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{learning.observation}</p>
                    {learning.evidence ? (
                      <div>
                        <strong>Evidence</strong>
                        <p style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{learning.evidence}</p>
                      </div>
                    ) : null}
                    {learning.next_action ? (
                      <div>
                        <strong>Next action</strong>
                        <p style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{learning.next_action}</p>
                      </div>
                    ) : null}
                    {associatedLabel ? (
                      <div className="stack compact">
                        <strong>Associated post</strong>
                        <p>{associatedLabel}</p>
                        {learning.associated_post?.post_url ? (
                          <a className="inline-link" href={learning.associated_post.post_url} target="_blank" rel="noreferrer">
                            Open associated post
                          </a>
                        ) : null}
                      </div>
                    ) : null}
                    <div className="key-grid">
                      <div><span>Created</span><strong>{formatTimestamp(learning.created_at)}</strong></div>
                      <div><span>Updated</span><strong>{formatTimestamp(learning.updated_at)}</strong></div>
                      <div><span>Archived</span><strong>{formatTimestamp(learning.archived_at)}</strong></div>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : null}
        </div>
      </section>

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
                    {winnerSelection?.platform_post_id === post.id ? <span className="status-pill success">Manual winner</span> : null}
                    {winnerSelection?.platform_post_id !== post.id ? (
                      <button
                        className="secondary"
                        type="button"
                        onClick={() => handleSelectWinner(post)}
                        disabled={winnerMutation !== null}
                      >
                        {winnerMutation?.postId === post.id
                          ? winnerMutation.action === "replace"
                            ? "Changing..."
                            : "Selecting..."
                          : winnerSelection?.platform_post_id
                            ? "Change winner"
                            : "Mark as winner"}
                      </button>
                    ) : null}
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
