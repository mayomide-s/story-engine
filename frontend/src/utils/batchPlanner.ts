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
  isWinner?: boolean;
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
  sourceBatchName?: string;
};

export type DashboardPrefillCapture = {
  prefill: DashboardPrefill | null;
  shouldClearStorage: boolean;
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

export const SPRINT_1_BATCH_NAME = "Sprint 1 - Coding Metaphors";

const SPRINT_1_SELECTED_TOPICS = new Set([
  "JWT explained as a nightclub wristband",
  "SQL joins explained as seating plans",
  "APIs explained as restaurant waiters",
  "Git branches explained as alternate timelines",
  "Rate limits explained as nightclub capacity",
]);

const SPRINT_1_TOPIC_IDS: Record<string, string> = {
  "JWT explained as a nightclub wristband": "sprint1-jwt-nightclub-wristband",
  "SQL joins explained as seating plans": "sprint1-sql-joins-seating-plans",
  "APIs explained as restaurant waiters": "sprint1-apis-restaurant-waiters",
  "Git branches explained as alternate timelines": "sprint1-git-branches-alternate-timelines",
  "Webhooks explained as doorbells": "sprint1-webhooks-doorbells",
  "Caching explained as keeping snacks nearby": "sprint1-caching-snacks-nearby",
  "Rate limits explained as nightclub capacity": "sprint1-rate-limits-nightclub-capacity",
  "Promises explained as food delivery tracking": "sprint1-promises-food-delivery-tracking",
  "DNS explained as a phonebook": "sprint1-dns-phonebook",
  "Environment variables explained as secret notes": "sprint1-env-vars-secret-notes",
};

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

function normalizeOptionalString(value: unknown) {
  if (typeof value !== "string") {
    return null;
  }
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function parseDashboardPrefill(raw: string): DashboardPrefill | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }

  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    return null;
  }

  const topic = normalizeOptionalString((parsed as Record<string, unknown>).topic);
  if (!topic) {
    return null;
  }

  const audienceLevel = normalizeOptionalString((parsed as Record<string, unknown>).audienceLevel);
  const contentFormat = normalizeOptionalString((parsed as Record<string, unknown>).contentFormat);
  const sourceBatchName = normalizeOptionalString((parsed as Record<string, unknown>).sourceBatchName);

  return {
    topic,
    ...(audienceLevel ? { audienceLevel } : {}),
    ...(contentFormat ? { contentFormat } : {}),
    ...(sourceBatchName ? { sourceBatchName } : {}),
  };
}

export function readDashboardPrefillCapture() {
  if (typeof window === "undefined") {
    return { prefill: null, shouldClearStorage: false } as DashboardPrefillCapture;
  }

  const raw = window.localStorage.getItem(DASHBOARD_PREFILL_STORAGE_KEY);
  if (raw === null) {
    return { prefill: null, shouldClearStorage: false } as DashboardPrefillCapture;
  }

  return {
    prefill: parseDashboardPrefill(raw),
    shouldClearStorage: true,
  } as DashboardPrefillCapture;
}

