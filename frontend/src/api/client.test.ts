import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api, clearClientAccessState } from "./client";


describe("api client authentication transport", () => {
  beforeEach(() => {
    clearClientAccessState();
    window.localStorage.clear();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    clearClientAccessState();
    vi.restoreAllMocks();
  });

  it("uses credentials include for login and does not persist auth tokens in storage", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          auth_enabled: true,
          authenticated: true,
          account_deleted: false,
          csrf_token: "csrf-login-token",
          session_expires_at: "2026-07-15T00:00:00Z",
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await api.login("open-sesame");

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [, options] = fetchMock.mock.calls[0];
    expect(options.credentials).toBe("include");
    expect(new Headers(options.headers).has("Authorization")).toBe(false);
    expect(window.localStorage.getItem("story-engine-access-token")).toBeNull();
  });

  it("sends the csrf header for authenticated mutating requests", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            auth_enabled: true,
            authenticated: true,
            account_deleted: false,
            csrf_token: "csrf-login-token",
            session_expires_at: "2026-07-15T00:00:00Z",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            pipeline_run: { id: "run-1", status: "awaiting_review" },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      );
    vi.stubGlobal("fetch", fetchMock);

    await api.login("open-sesame");
    await api.createRun({ topic: "CORS", auto_mode: false });

    expect(fetchMock).toHaveBeenCalledTimes(2);
    const [, requestOptions] = fetchMock.mock.calls[1];
    const headers = new Headers(requestOptions.headers);
    expect(requestOptions.credentials).toBe("include");
    expect(headers.get("X-CSRF-Token")).toBe("csrf-login-token");
  });
});
