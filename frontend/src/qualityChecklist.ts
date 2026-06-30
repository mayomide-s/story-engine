export function normalizeQualityChecklist(
  rawChecks: Record<string, unknown>,
  providerName: string | null | undefined,
): Array<[string, unknown]> {
  const normalized = { ...rawChecks };
  const isRunway = providerName === "runway";

  if (isRunway) {
    delete normalized.end_tag_present;
    if (!("branding_handled_separately" in normalized)) {
      normalized.branding_handled_separately = Boolean(
        normalized.video_exists &&
        normalized.aspect_ratio_9_16 &&
        normalized.duration_in_range &&
        normalized.provider_generated_video,
      );
    }
  }

  return Object.entries(normalized).filter(([key]) => !key.endsWith("_seconds"));
}