export function loadDashboardPrefill() {
  return readDashboardPrefillCapture().prefill;
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

export function createSprint1Topics(): BatchTopicIdea[] {
  const topics: BatchTopicIdea[] = [
    {
      id: SPRINT_1_TOPIC_IDS["JWT explained as a nightclub wristband"],
      topic: "JWT explained as a nightclub wristband",
      hookIdea: "One tiny band decides which doors open and which stay closed.",
      visualMetaphor: "A bouncer scanning wristbands for general access, VIP, and backstage zones.",
      audienceLevel: "beginner",
      platformFit: "all",
      estimatedDifficulty: "easy",
      hookScore: 5,
      productionStatus: "selected",
      notes: "",
    },
    {
      id: SPRINT_1_TOPIC_IDS["SQL joins explained as seating plans"],
      topic: "SQL joins explained as seating plans",
      hookIdea: "Joining tables feels a lot like figuring out who sits where at an event.",
      visualMetaphor: "Guests, name cards, and tables connecting across seating charts.",
      audienceLevel: "beginner",
      platformFit: "all",
      estimatedDifficulty: "easy",
      hookScore: 5,
      productionStatus: "selected",
      notes: "",
    },
    {
      id: SPRINT_1_TOPIC_IDS["APIs explained as restaurant waiters"],
      topic: "APIs explained as restaurant waiters",
      hookIdea: "Your app is not cooking the food. It is placing the order.",
      visualMetaphor: "A waiter passing requests from diners to the kitchen and back.",
      audienceLevel: "beginner",
      platformFit: "all",
      estimatedDifficulty: "easy",
      hookScore: 5,
      productionStatus: "selected",
      notes: "",
    },
    {
      id: SPRINT_1_TOPIC_IDS["Git branches explained as alternate timelines"],
      topic: "Git branches explained as alternate timelines",
      hookIdea: "Every branch is a different version of reality until one becomes canon.",
      visualMetaphor: "A developer hopping between glowing timeline splits.",
      audienceLevel: "beginner",
      platformFit: "all",
      estimatedDifficulty: "medium",
      hookScore: 5,
      productionStatus: "selected",
      notes: "",
    },
    {
      id: SPRINT_1_TOPIC_IDS["Webhooks explained as doorbells"],
      topic: "Webhooks explained as doorbells",
      hookIdea: "Stop checking the window. Let the event ring the bell.",
      visualMetaphor: "A house with repeated peeking versus a doorbell notification.",
      audienceLevel: "beginner",
      platformFit: "all",
      estimatedDifficulty: "easy",
      hookScore: 4,
      productionStatus: "idea",
      notes: "",
    },
    {
      id: SPRINT_1_TOPIC_IDS["Caching explained as keeping snacks nearby"],
      topic: "Caching explained as keeping snacks nearby",
      hookIdea: "Why walk across the house every time when the snack can stay on your desk?",
      visualMetaphor: "A snack drawer beside a desk versus repeated kitchen trips.",
      audienceLevel: "beginner",
      platformFit: "all",
      estimatedDifficulty: "easy",
      hookScore: 4,
      productionStatus: "idea",
      notes: "",
    },
    {
      id: SPRINT_1_TOPIC_IDS["Rate limits explained as nightclub capacity"],
      topic: "Rate limits explained as nightclub capacity",
      hookIdea: "The app is not broken. The room is just full.",
      visualMetaphor: "A venue hitting max capacity with a line still outside.",
      audienceLevel: "beginner",
      platformFit: "all",
      estimatedDifficulty: "easy",
      hookScore: 5,
      productionStatus: "selected",
      notes: "",
    },
    {
      id: SPRINT_1_TOPIC_IDS["Promises explained as food delivery tracking"],
      topic: "Promises explained as food delivery tracking",
      hookIdea: "Pending, fulfilled, rejected. It is basically waiting on your takeaway.",
      visualMetaphor: "A delivery tracker moving from ordered to delivered or cancelled.",
      audienceLevel: "beginner",
      platformFit: "all",
      estimatedDifficulty: "easy",
      hookScore: 4,
      productionStatus: "idea",
      notes: "",
    },
    {
      id: SPRINT_1_TOPIC_IDS["DNS explained as a phonebook"],
      topic: "DNS explained as a phonebook",
      hookIdea: "You remember the name. DNS remembers the number.",
      visualMetaphor: "A person finding a contact in a phonebook to place a call.",
      audienceLevel: "beginner",
      platformFit: "all",
      estimatedDifficulty: "easy",
      hookScore: 4,
      productionStatus: "idea",
      notes: "",
    },
    {
      id: SPRINT_1_TOPIC_IDS["Environment variables explained as secret notes"],
      topic: "Environment variables explained as secret notes",
      hookIdea: "Important app secrets should stay hidden, not written on the whiteboard.",
      visualMetaphor: "Folded private notes handed only to the right people backstage.",
      audienceLevel: "beginner",
      platformFit: "all",
      estimatedDifficulty: "easy",
      hookScore: 4,
      productionStatus: "idea",
      notes: "",
    },
  ];

  return topics.map((topic) => ({
    ...topic,
    productionStatus: SPRINT_1_SELECTED_TOPICS.has(topic.topic) ? "selected" : "idea",
  }));
}

export function createSprint1Batch(): ContentBatch {
  const now = new Date().toISOString();
  return {
    id: createId("batch"),
    batchName: SPRINT_1_BATCH_NAME,
    batchGoal: "Test which beginner coding metaphors get the best short-form engagement",
    targetPlatform: "all",
    targetAudience: "beginner",
    contentAngle: "funny metaphor",
    ideaCount: 10,
    batchStatus: "active",
    topics: createSprint1Topics(),
    createdAt: now,
    updatedAt: now,
  };
}

export function upsertSprint1Batch(batches: ContentBatch[]) {
  const existingIndex = batches.findIndex((batch) => batch.batchName === SPRINT_1_BATCH_NAME);
  if (existingIndex === -1) {
    const sprint = createSprint1Batch();
    return { batches: [sprint, ...batches], batchId: sprint.id };
  }
  return { batches, batchId: batches[existingIndex].id };
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
