export type PipelineRunSummary = {
  id: string;
  topic: string;
  status: string;
  current_stage: string;
  provider?: string | null;
  video_status?: string | null;
  provider_job_id?: string | null;
  error_message?: string | null;
  review_notes?: string | null;
  created_at: string;
};

export type AccountDefaults = {
  account_name: string;
  niche: string;
  account_config_json: {
    default_style_preset: string;
    target_platforms: string[];
    default_caption_tone: string;
    default_hashtag_set: string[];
    default_duration_seconds: number;
    default_audience_level: string;
    default_content_format: string;
    brand_description: string;
    preferred_cta: string;
    avoid_phrases: string[];
    emoji_preference: string;
    style_presets: Record<string, { style: string; prompt_modifier: string }>;
    [key: string]: unknown;
  };
};

export type PipelineRunDetail = {
  pipeline_run: Record<string, unknown>;
  idea: Record<string, unknown> | null;
  script: Record<string, unknown> | null;
  storyboard: Record<string, unknown> | null;
  video: Record<string, unknown> | null;
  assets: Record<string, unknown>[];
  prompt_logs: Record<string, unknown>[];
  quality_checks: Record<string, unknown>[];
  manual_post_package: Record<string, unknown> | null;
  pipeline_events: Record<string, unknown>[];
  prompt_preview?: string | null;
  content_critique?: Record<string, unknown> | null;
  story_adherence_review?: Record<string, unknown> | null;
  narration_draft?: Record<string, unknown> | null;
  latest_narration_render?: Record<string, unknown> | null;
  narration_renders?: Record<string, unknown>[];
  final_asset_selection?: FinalAssetSelection | null;
  winner_selection?: WinnerSelection | null;
  performance_learnings_summary?: PerformanceLearningsSummary | null;
  review_sections?: Record<string, string> | null;
  review_preflight?: {
    scores?: Record<string, number>;
    prompt_length?: {
      current: number;
      target: number;
      limit: number;
      too_long: boolean;
      warning: boolean;
    };
    prompt_valid?: boolean;
    low_score_warning?: boolean;
    summary?: string;
  } | null;
};

export type FinalAssetSelection = {
  source: "source_video" | "narration_render";
  asset: Record<string, unknown>;
  narration_render_id?: string | null;
  selection_revision: number;
  selected_at?: string | null;
  narration_transcript?: string | null;
  caption_cues: Record<string, unknown>[];
  ai_voice_disclosure?: string | null;
  voice_is_ai_generated: boolean;
  original_video_asset: Record<string, unknown>;
  can_revert_to_source: boolean;
};

export type WinnerPostSummary = {
  id: string;
  platform: "tiktok" | "instagram" | "youtube" | "other";
  custom_platform_name?: string | null;
  post_url: string;
  posted_at: string;
  final_asset_id: string;
  final_asset_source: "source_video" | "narration_render";
};

export type WinnerSelection = {
  platform_post_id: string | null;
  selected_at: string | null;
  selection_revision: number;
  post: WinnerPostSummary | null;
};

export type PerformanceLearningType =
  | "worked"
  | "did_not_work"
  | "next_test"
  | "observation";

export type PerformanceLearningAssociatedPostSummary = {
  id: string;
  platform: "tiktok" | "instagram" | "youtube" | "other";
  custom_platform_name?: string | null;
  post_url: string;
  posted_at: string;
};

