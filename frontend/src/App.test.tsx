import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { api } from "./api/client";

vi.mock("./components/EnvironmentStatusPanel", () => ({
  EnvironmentStatusPanel: () => <div data-testid="environment-panel" />,
}));

vi.mock("./pages/Dashboard", () => ({
  DashboardPage: () => <div>Dashboard</div>,
}));

vi.mock("./pages/AssetLibrary", () => ({
  AssetLibraryPage: () => <div>Asset Library</div>,
}));

vi.mock("./pages/ContentOps", () => ({
  ContentOpsPage: () => <div>Content Ops</div>,
}));

vi.mock("./pages/BatchPlanner", () => ({
  BatchPlannerPage: () => <div>Batch Planner</div>,
}));

vi.mock("./pages/IdeaQueue", () => ({
  IdeaQueuePage: () => <div>Idea Queue</div>,
}));

vi.mock("./pages/Ideas", () => ({
  IdeasPage: () => <div>Ideas</div>,
}));

vi.mock("./pages/Settings", () => ({
  SettingsPage: () => <div>Settings</div>,
}));

vi.mock("./pages/VideoReview", () => ({
  VideoReviewPage: () => <div>Video Review</div>,
}));

vi.mock("./pages/Performance", () => ({
  PerformancePage: () => <div>Performance</div>,
}));

function renderApp(route: string) {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <App />
    </MemoryRouter>,
  );
}

describe("App public routes", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the public homepage without requesting private access status", async () => {
    const accessStatusSpy = vi.spyOn(api, "getAccessStatus");

    renderApp("/");

    await screen.findByRole("heading", {
      name: /create, review, and approve short-form videos before they publish/i,
    });

    expect(accessStatusSpy).not.toHaveBeenCalled();
    expect(screen.getAllByText(/Operated by Mayo Soremekun/i).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: "Open Story Engine" })[0]).toHaveAttribute("href", "/app");
    expect(screen.getByRole("link", { name: "Contact Support" })).toHaveAttribute(
      "href",
      "mailto:mayomide.sore@outlook.com",
    );
  });

  it("renders the privacy page directly with retention and YouTube disconnect guidance", async () => {
    const accessStatusSpy = vi.spyOn(api, "getAccessStatus");

    renderApp("/privacy");

    await screen.findByRole("heading", { name: "Story Engine Privacy Policy" });

    expect(accessStatusSpy).not.toHaveBeenCalled();
    expect(screen.getAllByText(/Operational draft/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/OAuth tokens are encrypted at rest/i)).toBeInTheDocument();
    expect(screen.getByText(/12 months after it is no longer required/i)).toBeInTheDocument();
    expect(screen.getByText(/Users may also revoke Story Engine access through Google/i)).toBeInTheDocument();
  });

  it("renders the terms page directly and shows the Nigerian governing-law legal-review note", async () => {
    renderApp("/terms");

    await screen.findByRole("heading", { name: "Story Engine Terms of Service" });

    expect(screen.getByText(/Federal Republic of Nigeria is pending legal review/i)).toBeInTheDocument();
    expect(screen.getByText(/billing and refunds are not yet implemented/i)).toBeInTheDocument();
  });

  it("renders the public deletion page with the confirmation phrase and YouTube warning", async () => {
    renderApp("/data-deletion");

    await screen.findByRole("heading", { name: /Account and data deletion instructions/i });

    expect(screen.getByText("DELETE MY ACCOUNT")).toBeInTheDocument();
    expect(screen.getByText(/does not automatically delete videos already uploaded to YouTube/i)).toBeInTheDocument();
    expect(screen.getByText(/Identity verification may be required/i)).toBeInTheDocument();
  });

  it("supports public navigation links without private API data", async () => {
    const accessStatusSpy = vi.spyOn(api, "getAccessStatus");

    renderApp("/");

    fireEvent.click((await screen.findAllByRole("link", { name: "Privacy Policy" }))[0]);

    await screen.findByRole("heading", { name: "Story Engine Privacy Policy" });
    expect(accessStatusSpy).not.toHaveBeenCalled();
  });

  it("keeps authenticated routes protected behind the access gate", async () => {
    vi.spyOn(api, "getAccessStatus").mockResolvedValue({
      auth_enabled: true,
      authenticated: false,
      account_deleted: false,
      environment: "test",
    });

    renderApp("/app");

    await waitFor(() => {
      expect(api.getAccessStatus).toHaveBeenCalledTimes(1);
    });
    expect(screen.getByRole("heading", { name: /Enter app access password/i })).toBeInTheDocument();
  });
});
