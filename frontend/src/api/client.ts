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
};

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
  target_platform?: string | null;
  caption?: string | null;
  prompt_text?: string | null;
  manual_posting_status?: string | null;
};

export type AssetLibraryDetail = {
  pipeline_run: Record<string, unknown>;
  video: Record<string, unknown>;
  video_asset: Record<string, unknown>;
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
  target_platform?: string | null;
  linked_pipeline_run_id: string;
  linked_idea_queue_item_id?: string | null;
  platform_sections: {
    tiktok: ExportPlatformSection;
    instagram_reels: ExportPlatformSection;
    youtube_shorts: ExportPlatformSection;
  };
};

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api";
const BACKEND_BASE = API_BASE.replace(/\/api\/?$/, "");

export type HealthCheck = {
  status: string;
};

export type HealthDetails = {
  status: string;
  backend_reachable: boolean;
  environment: string;
  video_provider: string;
  storage_provider: string;
  runway_mode_enabled: boolean;
  r2_public_base_url_configured: boolean;
  checks: Record<string, { status: string; detail: string; errors?: string[]; mode?: string; provider?: string; sdk_version?: string | null }>;
};

async function request<T>(path: string, options?: RequestInit, baseUrl = API_BASE): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${baseUrl}${path}`, {
      headers: { "Content-Type": "application/json", ...(options?.headers ?? {}) },
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
        detail = String(payload.detail);
      }
    } catch {
      // ignore non-json error bodies
    }
    throw new Error(detail);
  }
  return response.json();
}

export const api = {
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
  resumeRun: (runId: string, reviewNotes = "") =>
    request<PipelineRunDetail>(`/pipeline-runs/${runId}/resume`, {
      method: "POST",
      body: JSON.stringify({ review_notes: reviewNotes })
    }),
  recheckRun: (runId: string, reviewNotes = "") =>
    request<PipelineRunDetail>(`/pipeline-runs/${runId}/recheck`, {
      method: "POST",
      body: JSON.stringify({ review_notes: reviewNotes })
    }),
  cancelRun: (runId: string, reviewNotes = "") =>
    request<PipelineRunDetail>(`/pipeline-runs/${runId}/cancel`, {
      method: "POST",
      body: JSON.stringify({ review_notes: reviewNotes })
    }),
  patchScript: (runId: string, scriptJson: Record<string, unknown>) =>
    request<PipelineRunDetail>(`/pipeline-runs/${runId}/script`, {
      method: "PATCH",
      body: JSON.stringify({ script_json: scriptJson })
    }),
  patchStoryboard: (runId: string, framesJson: Record<string, unknown>) =>
    request<PipelineRunDetail>(`/pipeline-runs/${runId}/storyboard`, {
      method: "PATCH",
      body: JSON.stringify({ frames_json: framesJson })
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
};
