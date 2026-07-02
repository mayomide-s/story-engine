const RUN_STATUS_LABELS: Record<string, string> = {
  queued: "Queued",
  running: "Running",
  awaiting_review: "Awaiting review",
  needs_review: "Needs review",
  completed: "Completed",
  failed: "Failed",
  cancelled: "Cancelled",
};

const STAGE_LABELS: Record<string, string> = {
  idea_generation: "Idea",
  script_generation: "Script",
  storyboard_generation: "Storyboard",
  video_prompt_build: "Preparing video prompt",
  video_generation_submit: "Submitting video",
  video_generation_polling: "Generating video",
  asset_upload: "Saving assets",
  quality_check: "Quality check",
  manual_package_creation: "Preparing posting package",
  completed: "Completed",
};

const VIDEO_STATUS_LABELS: Record<string, string> = {
  queued: "Queued",
  generating: "Generating",
  submitting: "Submitting",
  completed: "Completed",
  failed: "Failed",
  pending_review: "Pending review",
  approved: "Approved",
  rejected: "Rejected",
};

export function formatRunStatus(value: string | null | undefined) {
  return RUN_STATUS_LABELS[value ?? ""] ?? toReadableLabel(value);
}

export function formatStage(value: string | null | undefined) {
  return STAGE_LABELS[value ?? ""] ?? toReadableLabel(value);
}

export function formatVideoStatus(value: string | null | undefined) {
  return VIDEO_STATUS_LABELS[value ?? ""] ?? toReadableLabel(value);
}

export function formatProvider(value: string | null | undefined) {
  if (!value) {
    return "Not started";
  }
  if (value === "mock") {
    return "Mock";
  }
  if (value === "runway") {
    return "Runway";
  }
  return toReadableLabel(value);
}

export function toReadableLabel(value: string | null | undefined) {
  if (!value) {
    return "Not started";
  }
  return value
    .split(/[_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}
