import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api, setStoredAccessToken, type AccountDefaults, type AccountDeletionPreview, type RetentionReport } from "../api/client";
import { SettingsPage } from "./Settings";

const defaults: AccountDefaults = {
  account_name: "CodeToons AI",
  niche: "coding",
  account_config_json: {
    default_style_preset: "clean_3d_cartoon",
    target_platforms: ["instagram", "tiktok", "youtube"],
    default_caption_tone: "playful explainer",
    default_hashtag_set: ["#coding"],
    default_duration_seconds: 18,
    default_audience_level: "beginner",
    default_content_format: "coding metaphor",
    brand_description: "Teach APIs visually.",
    preferred_cta: "Follow for more.",
    avoid_phrases: ["guru"],
    emoji_preference: "minimal",
    style_presets: {},
  },
};

const deletionPreview: AccountDeletionPreview = {
  account_status: "active",
  can_delete: true,
  requires_password_confirmation: true,
  requires_recent_authentication: false,
  confirmation_phrase: "DELETE MY ACCOUNT",
  provider_video_warning: "Videos already uploaded to YouTube or other providers will remain online and must be removed on those platforms separately.",
  connected_accounts: [
    {
      platform: "youtube",
      display_name: "CodeToons Channel",
      username: "@codetoons",
    },
  ],
  deletion_categories: [
    {
      key: "social-connections",
      title: "Connected social accounts",
      count: 1,
      description: "Connected YouTube account records will be disconnected and removed from Story Engine.",
    },
  ],
  anonymised_categories: [
    {
      key: "account-tombstone",
      title: "Account tombstone",
      count: 1,
      description: "A minimal deleted-account record is retained to prevent reactivation and keep deletion idempotent.",
    },
  ],
  temporarily_retained_categories: [
    {
      key: "deleted-account-marker",
      title: "Deleted-account marker",
      count: 1,
      description: "Retained for up to 12 months for security review and anti-reactivation safeguards.",
    },
  ],
};

const retentionReport: RetentionReport = {
  default_retention_months: 12,
  generated_at: "2026-07-13T12:00:00Z",
  categories: [
    {
      key: "deleted-account-tombstones",
      title: "Deleted-account tombstones",
      retention_months: 12,
      cleanup_action: "review_for_purge",
      description: "Review for purge after 12 months.",
      automatically_deleted: false,
      expired_record_count: 0,
    },
  ],
};

describe("SettingsPage account deletion controls", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(api, "getAccountDefaults").mockResolvedValue(defaults);
    vi.spyOn(api, "getAccessStatus").mockResolvedValue({
      auth_enabled: true,
      authenticated: true,
      account_deleted: false,
      environment: "test",
    });
    vi.spyOn(api, "getAccountDeletionPreview").mockResolvedValue(deletionPreview);
    vi.spyOn(api, "getRetentionReport").mockResolvedValue(retentionReport);
    vi.spyOn(api, "validateAccountDeletion").mockResolvedValue({
      can_delete: true,
      requires_password_confirmation: true,
      validation_message: "Account deletion validation passed.",
      preview: deletionPreview,
    });
    vi.spyOn(api, "deleteAccount").mockResolvedValue({
      deleted: true,
      account_status: "deleted",
      message: "Your Story Engine account has been permanently deleted.",
      disconnected_connection_count: 1,
      deleted_social_connection_count: 1,
      deleted_pipeline_run_count: 1,
      deleted_asset_count: 2,
      deleted_local_file_count: 2,
      deleted_publication_job_count: 1,
      deleted_publication_target_count: 1,
      deleted_platform_post_count: 0,
      deleted_snapshot_count: 0,
      deleted_learning_count: 0,
    });
    vi.spyOn(window, "dispatchEvent");
  });

  it("renders the danger zone, retention guidance, and confirmation requirements", async () => {
    render(<SettingsPage />);

    await screen.findByRole("heading", { name: "Delete account" });
    expect(screen.getByText("Connected accounts to disconnect")).toBeInTheDocument();
    expect(screen.getByText(/CodeToons Channel/)).toBeInTheDocument();
    expect(screen.getByText(/12-month maximum retention window/i)).toBeInTheDocument();

    const deleteButton = screen.getByRole("button", { name: "Delete account" });
    expect(deleteButton).toBeDisabled();

    fireEvent.change(screen.getByLabelText("Delete account confirmation phrase"), {
      target: { value: "DELETE MY ACCOUNT" },
    });
    fireEvent.change(screen.getByLabelText("Delete account password confirmation"), {
      target: { value: "open-sesame" },
    });
    fireEvent.click(screen.getByRole("checkbox", {
      name: /uploaded YouTube videos remain online/i,
    }));

    await waitFor(() => expect(deleteButton).toBeEnabled());
  });

  it("validates, deletes, clears the local token, and dispatches the deleted-account event", async () => {
    setStoredAccessToken("temporary-token");
    render(<SettingsPage />);

    await screen.findByRole("heading", { name: "Delete account" });
    fireEvent.change(screen.getByLabelText("Delete account confirmation phrase"), {
      target: { value: "DELETE MY ACCOUNT" },
    });
    fireEvent.change(screen.getByLabelText("Delete account password confirmation"), {
      target: { value: "open-sesame" },
    });
    fireEvent.click(screen.getByRole("checkbox", {
      name: /uploaded YouTube videos remain online/i,
    }));
    fireEvent.click(screen.getByRole("button", { name: "Delete account" }));

    await waitFor(() =>
      expect(api.validateAccountDeletion).toHaveBeenCalledWith({
        confirmation_phrase: "DELETE MY ACCOUNT",
        acknowledge_provider_videos_remain_online: true,
        password: "open-sesame",
      }),
    );
    await waitFor(() => expect(api.deleteAccount).toHaveBeenCalled());
    await waitFor(() =>
      expect(window.dispatchEvent).toHaveBeenCalledWith(
        expect.objectContaining({ type: "story-engine-account-deleted" }),
      ),
    );
    expect(window.localStorage.getItem("story-engine-access-token")).toBeNull();
    expect(window.sessionStorage.getItem("story-engine-account-deletion-notice")).toBe(
      "Your Story Engine account has been permanently deleted.",
    );
  });

  it("shows inline deletion errors without clearing the current page state", async () => {
    vi.mocked(api.validateAccountDeletion).mockRejectedValueOnce(
      new Error("Type DELETE MY ACCOUNT exactly to continue."),
    );

    render(<SettingsPage />);

    await screen.findByRole("heading", { name: "Delete account" });
    fireEvent.change(screen.getByLabelText("Delete account confirmation phrase"), {
      target: { value: "DELETE MY ACCOUNT" },
    });
    fireEvent.change(screen.getByLabelText("Delete account password confirmation"), {
      target: { value: "open-sesame" },
    });
    fireEvent.click(screen.getByRole("checkbox", {
      name: /uploaded YouTube videos remain online/i,
    }));
    fireEvent.click(screen.getByRole("button", { name: "Delete account" }));

    await screen.findByText("Type DELETE MY ACCOUNT exactly to continue.");
    expect(api.deleteAccount).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Delete account confirmation phrase")).toHaveValue("DELETE MY ACCOUNT");
  });
});
