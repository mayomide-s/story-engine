export type BatchProductionStatus =
  | "idea"
  | "selected"
  | "in_production"
  | "generated"
  | "ready_to_post"
  | "posted";

export type BatchStatus = "draft" | "active" | "completed";

export type BatchTargetPlatform = "all" | "tiktok" | "instagram_reels" | "youtube_shorts";

export type BatchContentAngle =
  | "funny metaphor"
  | "visual explainer"
  | "common mistake"
  | "interview prep"
  | "debugging tip"
  | "web dev concept";

export type BatchTopicIdea = {
  id: string;
  topic: string;
  hookIdea: string;
  visualMetaphor: string;
  audienceLevel: string;
  platformFit: BatchTargetPlatform;
  estimatedDifficulty: string;
  hookScore: number;
  productionStatus: BatchProductionStatus;
  notes: string;
};

export type ContentBatch = {
  id: string;
  batchName: string;
  batchGoal: string;
  targetPlatform: BatchTargetPlatform;
  targetAudience: string;
  contentAngle: BatchContentAngle;
  ideaCount: number;
  batchStatus: BatchStatus;
  topics: BatchTopicIdea[];
  createdAt: string;
  updatedAt: string;
};

export type DashboardPrefill = {
  topic: string;
  audienceLevel?: string;
  contentFormat?: string;
};

export const BATCH_PLANNER_STORAGE_KEY = "story-engine-batch-planner";
export const DASHBOARD_PREFILL_STORAGE_KEY = "story-engine-dashboard-prefill";

export const BATCH_TARGET_PLATFORMS: BatchTargetPlatform[] = ["all", "tiktok", "instagram_reels", "youtube_shorts"];
export const BATCH_CONTENT_ANGLES: BatchContentAngle[] = [
  "funny metaphor",
  "visual explainer",
  "common mistake",
  "interview prep",
  "debugging tip",
  "web dev concept",
];
export const BATCH_STATUSES: BatchStatus[] = ["draft", "active", "completed"];
export const BATCH_PRODUCTION_STATUSES: BatchProductionStatus[] = [
  "idea",
  "selected",
  "in_production",
  "generated",
  "ready_to_post",
  "posted",
];