export type PerformanceLearning = {
  id: string;
  pipeline_run_id: string;
  learning_type: PerformanceLearningType;
  observation: string;
  evidence?: string | null;
  next_action?: string | null;
  platform_post_id?: string | null;
  associated_post?: PerformanceLearningAssociatedPostSummary | null;
  is_archived: boolean;
  archived_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type PerformanceLearningsSummary = {
  active_count: number;
  items: PerformanceLearning[];
};

export type SocialConnectionSummary = {
  id: string;
  platform: "youtube";
  display_name?: string | null;
  username?: string | null;
  external_identity_hint: string;
  connection_status: string;
  granted_scopes: string[];
  token_expires_at?: string | null;
  token_health: string;
  is_default: boolean;
  connected_at?: string | null;
  disconnected_at?: string | null;
  last_error_code?: string | null;
  created_at: string;
  updated_at: string;
};

export type SocialAuthorizeResponse = {
  platform: "youtube";
  authorization_url: string;
  expires_at: string;
};

export type PublicationTargetState =
  | "pending"
  | "validating"
  | "queued"
  | "uploading"
  | "processing"
  | "uploaded_private"
  | "published"
  | "retryable_failure"
  | "permanent_failure"
  | "outcome_uncertain"
  | "cancelled";

export type PublicationJobStatus =
  | "draft"
  | "ready"
  | "approved"
  | "active"
  | "published"
  | "partially_published"
  | "failed"
  | "cancelled";

export type PublicationTarget = {
  id: string;
  social_connection_id: string;
  channel_display_name?: string | null;
  channel_username?: string | null;
  channel_external_account_id?: string | null;
  platform: string;
  visibility: "private" | "unlisted" | "public";
  actual_visibility?: string | null;
  title: string;
  caption?: string | null;
  tags: string[];
  category_id: string;
  self_declared_made_for_kids: boolean;
  contains_synthetic_media: boolean;
  options: Record<string, unknown>;
  state: PublicationTargetState;
  idempotency_key: string;
  provider_video_id?: string | null;
  provider_submission_id?: string | null;
  provider_media_id?: string | null;
  provider_upload_status?: string | null;
  provider_processing_status?: string | null;
  public_post_url?: string | null;
  platform_post_id?: string | null;
  attempt_count: number;
  upload_bytes_total?: number | null;
  upload_bytes_sent?: number | null;
  upload_progress_percent?: number | null;
  next_poll_at?: string | null;
  processing_last_checked_at?: string | null;
  outcome_confirmed_at?: string | null;
  last_error_code?: string | null;
  last_error_message?: string | null;
  reconnect_required: boolean;
  submitted_at?: string | null;
  published_at?: string | null;
  created_at: string;
  updated_at: string;
  platform_post_creation_eligible: boolean;
  visibility_semantics: string;
  available_actions: string[];
};

export type PublicationJob = {
  id: string;
  pipeline_run_id: string;
  manual_post_package_id: string;
  final_asset_id: string;
  final_asset_selection_revision: number;
  final_asset_source: string;
  final_asset_sha256: string;
  final_asset_metadata: Record<string, unknown>;
  status: PublicationJobStatus;
  approved_at?: string | null;
  completed_at?: string | null;
  created_at: string;
  updated_at: string;
  targets: PublicationTarget[];
  selected_asset_is_frozen: boolean;
  selected_asset_has_changed_since_draft: boolean;
  available_actions: string[];
};

export type PublicationJobDraftPayload = {
  connection_id?: string | null;
  title: string;
  caption?: string | null;
  tags: string[];
  category_id: string;
  privacy: "private" | "unlisted" | "public";
  self_declared_made_for_kids: boolean;
  contains_synthetic_media: boolean;
};

export type StoryAdherenceHumanDecision = "approve" | "needs_review" | "regenerate";
export type NarrationHumanDecision = "approve" | "needs_revision" | "reject";

export type IdeaQueueItem = {
  id: string;
  account_id: string;
  topic: string;
  style_preset: string;
  input_config_json: Record<string, unknown>;
  target_platform: string;
  priority: string;
  status: string;
  notes?: string | null;
  planned_date?: string | null;
  pipeline_run_id?: string | null;
  idea_score?: IdeaScore | null;
  created_at: string;
  updated_at: string;
};

export type IdeaScore = {
  item_id: string;
  hook_strength: number;
  beginner_clarity: number;
  visual_potential: number;
  platform_fit: number;
  estimated_production_value: number;
  overall_score: number;
  provider: string;
  model: string;
};

export type AssetLibraryItem = {
  run_id: string;
  topic: string;
  style_preset: string;
  provider: string;
  run_status: string;
  video_status: string;
  quality_score?: number | null;
  created_at: string;
  thumbnail_url?: string | null;
  video_url: string;
  original_video_url?: string | null;
  final_asset_source?: string | null;
  final_narration_render_id?: string | null;
  target_platform?: string | null;
  caption?: string | null;
  prompt_text?: string | null;
  manual_posting_status?: string | null;
};

export type AssetLibraryDetail = {
  pipeline_run: Record<string, unknown>;
  video: Record<string, unknown>;
  video_asset: Record<string, unknown>;
  final_video_asset: Record<string, unknown>;
  final_asset_selection: FinalAssetSelection | null;
  winner_selection: WinnerSelection | null;
  performance_learnings_summary?: PerformanceLearningsSummary | null;
  thumbnail_asset: Record<string, unknown> | null;
  idea: Record<string, unknown> | null;
  quality_check: Record<string, unknown> | null;
  manual_post_package: Record<string, unknown> | null;
  idea_queue_item: Record<string, unknown> | null;
};

export type ExportPlatformSection = {
  recommended_caption: string;
  hashtags: string[];
  title?: string | null;
  description?: string | null;
  checklist: string[];
  full_post_text: string;
  manual_post_url?: string | null;
};

export type AssetExportPack = {
  run_id: string;
  topic: string;
  style_preset: string;
  provider: string;
  created_at: string;
  video_public_url: string;
  original_video_public_url?: string | null;
  thumbnail_public_url?: string | null;
  caption: string;
  hashtags: string[];
  final_prompt_used: string;
  quality_score?: number | null;
  quality_checklist: Record<string, unknown>;
  quality_critique?: string | null;
  idea_title?: string | null;
  idea_hook?: string | null;
  alternative_captions: string[];
  alternative_hooks: string[];
  manual_posting_status: string;
  manual_post_urls: {
    tiktok?: string | null;
    instagram?: string | null;
    youtube?: string | null;
  };
  final_asset_id: string;
  final_asset_source: "source_video" | "narration_render";
  final_narration_render_id?: string | null;
  final_asset_selection_revision: number;
  final_asset_selected_at?: string | null;
  narration_transcript?: string | null;
  caption_cues: Record<string, unknown>[];
  ai_voice_disclosure?: string | null;
  voice_is_ai_generated: boolean;
  target_platform?: string | null;
  linked_pipeline_run_id: string;
  linked_idea_queue_item_id?: string | null;
  platform_sections: {
    tiktok: ExportPlatformSection;
    instagram_reels: ExportPlatformSection;
    youtube_shorts: ExportPlatformSection;
  };
};

export type PerformanceSnapshot = {
  id: string;
  platform_post_id: string;
  captured_at: string;
  views?: number | null;
  likes?: number | null;
  comments?: number | null;
  shares?: number | null;
  saves?: number | null;
  average_watch_time_seconds?: number | null;
  completion_rate?: number | null;
  followers_gained?: number | null;
  notes?: string | null;
  created_at: string;
};

export type PerformanceComparisonMetricName =
  | "views"
  | "engagement_rate"
  | "like_rate"
  | "comment_rate"
  | "share_rate"
  | "save_rate"
  | "completion_rate"
  | "follower_conversion_rate"
  | "average_watch_time_ratio";

export type PerformanceComparisonMetricStatus = "unavailable" | "only_available" | "leader" | "tie";
export type PerformanceComparisonAgeStatus = "valid" | "captured_before_posting" | "unavailable";
export type PerformanceComparisonAgeBucket = "under_24h" | "1_3d" | "3_7d" | "7_30d" | "30d_plus";

export type PerformanceComparisonMetricValues = {
  views?: number | null;
  engagement_rate?: number | null;
  like_rate?: number | null;
  comment_rate?: number | null;
  share_rate?: number | null;
  save_rate?: number | null;
  completion_rate?: number | null;
  follower_conversion_rate?: number | null;
  average_watch_time_ratio?: number | null;
};

export type PerformanceMetricLeadershipSummary = {
  status: PerformanceComparisonMetricStatus;
  comparable_post_count: number;
  leader_post_ids: string[];
};

export type PerformanceComparisonSummary = {
  latest_snapshot_ordering: string[];
  mixed_age_warning: boolean;
  mixed_age_warning_text?: string | null;
  has_invalid_capture_age: boolean;
  invalid_capture_age_warning_text?: string | null;
  metrics: Record<PerformanceComparisonMetricName, PerformanceMetricLeadershipSummary>;
};

export type PlatformPost = {
  id: string;
  pipeline_run_id: string;
  manual_post_package_id: string;
  final_asset_id: string;
  final_asset_source: "source_video" | "narration_render";
  platform: "tiktok" | "instagram" | "youtube" | "other";
  post_url: string;
  posted_at: string;
  custom_platform_name?: string | null;
  final_narration_render_id?: string | null;
  final_asset_selection_revision?: number | null;
  final_asset_metadata_json?: Record<string, unknown> | null;
  notes?: string | null;
  created_at: string;
  updated_at: string;
  final_asset?: Record<string, unknown> | null;
  attributed_asset_duration_seconds?: number | null;
  latest_snapshot?: PerformanceSnapshot | null;
  latest_snapshot_age_seconds?: number | null;
  latest_snapshot_age_label?: string | null;
  latest_snapshot_age_bucket?: PerformanceComparisonAgeBucket | null;
  latest_snapshot_age_status: PerformanceComparisonAgeStatus;
  comparison_metrics: PerformanceComparisonMetricValues;
  snapshots: PerformanceSnapshot[];
};

export type RunPerformance = {
  run_id: string;
  topic: string;
  current_final_asset_selection: FinalAssetSelection | null;
  winner_selection: WinnerSelection | null;
  comparison: PerformanceComparisonSummary;
  learnings: PerformanceLearning[];
  platform_posts: PlatformPost[];
};

export type PerformanceLearningCreatePayload = {
  learning_type: PerformanceLearningType;
  observation: string;
  evidence?: string | null;
  next_action?: string | null;
  platform_post_id?: string | null;
};

export type PerformanceLearningPatchPayload = {
  learning_type?: PerformanceLearningType;
  observation?: string;
  evidence?: string | null;
  next_action?: string | null;
  platform_post_id?: string | null;
};

export type HealthCheck = {
  status: string;
};

export type HealthDetails = {
  status: string;
  backend_reachable: boolean;
  environment: string;
  auth_enabled: boolean;
  video_provider: string;
  storage_provider: string;
  runway_mode_enabled: boolean;
  r2_public_base_url_configured: boolean;
  checks: Record<string, { status: string; detail: string; errors?: string[]; mode?: string; provider?: string; sdk_version?: string | null }>;
};

export type AccessStatus = {
  auth_enabled: boolean;
  authenticated: boolean;
  environment: string;
};

export type AccessLoginResponse = {
  auth_enabled: boolean;
  token: string;
};

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api";
const BACKEND_BASE = API_BASE.replace(/\/api\/?$/, "");
const ACCESS_TOKEN_KEY = "story-engine-access-token";

export function getStoredAccessToken() {
  return window.localStorage.getItem(ACCESS_TOKEN_KEY);
}

export function setStoredAccessToken(token: string) {
  window.localStorage.setItem(ACCESS_TOKEN_KEY, token);
}

export function clearStoredAccessToken() {
  window.localStorage.removeItem(ACCESS_TOKEN_KEY);
}

async function request<T>(path: string, options?: RequestInit, baseUrl = API_BASE): Promise<T> {
  let response: Response;
  try {
    const token = getStoredAccessToken();
    const headers = new Headers(options?.headers ?? {});
    if (!headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    if (token && !headers.has("Authorization")) {
      headers.set("Authorization", `Bearer ${token}`);
    }
    response = await fetch(`${baseUrl}${path}`, {
      headers,
      ...options
    });
  } catch {
    throw new Error("Backend unavailable");
  }
  if (!response.ok) {
    let detail = `Request failed: ${response.status}`;
    try {
      const payload = await response.json();
      if (payload?.detail) {
        if (typeof payload.detail === "string") {
          detail = payload.detail;
        } else if (Array.isArray(payload.detail)) {
          detail = payload.detail
            .map((item: unknown) => {
              if (typeof item === "string") return item;
              if (item && typeof item === "object" && "msg" in item) {
                return String(item.msg);
              }
              return JSON.stringify(item);
            })
            .join("; ");
        } else {
          detail = JSON.stringify(payload.detail);
        }
      }
    } catch {
      // ignore non-json error bodies
    }
    if (response.status === 401) {
      clearStoredAccessToken();
      window.dispatchEvent(new CustomEvent("app-access-expired"));
    }
    throw new Error(detail);
  }
  return response.json();
}

export const api = {
  getAccessStatus: () => request<AccessStatus>("/access/status"),
  login: (password: string) =>
    request<AccessLoginResponse>("/access/login", {
      method: "POST",
      body: JSON.stringify({ password })
    }),
  getHealth: () => request<HealthCheck>("/health", undefined, BACKEND_BASE),
  getHealthDetails: () => request<HealthDetails>("/health/details", undefined, BACKEND_BASE),
  getAccountDefaults: () => request<AccountDefaults>("/settings/account-defaults"),
  updateAccountDefaults: (payload: Record<string, unknown>) =>
    request<AccountDefaults>("/settings/account-defaults", {
      method: "PATCH",
      body: JSON.stringify(payload)
    }),
  listRuns: () => request<PipelineRunSummary[]>("/pipeline-runs"),
  createRun: (payload: Record<string, unknown>) =>
    request<PipelineRunDetail>("/pipeline-runs", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  getRun: (runId: string) => request<PipelineRunDetail>(`/pipeline-runs/${runId}`),
  resumeRun: (runId: string, reviewNotes = "", confirmPaidGeneration = false) =>
    request<PipelineRunDetail>(`/pipeline-runs/${runId}/resume`, {
      method: "POST",
      body: JSON.stringify({ review_notes: reviewNotes, confirm_paid_generation: confirmPaidGeneration })
    }),
  recheckRun: (runId: string, reviewNotes = "") =>
    request<PipelineRunDetail>(`/pipeline-runs/${runId}/recheck`, {
      method: "POST",
      body: JSON.stringify({ review_notes: reviewNotes })
    }),
  recheckStoryAdherence: (runId: string, reviewNotes = "") =>
    request<PipelineRunDetail>(`/pipeline-runs/${runId}/story-adherence/recheck`, {
      method: "POST",
      body: JSON.stringify({ review_notes: reviewNotes })
    }),
  submitStoryAdherenceHumanReview: (runId: string, decision: StoryAdherenceHumanDecision, notes = "") =>
    request<PipelineRunDetail>(`/pipeline-runs/${runId}/story-adherence/human-review`, {
      method: "POST",
      body: JSON.stringify({ decision, notes })
    }),
  createNarrationDraft: (runId: string, confirmPaidDraft = false) =>
    request<PipelineRunDetail>(`/pipeline-runs/${runId}/narration/draft`, {
      method: "POST",
      body: JSON.stringify({ confirm_paid_draft: confirmPaidDraft })
    }),
  regenerateNarrationDraft: (runId: string, confirmPaidDraft = false) =>
    request<PipelineRunDetail>(`/pipeline-runs/${runId}/narration/draft/regenerate`, {
      method: "POST",
      body: JSON.stringify({ confirm_paid_draft: confirmPaidDraft })
    }),
  patchNarrationDraft: (runId: string, payload: Record<string, unknown>) =>
    request<PipelineRunDetail>(`/pipeline-runs/${runId}/narration/draft`, {
      method: "PATCH",
      body: JSON.stringify(payload)
    }),
  createNarrationRender: (runId: string, payload: { confirm_paid_narration: boolean; confirm_unapproved_story?: boolean; voice?: string | null }) =>
    request<PipelineRunDetail>(`/pipeline-runs/${runId}/narration/render`, {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  recomposeNarrationRender: (runId: string, renderId: string) =>
    request<PipelineRunDetail>(`/pipeline-runs/${runId}/narration/renders/${renderId}/recompose`, {
      method: "POST"
    }),
  submitNarrationHumanReview: (runId: string, narrationRenderId: string, decision: NarrationHumanDecision, notes = "") =>
    request<PipelineRunDetail>(`/pipeline-runs/${runId}/narration/human-review`, {
      method: "POST",
      body: JSON.stringify({ narration_render_id: narrationRenderId, decision, notes })
    }),
  selectFinalAsset: (
    runId: string,
    payload: {
      source: "source_video" | "narration_render";
      narration_render_id?: string | null;
      confirm_change_after_posting?: boolean;
    },
  ) =>
    request<PipelineRunDetail>(`/pipeline-runs/${runId}/final-asset/select`, {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  cancelRun: (runId: string, reviewNotes = "") =>
    request<PipelineRunDetail>(`/pipeline-runs/${runId}/cancel`, {
      method: "POST",
      body: JSON.stringify({ review_notes: reviewNotes })
    }),
  patchScript: (runId: string, patch: Record<string, unknown>) =>
    request<PipelineRunDetail>(`/pipeline-runs/${runId}/script`, {
      method: "PATCH",
      body: JSON.stringify(patch)
    }),
  patchStoryboard: (runId: string, patch: Record<string, unknown>) =>
    request<PipelineRunDetail>(`/pipeline-runs/${runId}/storyboard`, {
      method: "PATCH",
      body: JSON.stringify(patch)
    }),
  patchIdea: (runId: string, patch: Record<string, unknown>) =>
    request<PipelineRunDetail>(`/pipeline-runs/${runId}/idea`, {
      method: "PATCH",
      body: JSON.stringify(patch)
    }),
  patchReviewConfig: (runId: string, patch: Record<string, unknown>) =>
    request<PipelineRunDetail>(`/pipeline-runs/${runId}/review-config`, {
      method: "PATCH",
      body: JSON.stringify(patch)
    }),
  regenerateRunText: (runId: string, reviewNotes = "") =>
    request<PipelineRunDetail>(`/pipeline-runs/${runId}/regenerate-text`, {
      method: "POST",
      body: JSON.stringify({ review_notes: reviewNotes })
    }),
  runPromptAction: (runId: string, action: "improve" | "shorten") =>
    request<PipelineRunDetail>(`/pipeline-runs/${runId}/prompt-actions`, {
      method: "POST",
      body: JSON.stringify({ action })
    }),
  listIdeaQueue: () => request<IdeaQueueItem[]>("/idea-queue"),
  createIdeaQueueItem: (payload: Record<string, unknown>) =>
    request<IdeaQueueItem>("/idea-queue", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  patchIdeaQueueItem: (itemId: string, payload: Record<string, unknown>) =>
    request<IdeaQueueItem>(`/idea-queue/${itemId}`, {
      method: "PATCH",
      body: JSON.stringify(payload)
    }),
  batchUpdateIdeaQueueItems: (payload: Record<string, unknown>) =>
    request<IdeaQueueItem[]>("/idea-queue/batch-update", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  scoreIdeaQueueItems: (itemIds: string[]) =>
    request<IdeaScore[]>("/idea-queue/score", {
      method: "POST",
      body: JSON.stringify({ item_ids: itemIds })
    }),
  archiveIdeaQueueItem: (itemId: string) =>
    request<IdeaQueueItem>(`/idea-queue/${itemId}/archive`, {
      method: "POST"
    }),
  generateRunFromIdeaQueueItem: (itemId: string) =>
    request<{ idea_queue_item: Record<string, unknown>; pipeline_run: Record<string, unknown> }>(`/idea-queue/${itemId}/generate-run`, {
      method: "POST"
    }),
  listAssetLibrary: (params?: Record<string, string>) => {
    const search = new URLSearchParams(params ?? {});
    const suffix = search.toString() ? `?${search.toString()}` : "";
    return request<AssetLibraryItem[]>(`/asset-library${suffix}`);
  },
  getAssetLibraryItem: (runId: string) => request<AssetLibraryDetail>(`/asset-library/${runId}`),
  getAssetExportPack: (runId: string) => request<AssetExportPack>(`/asset-library/${runId}/export-pack`),
  updateAssetManualPosting: (runId: string, payload: Record<string, unknown>) =>
    request<AssetExportPack>(`/asset-library/${runId}/manual-posting`, {
      method: "PATCH",
      body: JSON.stringify(payload)
    }),
  getRunPerformance: (runId: string) => request<RunPerformance>(`/pipeline-runs/${runId}/performance`),
  createPlatformPost: (runId: string, payload: Record<string, unknown>) =>
    request<PlatformPost>(`/pipeline-runs/${runId}/performance/posts`, {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  updatePlatformPost: (runId: string, postId: string, payload: Record<string, unknown>) =>
    request<PlatformPost>(`/pipeline-runs/${runId}/performance/posts/${postId}`, {
      method: "PATCH",
      body: JSON.stringify(payload)
    }),
  addPerformanceSnapshot: (runId: string, postId: string, payload: Record<string, unknown>) =>
    request<PerformanceSnapshot>(`/pipeline-runs/${runId}/performance/posts/${postId}/snapshots`, {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  selectPerformanceWinner: (runId: string, platformPostId: string) =>
    request<RunPerformance>(`/pipeline-runs/${runId}/performance/winner`, {
      method: "PUT",
      body: JSON.stringify({ platform_post_id: platformPostId })
    }),
  clearPerformanceWinner: (runId: string) =>
    request<RunPerformance>(`/pipeline-runs/${runId}/performance/winner`, {
      method: "DELETE"
    }),
  createPerformanceLearning: (runId: string, payload: PerformanceLearningCreatePayload) =>
    request<RunPerformance>(`/pipeline-runs/${runId}/performance/learnings`, {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  updatePerformanceLearning: (runId: string, learningId: string, payload: PerformanceLearningPatchPayload) =>
    request<RunPerformance>(`/pipeline-runs/${runId}/performance/learnings/${learningId}`, {
      method: "PATCH",
      body: JSON.stringify(payload)
    }),
  archivePerformanceLearning: (runId: string, learningId: string) =>
    request<RunPerformance>(`/pipeline-runs/${runId}/performance/learnings/${learningId}/archive`, {
      method: "POST"
    }),
  listSocialConnections: () => request<{ items: SocialConnectionSummary[] }>("/social-connections"),
  authorizeYouTubeConnection: (returnPath?: string) =>
    request<SocialAuthorizeResponse>("/social-connections/youtube/authorize", {
      method: "POST",
      body: JSON.stringify({ return_path: returnPath ?? null })
    }),
  getLatestPublicationJobForRun: (runId: string) =>
    request<PublicationJob>(`/pipeline-runs/${runId}/publication-jobs/latest`),
  getPublicationJob: (jobId: string) =>
    request<PublicationJob>(`/publication-jobs/${jobId}`),
  createPublicationJob: (runId: string, payload: PublicationJobDraftPayload) =>
    request<{ job: PublicationJob }>(`/pipeline-runs/${runId}/publication-jobs`, {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  approvePublicationJob: (jobId: string) =>
    request<{ job: PublicationJob }>(`/publication-jobs/${jobId}/approve`, {
      method: "POST"
    }),
  dispatchPublicationJob: (jobId: string) =>
    request<{ job: PublicationJob }>(`/publication-jobs/${jobId}/dispatch`, {
      method: "POST"
    }),
  cancelPublicationJob: (jobId: string) =>
    request<{ job: PublicationJob }>(`/publication-jobs/${jobId}/cancel`, {
      method: "POST"
    }),
  retryPublicationTarget: (targetId: string) =>
    request<{ job: PublicationJob }>(`/publication-targets/${targetId}/retry`, {
      method: "POST"
    }),
  reconcilePublicationTarget: (targetId: string) =>
    request<{ job: PublicationJob }>(`/publication-targets/${targetId}/reconcile`, {
      method: "POST"
    }),
};
