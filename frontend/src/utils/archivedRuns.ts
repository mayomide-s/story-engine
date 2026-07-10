const ARCHIVED_RUNS_STORAGE_KEY = "story-engine.archived-runs";

function canUseStorage() {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

export function getArchivedRunsStorageKey() {
  return ARCHIVED_RUNS_STORAGE_KEY;
}

export function loadArchivedRunIds() {
  if (!canUseStorage()) {
    return [] as string[];
  }
  try {
    const raw = window.localStorage.getItem(ARCHIVED_RUNS_STORAGE_KEY);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed.filter((value): value is string => typeof value === "string");
  } catch {
    return [];
  }
}

export function saveArchivedRunIds(runIds: string[]) {
  if (!canUseStorage()) {
    return;
  }
  const uniqueRunIds = Array.from(new Set(runIds));
  window.localStorage.setItem(ARCHIVED_RUNS_STORAGE_KEY, JSON.stringify(uniqueRunIds));
}