export function formatBatchStatus(value: string) {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function loadBatches() {
  if (typeof window === "undefined") {
    return [] as ContentBatch[];
  }
  try {
    const raw = window.localStorage.getItem(BATCH_PLANNER_STORAGE_KEY);
    return raw ? (JSON.parse(raw) as ContentBatch[]) : [];
  } catch {
    return [] as ContentBatch[];
  }
}

export function saveBatches(batches: ContentBatch[]) {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(BATCH_PLANNER_STORAGE_KEY, JSON.stringify(batches));
}

export function saveDashboardPrefill(prefill: DashboardPrefill) {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(DASHBOARD_PREFILL_STORAGE_KEY, JSON.stringify(prefill));
}

export function loadDashboardPrefill() {
  if (typeof window === "undefined") {
    return null as DashboardPrefill | null;
  }
  try {
    const raw = window.localStorage.getItem(DASHBOARD_PREFILL_STORAGE_KEY);
    return raw ? (JSON.parse(raw) as DashboardPrefill) : null;
  } catch {
    return null as DashboardPrefill | null;
  }
}

export function clearDashboardPrefill() {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.removeItem(DASHBOARD_PREFILL_STORAGE_KEY);
}

export function createId(prefix: string) {
  return `${prefix}-${Math.random().toString(36).slice(2, 10)}`;
}

export function createStarterTopics(): BatchTopicIdea[] {
  return [
    {
      id: createId("topic"),
      topic: "JWT explained as a nightclub wristband",
      hookIdea: "Why does one tiny token decide whether you get in or get kicked out?",
      visualMetaphor: "A glowing wristband that grants access to different club zones.",
      audienceLevel: "beginner",
      platformFit: "tiktok",
      estimatedDifficulty: "easy",
      hookScore: 4,
      productionStatus: "idea",
      notes: "",
    },
    {
      id: createId("topic"),
      topic: "SQL joins explained as seating plans",
      hookIdea: "Why joining tables feels like figuring out who sits next to who at a wedding.",
      visualMetaphor: "Guests, place cards, and tables combining in different ways.",
      audienceLevel: "beginner",
      platformFit: "youtube_shorts",
      estimatedDifficulty: "medium",
      hookScore: 4,
      productionStatus: "idea",
      notes: "",
    },
    {
      id: createId("topic"),
      topic: "CORS explained as a bouncer checking guest lists",
      hookIdea: "The browser is not being rude. It is checking who is allowed in.",
      visualMetaphor: "A club entrance with a bouncer, guest list, and color-coded passes.",
      audienceLevel: "beginner",
      platformFit: "instagram_reels",
      estimatedDifficulty: "easy",
      hookScore: 5,
      productionStatus: "idea",
      notes: "",
    },
    {
      id: createId("topic"),
      topic: "APIs explained as restaurant waiters",
      hookIdea: "Your frontend is not cooking. It is placing an order.",
      visualMetaphor: "A waiter carrying requests to a kitchen and returning dishes.",
      audienceLevel: "beginner",
      platformFit: "all",
      estimatedDifficulty: "easy",
      hookScore: 5,
      productionStatus: "idea",
      notes: "",
    },
    {
      id: createId("topic"),
      topic: "Git branches explained as alternate timelines",
      hookIdea: "What if every branch is a new version of reality?",
      visualMetaphor: "Characters jumping between glowing timeline paths.",
      audienceLevel: "intermediate",
      platformFit: "tiktok",
      estimatedDifficulty: "medium",
      hookScore: 4,
      productionStatus: "idea",
      notes: "",
    },
    {
      id: createId("topic"),
      topic: "Webhooks explained as doorbells",
      hookIdea: "Polling keeps checking the window. Webhooks ring the bell when it matters.",
      visualMetaphor: "A visitor pressing a doorbell instead of someone peeking outside repeatedly.",
      audienceLevel: "beginner",
      platformFit: "instagram_reels",
      estimatedDifficulty: "easy",
      hookScore: 4,
      productionStatus: "idea",
      notes: "",
    },
    {
      id: createId("topic"),
      topic: "Caching explained as keeping snacks nearby",
      hookIdea: "Why walk to the kitchen every time if the snack is already on your desk?",
      visualMetaphor: "A runner choosing between a nearby snack drawer and a far kitchen.",
      audienceLevel: "beginner",
      platformFit: "all",
      estimatedDifficulty: "easy",
      hookScore: 3,
      productionStatus: "idea",
      notes: "",
    },
    {
      id: createId("topic"),
      topic: "Rate limits explained as nightclub capacity",
      hookIdea: "The app is not broken. The room is full.",
      visualMetaphor: "A crowd stopped at the door once capacity is hit.",
      audienceLevel: "beginner",
      platformFit: "tiktok",
      estimatedDifficulty: "easy",
      hookScore: 4,
      productionStatus: "idea",
      notes: "",
    },
    {
      id: createId("topic"),
      topic: "Promises explained as food delivery tracking",
      hookIdea: "Pending, fulfilled, rejected, just like waiting for your order.",
      visualMetaphor: "A delivery app progress bar with the meal arriving or failing.",
      audienceLevel: "beginner",
      platformFit: "youtube_shorts",
      estimatedDifficulty: "easy",
      hookScore: 4,
      productionStatus: "idea",
      notes: "",
    },
    {
      id: createId("topic"),
      topic: "DNS explained as a phonebook",
      hookIdea: "You remember the name. DNS remembers the number.",
      visualMetaphor: "A character flipping through a phonebook to connect a call.",
      audienceLevel: "beginner",
      platformFit: "all",
      estimatedDifficulty: "easy",
      hookScore: 3,
      productionStatus: "idea",
      notes: "",
    },
  ];
}

export function createDefaultBatch(): ContentBatch {
  const now = new Date().toISOString();
  return {
    id: createId("batch"),
    batchName: "July coding batch",
    batchGoal: "Pick strong coding explainers for the next production run.",
    targetPlatform: "all",
    targetAudience: "beginner",
    contentAngle: "funny metaphor",
    ideaCount: 10,
    batchStatus: "draft",
    topics: createStarterTopics(),
    createdAt: now,
    updatedAt: now,
  };
}
