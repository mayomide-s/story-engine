import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  api,
  type FinalAssetSelection,
  type PublicationJob,
  type SocialConnectionSummary,
  type YouTubeProjectCompliance,
} from "../api/client";
import { YouTubePublicationPanel } from "./YouTubePublicationPanel";

const finalAssetSelection: FinalAssetSelection = {
  source: "source_video",
  asset: {
    id: "asset-1",
    public_url: "http://localhost:8000/assets/final.mp4",
    original_filename: "final.mp4",
  },
  selection_revision: 3,
  caption_cues: [],
  voice_is_ai_generated: false,
  original_video_asset: {
    id: "asset-1",
  },
  can_revert_to_source: false,
};

const activeConnection: SocialConnectionSummary = {
  id: "conn-1",
  platform: "youtube",
  display_name: "Test Channel",
  username: "@testchannel",
  external_identity_hint: "UC123",
  connection_status: "active",
  granted_scopes: ["https://www.googleapis.com/auth/youtube.upload"],
  token_expires_at: null,
  token_health: "healthy",
  is_default: true,
  connected_at: null,
  disconnected_at: null,
  last_error_code: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

function makeCompliance(status: YouTubeProjectCompliance["compliance_status"]): YouTubeProjectCompliance {
  return {
    platform: "youtube",
    compliance_status: status,
    status_updated_at: "2026-01-01T00:00:00Z",
    submission_date: status === "audit_pending" || status === "audit_approved" ? "2026-01-02" : null,
    approval_date: status === "audit_approved" ? "2026-01-05" : null,
    case_reference: status === "audit_approved" ? "YT-AUDIT-123" : null,
    admin_note: null,
    can_publish_private: true,
    can_publish_unlisted: status === "audit_approved",
    can_publish_public: status === "audit_approved",
    status_explanation:
      status === "audit_approved"
        ? "YouTube audit approval is recorded. Private, unlisted, and public can be selected for future uploads."
        : status === "audit_pending"
          ? "YouTube audit review is recorded as pending. Private uploads remain available while unlisted and public stay blocked."
          : status === "unknown"
            ? "YouTube audit status is unknown. Story Engine safely treats unlisted and public uploads as unavailable until approval is recorded."
            : "This YouTube API project is recorded as private-only. Google restricts uploads from unverified projects to private viewing until compliance approval is recorded.",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
}

function makeJob(
  status: PublicationJob["status"],
  targetState: PublicationJob["targets"][0]["state"],
  visibility: PublicationJob["targets"][0]["visibility"] = "private",
): PublicationJob {
  return {
    id: "job-1",
    pipeline_run_id: "run-1",
    manual_post_package_id: "pkg-1",
    final_asset_id: "asset-1",
    final_asset_selection_revision: 3,
    final_asset_source: "source_video",
    final_asset_sha256: "a".repeat(64),
    final_asset_metadata: {},
    status,
    approved_at: status === "draft" ? null : "2026-01-01T00:00:00Z",
    completed_at: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    selected_asset_is_frozen: true,
    selected_asset_has_changed_since_draft: false,
    available_actions:
      status === "draft"
        ? ["approve", "cancel"]
        : status === "approved"
          ? ["dispatch"]
          : [],
    targets: [
      {
        id: "target-1",
        social_connection_id: "conn-1",
        channel_display_name: "Test Channel",
        channel_username: "@testchannel",
        channel_external_account_id: "UC123",
        platform: "youtube",
        visibility,
        actual_visibility: targetState === "uploaded_private" ? "private" : null,
        title: "API Waiter",
        caption: "Description",
        tags: ["api"],
        category_id: "27",
        self_declared_made_for_kids: false,
        contains_synthetic_media: true,
        options: {},
        state: targetState,
        idempotency_key: "youtube:key",
        provider_video_id: targetState === "uploading" ? null : "abc123xyz98",
        provider_submission_id: targetState === "uploading" ? null : "abc123xyz98",
        provider_media_id: targetState === "uploading" ? null : "abc123xyz98",
        provider_upload_status: null,
        provider_processing_status: null,
        public_post_url: null,
        platform_post_id: null,
        attempt_count: 1,
        upload_bytes_total: targetState === "uploading" ? 100 : null,
        upload_bytes_sent: targetState === "uploading" ? 40 : null,
        upload_progress_percent: targetState === "uploading" ? 40 : null,
        next_poll_at: null,
        processing_last_checked_at: null,
        outcome_confirmed_at: null,
        last_error_code: null,
        last_error_message: null,
        reconnect_required: false,
        submitted_at: null,
        published_at: null,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
        platform_post_creation_eligible: visibility !== "private",
        visibility_semantics: visibility === "private"
          ? "Private uploads do not create PlatformPost rows."
          : "Only confirmed unlisted or public YouTube uploads may later create PlatformPost rows.",
        available_actions:
          targetState === "retryable_failure"
            ? ["retry"]
            : targetState === "outcome_uncertain"
              ? ["reconcile"]
              : [],
      },
    ],
  };
}

describe("YouTubePublicationPanel", () => {
  const locationAssign = vi.fn();

  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(api, "listSocialConnections");
    vi.spyOn(api, "getLatestPublicationJobForRun");
    vi.spyOn(api, "getYouTubeProjectCompliance");
    vi.spyOn(api, "updateYouTubeProjectCompliance");
    vi.spyOn(api, "getYouTubeAuditReadinessReport");
    vi.spyOn(api, "getYouTubeAuditReadinessReportMarkdown");
    vi.spyOn(api, "authorizeYouTubeConnection");
    vi.spyOn(api, "createPublicationJob");
    vi.spyOn(api, "approvePublicationJob");
    vi.spyOn(api, "dispatchPublicationJob");
    Object.defineProperty(window, "location", {
      value: { assign: locationAssign },
      writable: true,
    });
    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn().mockResolvedValue(undefined),
      },
    });
  });

  afterEach(() => {
    locationAssign.mockReset();
  });

  it("shows the YouTube connection prerequisite and redirects to authorization", async () => {
    vi.mocked(api.listSocialConnections).mockResolvedValue({ items: [] });
    vi.mocked(api.getLatestPublicationJobForRun).mockRejectedValue(new Error("Publication job not found"));
    vi.mocked(api.getYouTubeProjectCompliance).mockResolvedValue(makeCompliance("private_only"));
    vi.mocked(api.authorizeYouTubeConnection).mockResolvedValue({
      platform: "youtube",
      authorization_url: "https://accounts.google.com/o/oauth2/auth",
      expires_at: "2026-01-01T00:05:00Z",
    });

    render(
      <YouTubePublicationPanel
        runId="run-1"
        runStatus="completed"
        finalAssetSelection={finalAssetSelection}
        manualPostPackage={null}
      />,
    );

    await screen.findByText("Connect YouTube first");
    fireEvent.click(screen.getByRole("button", { name: "Connect YouTube" }));

    await waitFor(() => expect(api.authorizeYouTubeConnection).toHaveBeenCalled());
    expect(locationAssign).toHaveBeenCalledWith("https://accounts.google.com/o/oauth2/auth");
  });

  it("shows private-only compliance and disables unlisted/public before approval", async () => {
    vi.mocked(api.listSocialConnections).mockResolvedValue({ items: [activeConnection] });
    vi.mocked(api.getLatestPublicationJobForRun).mockRejectedValue(new Error("Publication job not found"));
    vi.mocked(api.getYouTubeProjectCompliance).mockResolvedValue(makeCompliance("private_only"));

    render(
      <YouTubePublicationPanel
        runId="run-1"
        runStatus="completed"
        finalAssetSelection={finalAssetSelection}
        manualPostPackage={null}
      />,
    );

    await screen.findByText("YouTube compliance status: Private only");
    const privacySelect = screen.getByLabelText("Privacy") as HTMLSelectElement;
    const options = Array.from(privacySelect.options);

    expect(options.find((item) => item.value === "private")?.disabled).toBe(false);
    expect(options.find((item) => item.value === "unlisted")?.disabled).toBe(true);
    expect(options.find((item) => item.value === "public")?.disabled).toBe(true);
    expect(screen.getAllByText(/restricts uploads from unverified projects/i).length).toBeGreaterThan(0);
  });

  it("creates, approves, and dispatches a publication job from the review panel", async () => {
    vi.mocked(api.listSocialConnections).mockResolvedValue({ items: [activeConnection] });
    vi.mocked(api.getLatestPublicationJobForRun).mockRejectedValue(new Error("Publication job not found"));
    vi.mocked(api.getYouTubeProjectCompliance).mockResolvedValue(makeCompliance("audit_approved"));
    vi.mocked(api.createPublicationJob).mockResolvedValue({ job: makeJob("draft", "pending", "public") });
    vi.mocked(api.approvePublicationJob).mockResolvedValue({ job: makeJob("approved", "pending", "public") });
    vi.mocked(api.dispatchPublicationJob).mockResolvedValue({ job: makeJob("active", "uploading", "public") });

    render(
      <YouTubePublicationPanel
        runId="run-1"
        runStatus="completed"
        finalAssetSelection={finalAssetSelection}
        manualPostPackage={{
          caption: "Manual package caption",
          hashtags_json: ["api", "backend"],
        }}
      />,
    );

    await screen.findByText("Connected channel");

    fireEvent.change(screen.getByLabelText("Privacy"), { target: { value: "public" } });
    fireEvent.click(screen.getByRole("button", { name: "Publish to YouTube" }));
    await screen.findByText("Publication status");
    expect(screen.getByRole("button", { name: "Approve publication" })).toBeDisabled();

    fireEvent.click(screen.getByRole("checkbox", { name: /approve publication/i }));
    fireEvent.click(screen.getByRole("button", { name: "Approve publication" }));
    await screen.findByRole("button", { name: "Start YouTube upload" });

    fireEvent.click(screen.getByRole("button", { name: "Start YouTube upload" }));

    await screen.findByText("Upload progress: 40%");
    expect(api.createPublicationJob).toHaveBeenCalledWith(
      "run-1",
      expect.objectContaining({ privacy: "public" }),
    );
    expect(api.approvePublicationJob).toHaveBeenCalledWith("job-1");
    expect(api.dispatchPublicationJob).toHaveBeenCalledWith("job-1");
  });

  it("loads the audit report and saves an approved compliance state", async () => {
    vi.mocked(api.listSocialConnections).mockResolvedValue({ items: [activeConnection] });
    vi.mocked(api.getLatestPublicationJobForRun).mockRejectedValue(new Error("Publication job not found"));
    vi.mocked(api.getYouTubeProjectCompliance).mockResolvedValue(makeCompliance("audit_pending"));
    vi.mocked(api.updateYouTubeProjectCompliance).mockResolvedValue(makeCompliance("audit_approved"));
    vi.mocked(api.getYouTubeAuditReadinessReport).mockResolvedValue({
      platform: "youtube",
      application_name: "Story Engine",
      application_purpose: "Review and publish selected final videos.",
      connected_youtube_functionality: "OAuth plus resumable uploads.",
      current_compliance_status: "audit_pending",
      requested_scopes: [
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/youtube.readonly",
      ],
      scope_justifications: [
        {
          scope: "https://www.googleapis.com/auth/youtube.upload",
          required_for: "Upload approved videos.",
        },
      ],
      sections: [
        {
          key: "visibility-controls",
          title: "Visibility controls",
          status: "implemented_verified",
          summary: "Unlisted/public are blocked until approval.",
          bullets: ["Blocked requests fail locally before job creation."],
        },
      ],
      generated_at: "2026-01-01T00:00:00Z",
      application_version: "80ee63d2",
      markdown: "# Report",
    });

    render(
      <YouTubePublicationPanel
        runId="run-1"
        runStatus="completed"
        finalAssetSelection={finalAssetSelection}
        manualPostPackage={null}
      />,
    );

    await screen.findByText("YouTube compliance status: Audit pending");
    fireEvent.click(screen.getByText("YouTube audit readiness"));
    fireEvent.click(screen.getByRole("button", { name: "View audit report" }));

    await screen.findByText("YouTube audit-readiness report");
    expect(screen.getByText("Visibility controls")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Compliance status"), { target: { value: "audit_approved" } });
    fireEvent.click(screen.getByRole("checkbox", { name: /compliance approval has been granted/i }));
    fireEvent.click(screen.getByRole("button", { name: "Save compliance status" }));

    await waitFor(() =>
      expect(api.updateYouTubeProjectCompliance).toHaveBeenCalledWith(
        expect.objectContaining({
          compliance_status: "audit_approved",
          confirm_audit_approved: true,
        }),
      ),
    );
  });
});
