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
  target_platform: string;
  priority: string;
  status: string;
  notes?: string | null;
  planned_date?: string | null;
  pipeline_run_id?: string | null;
  created_at: string;
  updated_at: string;
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

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options
  });
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
  listRuns: () => request<PipelineRunSummary[]>("/pipeline-runs"),
  createRun: (topic: string, autoMode = false, stylePreset = "clean_3d_cartoon") =>
    request<PipelineRunDetail>("/pipeline-runs", {
      method: "POST",
      body: JSON.stringify({ topic, auto_mode: autoMode, style_preset: stylePreset })
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
};
