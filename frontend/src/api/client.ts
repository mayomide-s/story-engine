export type PipelineRunSummary = {
  id: string;
  topic: string;
  status: string;
  current_stage: string;
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
  createRun: (topic: string, autoMode = false) =>
    request<PipelineRunDetail>("/pipeline-runs", {
      method: "POST",
      body: JSON.stringify({ topic, auto_mode: autoMode })
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
    })
};
