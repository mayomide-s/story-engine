import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  api,
  type FinalAssetSelection,
  type PublicationJob,
  type SocialConnectionSummary,
  type YouTubeComplianceReadiness,
  type YouTubeComplianceSubmissionPackage,
  type YouTubeProjectCompliance,
  type YouTubeSubmissionProfile,
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

function makeProfile(): YouTubeSubmissionProfile {
  return {
    platform: "youtube",
    application_display_name: "Story Engine",
    product_description: "Review and publish selected final videos.",
    organization_name: "Mayomide Studio",
    support_contact: "support@example.com",
    privacy_policy_url: "https://storyengine.example.com/privacy",
    terms_of_service_url: "https://storyengine.example.com/terms",
    application_homepage_url: "https://storyengine.example.com",
    production_oauth_redirect_uri: "https://api.storyengine.example.com/api/social-connections/youtube/callback",
    production_frontend_url: "https://storyengine.example.com",
    production_api_url: "https://api.storyengine.example.com",
    data_retention_summary: "Retained for auditability.",
    user_data_deletion_summary: "Deletion available through support.",
    token_revocation_summary: "Revocation available through Google.",
    account_disconnection_summary: "Disconnect clears stored tokens.",
    quota_monitoring_summary: "Quota monitored operationally.",
    incident_response_summary: "Incidents are reviewed and resolved.",
    security_contact_summary: "security@example.com",
    intended_submission_date: "2026-01-20",
    submission_case_reference: "YT-SUBMIT-123",
    last_reviewed_at: "2026-01-01T00:00:00Z",
    reviewed_by: "Admin Reviewer",
    admin_note: null,
    human_confirmations: [
      {
        key: "legal_review_completed",
        title: "Legal review completed",
        description: "Legal review is complete.",
        required_for_approval: true,
        completed: false,
      },
      {
        key: "submission_package_reviewed",
        title: "Submission package reviewed",
        description: "Submission package reviewed.",
        required_for_approval: true,
        completed: false,
      },
    ],
  };
}

function makeReadiness(canApprove = false): YouTubeComplianceReadiness {
  return {
    platform: "youtube",
    current_compliance_status: canApprove ? "audit_pending" : "private_only",
    overall_status: canApprove ? "pass" : "fail",
    blocker_count: canApprove ? 0 : 2,
    blockers: canApprove
      ? []
      : [
        {
          key: "privacy-policy-url",
          title: "Privacy policy URL recorded",
          category: "privacy",
          status: "fail",
          blocker_severity: "blocking",
          evidence_summary: "Missing.",
          remediation_guidance: "Record the production HTTPS privacy policy URL.",
        },
        {
          key: "confirmation:legal_review_completed",
          title: "Legal review completed",
          category: "legal and organisational information",
          status: "needs_confirmation",
          blocker_severity: "blocking",
          evidence_summary: "Still required.",
          remediation_guidance: "Complete the legal review.",
        },
      ],
    requirements: [
      {
        key: "privacy-policy-url",
        title: "Privacy policy URL recorded",
        description: "A privacy policy URL is required.",
        category: "privacy",
        status: canApprove ? "pass" : "fail",
        evidence_source: "submission_profile",
        evidence_summary: canApprove ? "Recorded." : "Missing.",
        blocker_severity: canApprove ? "none" : "blocking",
        remediation_guidance: "Record the production HTTPS privacy policy URL.",
        human_confirmation_required: false,
        last_evaluated_at: "2026-01-01T00:00:00Z",
      },
      {
        key: "confirmation:legal_review_completed",
        title: "Legal review completed",
        description: "Human legal confirmation is required.",
        category: "legal and organisational information",
        status: canApprove ? "pass" : "needs_confirmation",
        evidence_source: "human_confirmation",
        evidence_summary: canApprove ? "Recorded." : "Still required.",
        blocker_severity: canApprove ? "none" : "blocking",
        remediation_guidance: "Complete the legal review.",
        human_confirmation_required: true,
        last_evaluated_at: "2026-01-01T00:00:00Z",
      },
    ],
    human_confirmations: makeProfile().human_confirmations,
    can_record_audit_approved: canApprove,
    generated_at: "2026-01-01T00:00:00Z",
  };
}

