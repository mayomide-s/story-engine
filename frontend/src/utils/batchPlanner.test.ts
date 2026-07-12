import { describe, expect, it } from "vitest";

import {
  DASHBOARD_PREFILL_STORAGE_KEY,
  readDashboardPrefillCapture,
} from "./batchPlanner";

describe("readDashboardPrefillCapture", () => {
  it("returns a valid complete handoff and trims whitespace", () => {
    window.localStorage.setItem(
      DASHBOARD_PREFILL_STORAGE_KEY,
      JSON.stringify({
        topic: "  APIs explained as restaurant waiters  ",
        audienceLevel: " beginner ",
        contentFormat: " quick concept explainer ",
        sourceBatchName: " Sprint 1 ",
      }),
    );

    expect(readDashboardPrefillCapture()).toEqual({
      prefill: {
        topic: "APIs explained as restaurant waiters",
        audienceLevel: "beginner",
        contentFormat: "quick concept explainer",
        sourceBatchName: "Sprint 1",
      },
      shouldClearStorage: true,
    });
  });

  it("accepts a topic-only handoff", () => {
    window.localStorage.setItem(
      DASHBOARD_PREFILL_STORAGE_KEY,
      JSON.stringify({ topic: "JWT explained as a nightclub wristband" }),
    );

    expect(readDashboardPrefillCapture()).toEqual({
      prefill: {
        topic: "JWT explained as a nightclub wristband",
      },
      shouldClearStorage: true,
    });
  });

  it("returns null for malformed JSON without throwing", () => {
    window.localStorage.setItem(DASHBOARD_PREFILL_STORAGE_KEY, "{bad-json");

    expect(readDashboardPrefillCapture()).toEqual({
      prefill: null,
      shouldClearStorage: true,
    });
  });

  it("rejects arrays, missing topics, blank topics, and invalid optional fields", () => {
    window.localStorage.setItem(DASHBOARD_PREFILL_STORAGE_KEY, JSON.stringify([]));
    expect(readDashboardPrefillCapture()).toEqual({
      prefill: null,
      shouldClearStorage: true,
    });

    window.localStorage.setItem(
      DASHBOARD_PREFILL_STORAGE_KEY,
      JSON.stringify({ audienceLevel: "beginner" }),
    );
    expect(readDashboardPrefillCapture()).toEqual({
      prefill: null,
      shouldClearStorage: true,
    });

    window.localStorage.setItem(
      DASHBOARD_PREFILL_STORAGE_KEY,
      JSON.stringify({
        topic: "   ",
        audienceLevel: 3,
        contentFormat: ["coding metaphor"],
        sourceBatchName: null,
      }),
    );
    expect(readDashboardPrefillCapture()).toEqual({
      prefill: null,
      shouldClearStorage: true,
    });
  });

  it("drops invalid optional fields while preserving a valid topic", () => {
    window.localStorage.setItem(
      DASHBOARD_PREFILL_STORAGE_KEY,
      JSON.stringify({
        topic: "Rate limits explained as nightclub capacity",
        audienceLevel: "  ",
        contentFormat: 99,
        sourceBatchName: { bad: true },
      }),
    );

    expect(readDashboardPrefillCapture()).toEqual({
      prefill: {
        topic: "Rate limits explained as nightclub capacity",
      },
      shouldClearStorage: true,
    });
  });

  it("reports no handoff when the storage key is absent", () => {
    expect(readDashboardPrefillCapture()).toEqual({
      prefill: null,
      shouldClearStorage: false,
    });
  });
});
