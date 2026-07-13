import { FormEvent, useEffect, useMemo, useState } from "react";

import {
  api,
  FinalAssetSelection,
  PublicationJob,
  PublicationJobDraftPayload,
  PublicationTarget,
  SocialConnectionSummary,
  YouTubeComplianceReadiness,
  YouTubeComplianceSubmissionPackage,
  YouTubeHumanConfirmation,
  YouTubeProjectCompliance,
  YouTubeProjectComplianceUpdatePayload,
  YouTubeSubmissionProfile,
  YouTubeSubmissionProfileUpdatePayload,
} from "../api/client";

function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);

  async function handleClick() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1200);
    } catch {
      setCopied(false);
    }
  }

  return (
    <button type="button" className="secondary" onClick={handleClick}>
      {copied ? `${label} copied` : `Copy ${label}`}
    </button>
  );
}

function formatDateTime(value?: string | null) {
  if (!value) return "Unavailable";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function formatConnectionLabel(connection: SocialConnectionSummary) {
  return connection.display_name || connection.username || connection.external_identity_hint;
}

function formatTargetState(target: PublicationTarget) {
  switch (target.state) {
    case "uploaded_private":
      return "Uploaded privately";
    case "retryable_failure":
      return "Retryable failure";
    case "permanent_failure":
      return "Permanent failure";
    case "outcome_uncertain":
      return "Outcome uncertain";
    default:
      return target.state.replace(/_/g, " ");
  }
}

function splitTags(raw: string) {
  return raw
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function defaultDraftPayload(
  finalAssetSelection: FinalAssetSelection | null,
  manualPostPackage: Record<string, unknown> | null,
): PublicationJobDraftPayload {
  const variants = (manualPostPackage?.platform_variants_json as Record<string, unknown> | undefined) ?? {};
  const youtube = (variants.youtube as Record<string, unknown> | undefined) ?? {};
  const hashtags = Array.isArray(manualPostPackage?.hashtags_json)
    ? manualPostPackage.hashtags_json.map((item) => String(item))
    : [];
  const asset = finalAssetSelection?.asset as Record<string, unknown> | undefined;
  return {
    title: String(youtube.title ?? manualPostPackage?.caption ?? asset?.original_filename ?? "Story Engine upload"),
    caption: String(youtube.description ?? manualPostPackage?.caption ?? "").trim() || null,
    tags: hashtags,
    category_id: "27",
    privacy: "private",
    self_declared_made_for_kids: false,
    contains_synthetic_media: true,
  };
}

function defaultCompliancePayload(compliance: YouTubeProjectCompliance | null): YouTubeProjectComplianceUpdatePayload {
  return {
    compliance_status: compliance?.compliance_status ?? "private_only",
    submission_date: compliance?.submission_date ?? null,
    approval_date: compliance?.approval_date ?? null,
    case_reference: compliance?.case_reference ?? null,
    admin_note: compliance?.admin_note ?? null,
    confirm_audit_approved: false,
    confirm_google_audit_approval_received: false,
  };
}

function defaultProfilePayload(profile: YouTubeSubmissionProfile | null): YouTubeSubmissionProfileUpdatePayload {
  return {
    application_display_name: profile?.application_display_name ?? null,
    product_description: profile?.product_description ?? null,
    organization_name: profile?.organization_name ?? null,
    support_contact: profile?.support_contact ?? null,
    privacy_policy_url: profile?.privacy_policy_url ?? null,
    terms_of_service_url: profile?.terms_of_service_url ?? null,
    application_homepage_url: profile?.application_homepage_url ?? null,
    production_oauth_redirect_uri: profile?.production_oauth_redirect_uri ?? null,
    production_frontend_url: profile?.production_frontend_url ?? null,
    production_api_url: profile?.production_api_url ?? null,
    data_retention_summary: profile?.data_retention_summary ?? null,
    user_data_deletion_summary: profile?.user_data_deletion_summary ?? null,
    token_revocation_summary: profile?.token_revocation_summary ?? null,
    account_disconnection_summary: profile?.account_disconnection_summary ?? null,
    quota_monitoring_summary: profile?.quota_monitoring_summary ?? null,
    incident_response_summary: profile?.incident_response_summary ?? null,
    security_contact_summary: profile?.security_contact_summary ?? null,
    intended_submission_date: profile?.intended_submission_date ?? null,
    submission_case_reference: profile?.submission_case_reference ?? null,
    reviewed_by: profile?.reviewed_by ?? null,
    admin_note: profile?.admin_note ?? null,
  };
}

function formatComplianceLabel(status: string) {
  switch (status) {
    case "audit_approved":
      return "Audit approved";
    case "audit_pending":
      return "Audit pending";
    case "unknown":
      return "Unknown";
    default:
      return "Private only";
  }
}

function formatReadinessLabel(status: string) {
  switch (status) {
    case "needs_confirmation":
      return "Needs confirmation";
    case "not_applicable":
      return "Not applicable";
    default:
      return status.charAt(0).toUpperCase() + status.slice(1);
  }
}

function statusClassName(status: string) {
  if (status === "pass") return "success";
  if (status === "fail") return "warning";
  if (status === "needs_confirmation") return "warning";
  return "";
}

type Props = {
  runId: string;
  runStatus: string;
  finalAssetSelection: FinalAssetSelection | null;
  manualPostPackage?: Record<string, unknown> | null;
};

export function YouTubePublicationPanel({ runId, runStatus, finalAssetSelection, manualPostPackage }: Props) {
  const [connections, setConnections] = useState<SocialConnectionSummary[]>([]);
  const [job, setJob] = useState<PublicationJob | null>(null);
  const [compliance, setCompliance] = useState<YouTubeProjectCompliance | null>(null);
  const [profile, setProfile] = useState<YouTubeSubmissionProfile | null>(null);
  const [readiness, setReadiness] = useState<YouTubeComplianceReadiness | null>(null);
  const [submissionPackage, setSubmissionPackage] = useState<YouTubeComplianceSubmissionPackage | null>(null);
  const [packageMarkdown, setPackageMarkdown] = useState("");
  const [checklistMarkdown, setChecklistMarkdown] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isWorking, setIsWorking] = useState(false);
  const [isSavingCompliance, setIsSavingCompliance] = useState(false);
  const [isSavingProfile, setIsSavingProfile] = useState(false);
  const [isSavingConfirmationKey, setIsSavingConfirmationKey] = useState<string | null>(null);
  const [isLoadingPackage, setIsLoadingPackage] = useState(false);
  const [error, setError] = useState("");
  const [approvalChecked, setApprovalChecked] = useState(false);
  const [showSubmissionPrep, setShowSubmissionPrep] = useState(false);
  const [showExports, setShowExports] = useState(false);
  const [exportMode, setExportMode] = useState<"json" | "markdown" | "checklist">("json");
  const [draft, setDraft] = useState<PublicationJobDraftPayload>(() => defaultDraftPayload(finalAssetSelection, manualPostPackage ?? null));
  const [tagsInput, setTagsInput] = useState(() => defaultDraftPayload(finalAssetSelection, manualPostPackage ?? null).tags.join(", "));
  const [complianceForm, setComplianceForm] = useState<YouTubeProjectComplianceUpdatePayload>(() => defaultCompliancePayload(null));
  const [profileForm, setProfileForm] = useState<YouTubeSubmissionProfileUpdatePayload>(() => defaultProfilePayload(null));

  const selectedAsset = finalAssetSelection?.asset as Record<string, unknown> | undefined;
  const activeConnection = useMemo(
    () => connections.find((item) => item.platform === "youtube" && item.connection_status === "active" && item.is_default)
      ?? connections.find((item) => item.platform === "youtube" && item.connection_status === "active")
      ?? null,
    [connections],
  );
  const target = job?.targets[0] ?? null;
  const canPublish = runStatus === "completed" && Boolean(finalAssetSelection?.asset);
  const terminalTarget = target ? ["uploaded_private", "published", "permanent_failure", "cancelled"].includes(target.state) : false;
  const canUseUnlisted = Boolean(compliance?.can_publish_unlisted);
  const canUsePublic = Boolean(compliance?.can_publish_public);
  const canRecordAuditApproved = Boolean(readiness?.can_record_audit_approved);
  const groupedRequirements = useMemo(() => {
    const groups = new Map<string, YouTubeComplianceReadiness["requirements"]>();
    for (const item of readiness?.requirements ?? []) {
      const group = groups.get(item.category) ?? [];
      group.push(item);
      groups.set(item.category, group);
    }
    return Array.from(groups.entries());
  }, [readiness]);

  useEffect(() => {
    const nextDefault = defaultDraftPayload(finalAssetSelection, manualPostPackage ?? null);
    setDraft((current) => job ? current : nextDefault);
    setTagsInput((current) => job ? current : nextDefault.tags.join(", "));
  }, [finalAssetSelection, manualPostPackage, job]);

  useEffect(() => {
    if (job || !compliance) return;
    if ((draft.privacy === "unlisted" && !canUseUnlisted) || (draft.privacy === "public" && !canUsePublic)) {
      setDraft((current) => ({ ...current, privacy: "private" }));
    }
  }, [canUsePublic, canUseUnlisted, compliance, draft.privacy, job]);

  useEffect(() => {
    setComplianceForm(defaultCompliancePayload(compliance));
  }, [compliance]);

  useEffect(() => {
    setProfileForm(defaultProfilePayload(profile));
  }, [profile]);

  async function loadComplianceResources() {
    const [complianceResponse, profileResponse, readinessResponse] = await Promise.all([
      api.getYouTubeProjectCompliance(),
      api.getYouTubeSubmissionProfile(),
      api.getYouTubeComplianceReadiness(),
    ]);
    setCompliance(complianceResponse);
    setProfile(profileResponse);
    setReadiness(readinessResponse);
  }

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setIsLoading(true);
      try {
        const [connectionResponse, latestJob] = await Promise.all([
          api.listSocialConnections(),
          api.getLatestPublicationJobForRun(runId).catch((requestError: Error) => {
            if (requestError.message === "Publication job not found") {
              return null;
            }
            throw requestError;
          }),
        ]);
        if (cancelled) return;
        setConnections(connectionResponse.items);
        setJob(latestJob);
        await loadComplianceResources();
        if (cancelled) return;
        setError("");
      } catch (requestError) {
        if (cancelled) return;
        setError(requestError instanceof Error ? requestError.message : "Failed to load YouTube publishing state.");
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }
    load().catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [runId]);

  useEffect(() => {
    if (!job || terminalTarget) return;
    const timeout = window.setTimeout(() => {
      api.getPublicationJob(job.id)
        .then((nextJob) => {
          setJob(nextJob);
          setError("");
        })
        .catch((requestError: Error) => setError(requestError.message));
    }, 5000);
    return () => window.clearTimeout(timeout);
  }, [job, terminalTarget]);

  async function handleConnect() {
    setIsWorking(true);
    setError("");
    try {
      const response = await api.authorizeYouTubeConnection(`/review?run=${runId}`);
      window.location.assign(response.authorization_url);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to start YouTube connection.");
      setIsWorking(false);
    }
  }

  async function handleCreateDraft(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextTitle = draft.title.trim();
    const nextCaption = draft.caption?.trim() || null;
    if (!nextTitle) {
      setError("Title is required before approval.");
      return;
    }
    setIsSaving(true);
    setError("");
    try {
      const response = await api.createPublicationJob(runId, {
        ...draft,
        title: nextTitle,
        caption: nextCaption,
        tags: splitTags(tagsInput),
      });
      setJob(response.job);
      setApprovalChecked(false);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to create the YouTube publication draft.");
    } finally {
      setIsSaving(false);
    }
  }

  async function runJobAction(action: () => Promise<{ job: PublicationJob }>) {
    setIsWorking(true);
    setError("");
    try {
      const response = await action();
      setJob(response.job);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "YouTube publication action failed.");
    } finally {
      setIsWorking(false);
    }
  }

  async function handleComplianceSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSavingCompliance(true);
    setError("");
    try {
      const response = await api.updateYouTubeProjectCompliance(complianceForm);
      setCompliance(response);
      await loadComplianceResources();
      setSubmissionPackage(null);
      setPackageMarkdown("");
      setChecklistMarkdown("");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to update YouTube compliance status.");
    } finally {
      setIsSavingCompliance(false);
    }
  }

  async function handleProfileSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSavingProfile(true);
    setError("");
    try {
      const response = await api.updateYouTubeSubmissionProfile(profileForm);
      setProfile(response);
      await loadComplianceResources();
      setSubmissionPackage(null);
      setPackageMarkdown("");
      setChecklistMarkdown("");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to update the YouTube submission profile.");
    } finally {
      setIsSavingProfile(false);
    }
  }

  async function toggleConfirmation(item: YouTubeHumanConfirmation, completed: boolean) {
    setIsSavingConfirmationKey(item.key);
    setError("");
    try {
      const response = completed
        ? await api.setYouTubeHumanConfirmation(item.key, true, profileForm.reviewed_by ?? null)
        : await api.clearYouTubeHumanConfirmation(item.key, profileForm.reviewed_by ?? null);
      setProfile(response);
      await loadComplianceResources();
      setSubmissionPackage(null);
      setPackageMarkdown("");
      setChecklistMarkdown("");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to update the human confirmation.");
    } finally {
      setIsSavingConfirmationKey(null);
    }
  }

  async function loadSubmissionPackage(mode: "json" | "markdown" | "checklist") {
    setIsLoadingPackage(true);
    setError("");
    setShowExports(true);
    setExportMode(mode);
    try {
      if (mode === "markdown") {
        setPackageMarkdown(await api.getYouTubeComplianceSubmissionPackageMarkdown());
      } else if (mode === "checklist") {
        setChecklistMarkdown(await api.getYouTubeComplianceSubmissionChecklistMarkdown());
      } else {
        setSubmissionPackage(await api.getYouTubeComplianceSubmissionPackage());
      }
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to load the YouTube compliance submission package.");
    } finally {
      setIsLoadingPackage(false);
    }
  }

  const publishPreviewUrl = String(selectedAsset?.public_url ?? "");

  return (
    <section className="panel inset stack">
      <div className="panel-header">
        <div>
          <h3>Publish to YouTube</h3>
          <p className="subtle">Review the exact frozen final video, approve publication, then let Story Engine track the upload safely.</p>
        </div>
      </div>

      {!canPublish ? (
        <div className="notice-card warning">
          <strong>YouTube publication unavailable</strong>
          <p>Only completed runs with a selected final video can be published to YouTube.</p>
        </div>
      ) : null}

      {error ? <p className="error-text">{error}</p> : null}
      {isLoading ? <p className="subtle">Loading YouTube publication state...</p> : null}

      {compliance ? (
        <div className={`notice-card ${compliance.compliance_status === "audit_approved" ? "success" : "warning"}`}>
          <strong>YouTube compliance status: {formatComplianceLabel(compliance.compliance_status)}</strong>
          <p>{compliance.status_explanation}</p>
          <div className="key-grid">
            <div><span>Status updated</span><strong>{formatDateTime(compliance.status_updated_at)}</strong></div>
            <div><span>Submission date</span><strong>{compliance.submission_date ?? "Not recorded"}</strong></div>
            <div><span>Approval date</span><strong>{compliance.approval_date ?? "Not recorded"}</strong></div>
            <div><span>Reference</span><strong>{compliance.case_reference ?? "Not recorded"}</strong></div>
          </div>
        </div>
      ) : null}

      {readiness ? (
        <div className={`notice-card ${statusClassName(readiness.overall_status)}`}>
          <strong>YouTube submission readiness: {formatReadinessLabel(readiness.overall_status)}</strong>
          <p>
            {readiness.blocker_count} blocker{readiness.blocker_count === 1 ? "" : "s"} remain. Story Engine cannot self-certify Google approval,
            and audit approval stays blocked until the backend readiness check passes.
          </p>
          <div className="key-grid">
            <div><span>Blocker count</span><strong>{String(readiness.blocker_count)}</strong></div>
            <div><span>Can record audit approval</span><strong>{readiness.can_record_audit_approved ? "Yes" : "No"}</strong></div>
            <div><span>Generated</span><strong>{formatDateTime(readiness.generated_at)}</strong></div>
          </div>
        </div>
      ) : null}

      {canPublish ? (
        <details className="technical-disclosure" open={showSubmissionPrep} onToggle={(event) => setShowSubmissionPrep((event.target as HTMLDetailsElement).open)}>
          <summary>YouTube compliance submission preparation</summary>
          <div className="stack compact">
            {readiness?.blockers.length ? (
              <div className="notice-card warning">
                <strong>Unresolved blockers</strong>
                <ul>
                  {readiness.blockers.map((item) => (
                    <li key={item.key}>
                      <strong>{item.title}:</strong> {item.remediation_guidance}
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              <div className="notice-card success">
                <strong>No current blockers</strong>
                <p>The current readiness evaluation has no blocking failures or pending human confirmations.</p>
              </div>
            )}

            <form className="stack" onSubmit={handleProfileSave}>
              <div className="panel inset stack">
                <h4>Submission profile</h4>
                <p className="subtle">Store only non-secret reviewer-facing metadata here. Story Engine does not invent legal claims, production domains, or support contacts for you.</p>
                <div className="form-grid compact">
                  <label>
                    <span>Application display name</span>
                    <input
                      value={profileForm.application_display_name ?? ""}
                      onChange={(event) => setProfileForm((current) => ({ ...current, application_display_name: event.target.value || null }))}
                      maxLength={255}
                    />
                  </label>
                  <label>
                    <span>Organization or developer name</span>
                    <input
                      value={profileForm.organization_name ?? ""}
                      onChange={(event) => setProfileForm((current) => ({ ...current, organization_name: event.target.value || null }))}
                      maxLength={255}
                    />
                  </label>
                </div>
                <label>
                  <span>Product description</span>
                  <textarea
                    value={profileForm.product_description ?? ""}
                    onChange={(event) => setProfileForm((current) => ({ ...current, product_description: event.target.value || null }))}
                    rows={3}
                    maxLength={4000}
                  />
                </label>
                <div className="form-grid compact">
                  <label>
                    <span>Support contact</span>
                    <input
                      value={profileForm.support_contact ?? ""}
                      onChange={(event) => setProfileForm((current) => ({ ...current, support_contact: event.target.value || null }))}
                      maxLength={255}
                    />
                  </label>
                  <label>
                    <span>Security contact summary</span>
                    <input
                      value={profileForm.security_contact_summary ?? ""}
                      onChange={(event) => setProfileForm((current) => ({ ...current, security_contact_summary: event.target.value || null }))}
                      maxLength={4000}
                    />
                  </label>
                </div>
                <div className="form-grid compact">
                  <label>
                    <span>Privacy policy URL</span>
                    <input
                      value={profileForm.privacy_policy_url ?? ""}
                      onChange={(event) => setProfileForm((current) => ({ ...current, privacy_policy_url: event.target.value || null }))}
                    />
                  </label>
                  <label>
                    <span>Terms of service URL</span>
                    <input
                      value={profileForm.terms_of_service_url ?? ""}
                      onChange={(event) => setProfileForm((current) => ({ ...current, terms_of_service_url: event.target.value || null }))}
                    />
                  </label>
                </div>
                <div className="form-grid compact">
                  <label>
                    <span>Application homepage URL</span>
                    <input
                      value={profileForm.application_homepage_url ?? ""}
                      onChange={(event) => setProfileForm((current) => ({ ...current, application_homepage_url: event.target.value || null }))}
                    />
                  </label>
                  <label>
                    <span>Production OAuth redirect URI</span>
                    <input
                      value={profileForm.production_oauth_redirect_uri ?? ""}
                      onChange={(event) => setProfileForm((current) => ({ ...current, production_oauth_redirect_uri: event.target.value || null }))}
                    />
                  </label>
                </div>
                <div className="form-grid compact">
                  <label>
                    <span>Production frontend URL</span>
                    <input
                      value={profileForm.production_frontend_url ?? ""}
                      onChange={(event) => setProfileForm((current) => ({ ...current, production_frontend_url: event.target.value || null }))}
                    />
                  </label>
                  <label>
                    <span>Production API URL</span>
                    <input
                      value={profileForm.production_api_url ?? ""}
                      onChange={(event) => setProfileForm((current) => ({ ...current, production_api_url: event.target.value || null }))}
                    />
                  </label>
                </div>
                <label>
                  <span>Data retention summary</span>
                  <textarea
                    value={profileForm.data_retention_summary ?? ""}
                    onChange={(event) => setProfileForm((current) => ({ ...current, data_retention_summary: event.target.value || null }))}
                    rows={2}
                    maxLength={4000}
                  />
                </label>
                <label>
                  <span>User-data deletion summary</span>
                  <textarea
                    value={profileForm.user_data_deletion_summary ?? ""}
                    onChange={(event) => setProfileForm((current) => ({ ...current, user_data_deletion_summary: event.target.value || null }))}
                    rows={2}
                    maxLength={4000}
                  />
                </label>
                <label>
                  <span>Token revocation summary</span>
                  <textarea
                    value={profileForm.token_revocation_summary ?? ""}
                    onChange={(event) => setProfileForm((current) => ({ ...current, token_revocation_summary: event.target.value || null }))}
                    rows={2}
                    maxLength={4000}
                  />
                </label>
                <label>
                  <span>Account disconnection summary</span>
                  <textarea
                    value={profileForm.account_disconnection_summary ?? ""}
                    onChange={(event) => setProfileForm((current) => ({ ...current, account_disconnection_summary: event.target.value || null }))}
                    rows={2}
                    maxLength={4000}
                  />
                </label>
                <div className="form-grid compact">
                  <label>
                    <span>Quota monitoring summary</span>
                    <textarea
                      value={profileForm.quota_monitoring_summary ?? ""}
                      onChange={(event) => setProfileForm((current) => ({ ...current, quota_monitoring_summary: event.target.value || null }))}
                      rows={2}
                      maxLength={4000}
                    />
                  </label>
                  <label>
                    <span>Incident response summary</span>
                    <textarea
                      value={profileForm.incident_response_summary ?? ""}
                      onChange={(event) => setProfileForm((current) => ({ ...current, incident_response_summary: event.target.value || null }))}
                      rows={2}
                      maxLength={4000}
                    />
                  </label>
                </div>
                <div className="form-grid compact">
                  <label>
                    <span>Submission case/reference ID</span>
                    <input
                      value={profileForm.submission_case_reference ?? ""}
                      onChange={(event) => setProfileForm((current) => ({ ...current, submission_case_reference: event.target.value || null }))}
                      maxLength={255}
                    />
                  </label>
                  <label>
                    <span>Intended submission date</span>
                    <input
                      type="date"
                      value={profileForm.intended_submission_date ?? ""}
                      onChange={(event) => setProfileForm((current) => ({ ...current, intended_submission_date: event.target.value || null }))}
                    />
                  </label>
                </div>
                <div className="form-grid compact">
                  <label>
                    <span>Reviewed by</span>
                    <input
                      value={profileForm.reviewed_by ?? ""}
                      onChange={(event) => setProfileForm((current) => ({ ...current, reviewed_by: event.target.value || null }))}
                      maxLength={255}
                    />
                  </label>
                  <label>
                    <span>Non-secret note</span>
                    <input
                      value={profileForm.admin_note ?? ""}
                      onChange={(event) => setProfileForm((current) => ({ ...current, admin_note: event.target.value || null }))}
                      maxLength={2000}
                    />
                  </label>
                </div>
                <div className="button-row">
                  <button type="submit" disabled={isSavingProfile}>
                    {isSavingProfile ? "Saving..." : "Save submission profile"}
                  </button>
                </div>
              </div>
            </form>

            <div className="panel inset stack">
              <h4>Human confirmations</h4>
              <p className="subtle">These confirmations represent review steps that Story Engine cannot truthfully complete on its own.</p>
              {(profile?.human_confirmations ?? []).map((item) => (
                <label key={item.key} className="checkbox-row">
                  <input
                    type="checkbox"
                    checked={item.completed}
                    disabled={isSavingConfirmationKey === item.key}
                    onChange={(event) => toggleConfirmation(item, event.target.checked)}
                  />
                  <span>
                    <strong>{item.title}</strong>
                    <br />
                    {item.description}
                  </span>
                </label>
              ))}
            </div>

            <form className="panel inset stack" onSubmit={handleComplianceSave}>
              <h4>Compliance status</h4>
              <p className="subtle">Story Engine cannot infer Google approval from OAuth success, a private upload, or any local test. Audit approval stays blocked until the backend confirms readiness.</p>
              <label>
                <span>Compliance status</span>
                <select
                  value={complianceForm.compliance_status}
                  onChange={(event) =>
                    setComplianceForm((current) => ({
                      ...current,
                      compliance_status: event.target.value as YouTubeProjectComplianceUpdatePayload["compliance_status"],
                    }))
                  }
                >
                  <option value="unknown">Unknown</option>
                  <option value="private_only">Private only</option>
                  <option value="audit_pending">Audit pending</option>
                  <option value="audit_approved" disabled={!canRecordAuditApproved && compliance?.compliance_status !== "audit_approved"}>
                    Audit approved
                  </option>
                </select>
              </label>
              <div className="form-grid compact">
                <label>
                  <span>Submission date</span>
                  <input
                    type="date"
                    value={complianceForm.submission_date ?? ""}
                    onChange={(event) => setComplianceForm((current) => ({ ...current, submission_date: event.target.value || null }))}
                  />
                </label>
                <label>
                  <span>Approval date</span>
                  <input
                    type="date"
                    value={complianceForm.approval_date ?? ""}
                    onChange={(event) => setComplianceForm((current) => ({ ...current, approval_date: event.target.value || null }))}
                  />
                </label>
              </div>
              <label>
                <span>Approval or submission reference</span>
                <input
                  value={complianceForm.case_reference ?? ""}
                  onChange={(event) => setComplianceForm((current) => ({ ...current, case_reference: event.target.value || null }))}
                  maxLength={255}
                />
              </label>
              <label>
                <span>Administrative note</span>
                <textarea
                  value={complianceForm.admin_note ?? ""}
                  onChange={(event) => setComplianceForm((current) => ({ ...current, admin_note: event.target.value || null }))}
                  rows={3}
                  maxLength={2000}
                />
              </label>
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={Boolean(complianceForm.confirm_audit_approved)}
                  onChange={(event) => setComplianceForm((current) => ({ ...current, confirm_audit_approved: event.target.checked }))}
                />
                <span>I understand that Story Engine may record audit approval only after all readiness blockers are resolved.</span>
              </label>
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={Boolean(complianceForm.confirm_google_audit_approval_received)}
                  onChange={(event) => setComplianceForm((current) => ({ ...current, confirm_google_audit_approval_received: event.target.checked }))}
                />
                <span>I confirm that only Google can grant audit approval and that this status is not inferred from Story Engine behaviour.</span>
              </label>
              <div className="button-row">
                <button
                  type="submit"
                  disabled={isSavingCompliance || (complianceForm.compliance_status === "audit_approved" && !canRecordAuditApproved && compliance?.compliance_status !== "audit_approved")}
                >
                  {isSavingCompliance ? "Saving..." : "Save compliance status"}
                </button>
              </div>
            </form>

            <div className="panel inset stack">
              <h4>Requirements by category</h4>
              {groupedRequirements.map(([category, items]) => (
                <div key={category} className="stack compact">
                  <strong>{category}</strong>
                  {items.map((item) => (
                    <div key={item.key} className={`notice-card ${statusClassName(item.status)}`}>
                      <strong>{item.title} ({formatReadinessLabel(item.status)})</strong>
                      <p>{item.description}</p>
                      <p className="subtle">{item.evidence_summary}</p>
                      <p className="subtle">Remediation: {item.remediation_guidance}</p>
                    </div>
                  ))}
                </div>
              ))}
            </div>

            <div className="panel inset stack">
              <h4>Submission package exports</h4>
              <div className="button-row">
                <button type="button" className="secondary" onClick={() => loadSubmissionPackage("json")} disabled={isLoadingPackage}>
                  {isLoadingPackage && exportMode === "json" ? "Loading JSON..." : "View JSON package"}
                </button>
                <button type="button" className="secondary" onClick={() => loadSubmissionPackage("markdown")} disabled={isLoadingPackage}>
                  {isLoadingPackage && exportMode === "markdown" ? "Loading Markdown..." : "View Markdown package"}
                </button>
                <button type="button" className="secondary" onClick={() => loadSubmissionPackage("checklist")} disabled={isLoadingPackage}>
                  {isLoadingPackage && exportMode === "checklist" ? "Loading checklist..." : "View checklist export"}
                </button>
              </div>

              {showExports && exportMode === "json" && submissionPackage ? (
                <div className="stack">
                  <div className="panel-header">
                    <div>
                      <h4>YouTube compliance submission package</h4>
                      <p className="subtle">Generated {formatDateTime(submissionPackage.generated_at)}.</p>
                    </div>
                    <CopyButton text={JSON.stringify(submissionPackage, null, 2)} label="JSON package" />
                  </div>
                  <div className="key-grid">
                    <div><span>Application</span><strong>{String(submissionPackage.executive_summary.application_display_name ?? "Unavailable")}</strong></div>
                    <div><span>Readiness</span><strong>{String(submissionPackage.executive_summary.readiness_status ?? "Unavailable")}</strong></div>
                    <div><span>Blockers</span><strong>{String(submissionPackage.executive_summary.blocker_count ?? "0")}</strong></div>
                  </div>
                  <p>{String(submissionPackage.executive_summary.product_purpose ?? "")}</p>
                  <div className="stack compact">
                    <strong>Evidence manifest</strong>
                    {submissionPackage.evidence_manifest.map((item) => (
                      <div key={item.key} className="notice-card">
                        <strong>{item.title}</strong>
                        <p>{item.why_needed}</p>
                        <p className="subtle">Current state: {item.current_state}</p>
                      </div>
                    ))}
                  </div>
                  <div className="stack compact">
                    <strong>Human completion items</strong>
                    <ul>
                      {submissionPackage.human_completion_items.map((item) => <li key={item}>{item}</li>)}
                    </ul>
                  </div>
                </div>
              ) : null}

              {showExports && exportMode === "markdown" && packageMarkdown ? (
                <div className="stack">
                  <div className="panel-header">
                    <div>
                      <h4>Submission package markdown</h4>
                      <p className="subtle">Human-readable export for manual review.</p>
                    </div>
                    <CopyButton text={packageMarkdown} label="Markdown package" />
                  </div>
                  <pre>{packageMarkdown}</pre>
                </div>
              ) : null}

              {showExports && exportMode === "checklist" && checklistMarkdown ? (
                <div className="stack">
                  <div className="panel-header">
                    <div>
                      <h4>Submission checklist export</h4>
                      <p className="subtle">Concise reviewer checklist.</p>
                    </div>
                    <CopyButton text={checklistMarkdown} label="Checklist markdown" />
                  </div>
                  <pre>{checklistMarkdown}</pre>
                </div>
              ) : null}
            </div>
          </div>
        </details>
      ) : null}

      {canPublish && publishPreviewUrl ? (
        <div className="stack">
          <video className="video-player" controls preload="metadata" src={publishPreviewUrl}>
            Your browser does not support the selected final video preview.
          </video>
          <div className="key-grid">
            <div><span>Frozen asset ID</span><strong>{String(selectedAsset?.id ?? "Unavailable")}</strong></div>
            <div><span>Selection revision</span><strong>{String(finalAssetSelection?.selection_revision ?? "Unavailable")}</strong></div>
            <div><span>Source</span><strong>{String(finalAssetSelection?.source ?? "Unavailable")}</strong></div>
            {job ? <div><span>SHA-256</span><strong>{job.final_asset_sha256}</strong></div> : null}
          </div>
        </div>
      ) : null}

      {!activeConnection && canPublish ? (
        <div className="notice-card warning">
          <strong>Connect YouTube first</strong>
          <p>An active YouTube connection is required before Story Engine can draft or execute a YouTube publication job.</p>
          <button type="button" onClick={handleConnect} disabled={isWorking}>
            {isWorking ? "Opening YouTube..." : "Connect YouTube"}
          </button>
        </div>
      ) : null}

      {activeConnection ? (
        <div className="notice-card">
          <strong>Connected channel</strong>
          <p>{formatConnectionLabel(activeConnection)} <span className="subtle">({activeConnection.external_identity_hint})</span></p>
          <p className="subtle">Token health: {activeConnection.token_health}</p>
        </div>
      ) : null}

      {!job && activeConnection && canPublish ? (
        <form className="stack" onSubmit={handleCreateDraft}>
          <p className="subtle">Private uploads remain available. Unlisted and public stay disabled until audit approval is recorded for this YouTube API project.</p>
          <label>
            <span>Title</span>
            <input
              value={draft.title}
              onChange={(event) => setDraft((current) => ({ ...current, title: event.target.value }))}
              maxLength={100}
            />
          </label>
          <label>
            <span>Description</span>
            <textarea
              value={draft.caption ?? ""}
              onChange={(event) => setDraft((current) => ({ ...current, caption: event.target.value || null }))}
              rows={4}
              maxLength={5000}
            />
          </label>
          <label>
            <span>Tags</span>
            <input
              value={tagsInput}
              onChange={(event) => setTagsInput(event.target.value)}
              placeholder="api, backend, tutorial"
            />
          </label>
          <div className="form-grid compact">
            <label>
              <span>YouTube category ID</span>
              <input
                value={draft.category_id}
                onChange={(event) => setDraft((current) => ({ ...current, category_id: event.target.value }))}
              />
            </label>
            <label>
              <span>Privacy</span>
              <select
                aria-label="Privacy"
                value={draft.privacy}
                onChange={(event) => setDraft((current) => ({ ...current, privacy: event.target.value as PublicationJobDraftPayload["privacy"] }))}
              >
                <option value="private">Private</option>
                <option value="unlisted" disabled={!canUseUnlisted}>Unlisted</option>
                <option value="public" disabled={!canUsePublic}>Public</option>
              </select>
            </label>
          </div>
          {!canUseUnlisted || !canUsePublic ? (
            <p className="subtle">{compliance?.status_explanation ?? "Unlisted and public remain blocked until audit approval is recorded."}</p>
          ) : null}
          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={draft.self_declared_made_for_kids}
              onChange={(event) => setDraft((current) => ({ ...current, self_declared_made_for_kids: event.target.checked }))}
            />
            <span>Made for kids</span>
          </label>
          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={draft.contains_synthetic_media}
              onChange={(event) => setDraft((current) => ({ ...current, contains_synthetic_media: event.target.checked }))}
            />
            <span>Contains synthetic media</span>
          </label>
          <button type="submit" disabled={isSaving}>
            {isSaving ? "Saving draft..." : "Publish to YouTube"}
          </button>
        </form>
      ) : null}

      {job ? (
        <div className="stack">
          <div className="notice-card">
            <strong>Publication status</strong>
            <p>Job status: {job.status.replace(/_/g, " ")}</p>
            {target ? (
              <>
                <p>Target state: {formatTargetState(target)}</p>
                {target.upload_progress_percent != null ? <p>Upload progress: {target.upload_progress_percent}%</p> : null}
                {target.last_error_message ? <p className="error-text">{target.last_error_message}</p> : null}
              </>
            ) : null}
          </div>

          {job.status === "draft" ? (
            <div className="stack">
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={approvalChecked}
                  onChange={(event) => setApprovalChecked(event.target.checked)}
                />
                <span>I reviewed the frozen asset, metadata, visibility, made-for-kids setting, and synthetic-media disclosure for this YouTube upload.</span>
              </label>
              <div className="button-row">
                <button type="button" onClick={() => runJobAction(() => api.approvePublicationJob(job.id))} disabled={!approvalChecked || isWorking}>
                  {isWorking ? "Approving..." : "Approve publication"}
                </button>
                <button type="button" className="secondary" onClick={() => runJobAction(() => api.cancelPublicationJob(job.id))} disabled={isWorking}>
                  Cancel draft
                </button>
              </div>
            </div>
          ) : null}

          {job.available_actions.includes("dispatch") ? (
            <button type="button" onClick={() => runJobAction(() => api.dispatchPublicationJob(job.id))} disabled={isWorking}>
              {isWorking ? "Dispatching..." : "Start YouTube upload"}
            </button>
          ) : null}

          {target?.available_actions.includes("retry") ? (
            <button type="button" className="secondary" onClick={() => runJobAction(() => api.retryPublicationTarget(target.id))} disabled={isWorking}>
              {isWorking ? "Retrying..." : "Retry target"}
            </button>
          ) : null}

          {target?.available_actions.includes("reconcile") ? (
            <button type="button" className="secondary" onClick={() => runJobAction(() => api.reconcilePublicationTarget(target.id))} disabled={isWorking}>
              {isWorking ? "Reconciling..." : "Reconcile target"}
            </button>
          ) : null}

          {target?.state === "uploaded_private" ? (
            <div className="notice-card warning">
              <strong>Uploaded privately</strong>
              <p>The Google project still resulted in a private upload. Story Engine did not create a PlatformPost because the video is not publicly attributable yet.</p>
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