function makePackage(): YouTubeComplianceSubmissionPackage {
  return {
    platform: "youtube",
    executive_summary: {
      application_display_name: "Story Engine",
      readiness_status: "fail",
      blocker_count: 2,
      product_purpose: "Review and publish selected final videos.",
    },
    oauth_and_access: {
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
    },
    publishing_workflow: {},
    user_controls: {},
    security_and_operations: {},
    legal_and_policy: {},
    readiness: makeReadiness(false),
    evidence_matrix: makeReadiness(false).requirements,
    evidence_manifest: [
      {
        key: "privacy-policy-page",
        title: "Privacy policy page",
        required: true,
        why_needed: "Reviewer evidence.",
        acceptable_evidence: "Screenshot or URL.",
        current_state: "Blocked until a privacy policy URL is recorded",
        human_action_required: true,
      },
    ],
    submission_checklist: ["Resolve blockers", "Capture screenshots"],
    human_completion_items: ["Privacy policy page: Screenshot or URL."],
    generated_at: "2026-01-01T00:00:00Z",
    application_version: "9efb867d",
    markdown: "# YouTube Compliance Submission Package",
    checklist_markdown: "# YouTube Submission Checklist",
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
    vi.spyOn(api, "getYouTubeSubmissionProfile");
    vi.spyOn(api, "updateYouTubeSubmissionProfile");
    vi.spyOn(api, "getYouTubeComplianceReadiness");
    vi.spyOn(api, "setYouTubeHumanConfirmation");
    vi.spyOn(api, "clearYouTubeHumanConfirmation");
    vi.spyOn(api, "getYouTubeComplianceSubmissionPackage");
    vi.spyOn(api, "getYouTubeComplianceSubmissionPackageMarkdown");
    vi.spyOn(api, "getYouTubeComplianceSubmissionChecklistMarkdown");
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

  function primeBase({
    compliance = makeCompliance("private_only"),
    readiness = makeReadiness(false),
    profile = makeProfile(),
    jobError = true,
  }: {
    compliance?: YouTubeProjectCompliance;
    readiness?: YouTubeComplianceReadiness;
    profile?: YouTubeSubmissionProfile;
    jobError?: boolean;
  } = {}) {
    vi.mocked(api.listSocialConnections).mockResolvedValue({ items: [activeConnection] });
    if (jobError) {
      vi.mocked(api.getLatestPublicationJobForRun).mockRejectedValue(new Error("Publication job not found"));
    } else {
      vi.mocked(api.getLatestPublicationJobForRun).mockResolvedValue(makeJob("draft", "pending", "private"));
    }
    vi.mocked(api.getYouTubeProjectCompliance).mockResolvedValue(compliance);
    vi.mocked(api.getYouTubeSubmissionProfile).mockResolvedValue(profile);
    vi.mocked(api.getYouTubeComplianceReadiness).mockResolvedValue(readiness);
  }

  it("shows readiness summary, blocker panel, grouped requirements, and disabled audit approval while blocked", async () => {
    primeBase();

    render(
      <YouTubePublicationPanel
        runId="run-1"
        runStatus="completed"
        finalAssetSelection={finalAssetSelection}
        manualPostPackage={null}
      />,
    );

    await screen.findByText("YouTube submission readiness: Fail");
    expect(screen.getByText("Unresolved blockers")).toBeInTheDocument();
    expect(screen.getByText("Requirements by category")).toBeInTheDocument();
    expect(screen.getByText("privacy")).toBeInTheDocument();
    fireEvent.click(screen.getByText("YouTube compliance submission preparation"));
    const statusSelect = screen.getByLabelText("Compliance status") as HTMLSelectElement;
    const approvedOption = Array.from(statusSelect.options).find((item) => item.value === "audit_approved");
    expect(approvedOption?.disabled).toBe(true);
  });

  it("saves submission profile fields and toggles human confirmations", async () => {
    primeBase();
    vi.mocked(api.updateYouTubeSubmissionProfile).mockResolvedValue(makeProfile());
    vi.mocked(api.setYouTubeHumanConfirmation).mockResolvedValue({
      ...makeProfile(),
      human_confirmations: makeProfile().human_confirmations.map((item) =>
        item.key === "legal_review_completed" ? { ...item, completed: true } : item,
      ),
    });

    render(
      <YouTubePublicationPanel
        runId="run-1"
        runStatus="completed"
        finalAssetSelection={finalAssetSelection}
        manualPostPackage={null}
      />,
    );

    await screen.findByText("YouTube submission readiness: Fail");
    fireEvent.click(screen.getByText("YouTube compliance submission preparation"));
    fireEvent.change(screen.getByLabelText("Application display name"), { target: { value: "Story Engine Pro" } });
    fireEvent.click(screen.getByRole("button", { name: "Save submission profile" }));

    await waitFor(() =>
      expect(api.updateYouTubeSubmissionProfile).toHaveBeenCalledWith(
        expect.objectContaining({ application_display_name: "Story Engine Pro" }),
      ),
    );

    fireEvent.click(screen.getByRole("checkbox", { name: /Legal review completed/i }));
    await waitFor(() => expect(api.setYouTubeHumanConfirmation).toHaveBeenCalledWith("legal_review_completed", true, "Admin Reviewer"));
  });

  it("loads package exports and keeps approval blocked messaging visible", async () => {
    primeBase();
    vi.mocked(api.getYouTubeComplianceSubmissionPackage).mockResolvedValue(makePackage());
    vi.mocked(api.getYouTubeComplianceSubmissionPackageMarkdown).mockResolvedValue("# YouTube Compliance Submission Package");
    vi.mocked(api.getYouTubeComplianceSubmissionChecklistMarkdown).mockResolvedValue("# YouTube Submission Checklist");

    render(
      <YouTubePublicationPanel
        runId="run-1"
        runStatus="completed"
        finalAssetSelection={finalAssetSelection}
        manualPostPackage={null}
      />,
    );

    await screen.findByText("YouTube submission readiness: Fail");
    fireEvent.click(screen.getByText("YouTube compliance submission preparation"));
    fireEvent.click(screen.getByRole("button", { name: "View JSON package" }));
    await screen.findByText("YouTube compliance submission package");
    expect(screen.getByText("Evidence manifest")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "View Markdown package" }));
    await screen.findByText("Submission package markdown");

    fireEvent.click(screen.getByRole("button", { name: "View checklist export" }));
    await screen.findByText("Submission checklist export");
  });

  it("enables audit-approved selection after backend readiness passes and still supports publication flow", async () => {
    primeBase({
      compliance: makeCompliance("audit_pending"),
      readiness: makeReadiness(true),
    });
    vi.mocked(api.updateYouTubeProjectCompliance).mockResolvedValue(makeCompliance("audit_pending"));
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

    await screen.findByText("YouTube submission readiness: Pass");
    fireEvent.click(screen.getByText("YouTube compliance submission preparation"));
    const statusSelect = screen.getByLabelText("Compliance status") as HTMLSelectElement;
    const approvedOption = Array.from(statusSelect.options).find((item) => item.value === "audit_approved");
    expect(approvedOption?.disabled).toBe(false);

    fireEvent.change(screen.getByLabelText("Privacy"), { target: { value: "public" } });
    fireEvent.click(screen.getByRole("button", { name: "Publish to YouTube" }));
    await screen.findByText("Publication status");
    fireEvent.click(
      screen.getByRole("checkbox", {
        name: /I reviewed the frozen asset, metadata, visibility, made-for-kids setting, and synthetic-media disclosure/i,
      }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Approve publication" }));
    await screen.findByRole("button", { name: "Start YouTube upload" });
  });

  it("shows connect prerequisite and redirects to authorization", async () => {
    vi.mocked(api.listSocialConnections).mockResolvedValue({ items: [] });
    vi.mocked(api.getLatestPublicationJobForRun).mockRejectedValue(new Error("Publication job not found"));
    vi.mocked(api.getYouTubeProjectCompliance).mockResolvedValue(makeCompliance("private_only"));
    vi.mocked(api.getYouTubeSubmissionProfile).mockResolvedValue(makeProfile());
    vi.mocked(api.getYouTubeComplianceReadiness).mockResolvedValue(makeReadiness(false));
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
});
