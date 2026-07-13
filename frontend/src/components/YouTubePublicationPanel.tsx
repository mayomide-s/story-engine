import { FormEvent, useEffect, useMemo, useState } from "react";

import {
  api,
  FinalAssetSelection,
  PublicationJob,
  PublicationJobDraftPayload,
  PublicationTarget,
  SocialConnectionSummary,
  YouTubeAuditReadinessReport,
  YouTubeProjectCompliance,
  YouTubeProjectComplianceUpdatePayload,
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
  };
}

function formatComplianceLabel(status: YouTubeProjectCompliance["compliance_status"] | string) {
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

function formatSectionStatus(status: string) {
  return status.replace(/_/g, " ");
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
  const [report, setReport] = useState<YouTubeAuditReadinessReport | null>(null);
  const [reportMarkdown, setReportMarkdown] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isWorking, setIsWorking] = useState(false);
  const [isSavingCompliance, setIsSavingCompliance] = useState(false);
  const [isLoadingReport, setIsLoadingReport] = useState(false);
  const [error, setError] = useState("");
  const [approvalChecked, setApprovalChecked] = useState(false);
  const [showReport, setShowReport] = useState(false);
  const [reportMode, setReportMode] = useState<"json" | "markdown">("json");
  const [draft, setDraft] = useState<PublicationJobDraftPayload>(() => defaultDraftPayload(finalAssetSelection, manualPostPackage ?? null));
  const [tagsInput, setTagsInput] = useState(() => defaultDraftPayload(finalAssetSelection, manualPostPackage ?? null).tags.join(", "));
  const [complianceForm, setComplianceForm] = useState<YouTubeProjectComplianceUpdatePayload>(() => defaultCompliancePayload(null));

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
  const complianceBadge = formatComplianceLabel(compliance?.compliance_status ?? "private_only");

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
    let cancelled = false;
    async function load() {
      setIsLoading(true);
      try {
        const [connectionResponse, latestJob, complianceResponse] = await Promise.all([
          api.listSocialConnections(),
          api.getLatestPublicationJobForRun(runId).catch((requestError: Error) => {
            if (requestError.message === "Publication job not found") {
              return null;
            }
            throw requestError;
          }),
          api.getYouTubeProjectCompliance(),
        ]);
        if (cancelled) return;
        setConnections(connectionResponse.items);
        setJob(latestJob);
        setCompliance(complianceResponse);
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
      setReport(null);
      setReportMarkdown("");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to update YouTube compliance status.");
    } finally {
      setIsSavingCompliance(false);
    }
  }

  async function loadAuditReport(mode: "json" | "markdown") {
    setIsLoadingReport(true);
    setError("");
    setShowReport(true);
    setReportMode(mode);
    try {
      if (mode === "markdown") {
        setReportMarkdown(await api.getYouTubeAuditReadinessReportMarkdown());
      } else {
        setReport(await api.getYouTubeAuditReadinessReport());
      }
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to load the YouTube audit-readiness report.");
    } finally {
      setIsLoadingReport(false);
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
        <div className={`notice-card ${compliance.compliance_status === "audit_approved" ? "" : "warning"}`}>
          <strong>YouTube compliance status: {complianceBadge}</strong>
          <p>{compliance.status_explanation}</p>
          <div className="key-grid">
            <div><span>Status updated</span><strong>{formatDateTime(compliance.status_updated_at)}</strong></div>
            <div><span>Submission date</span><strong>{compliance.submission_date ?? "Not recorded"}</strong></div>
            <div><span>Approval date</span><strong>{compliance.approval_date ?? "Not recorded"}</strong></div>
            <div><span>Reference</span><strong>{compliance.case_reference ?? "Not recorded"}</strong></div>
          </div>
        </div>
      ) : null}

      {canPublish ? (
        <details className="technical-disclosure">
          <summary>YouTube audit readiness</summary>
          <div className="stack compact">
            <form className="stack" onSubmit={handleComplianceSave}>
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
                  <option value="audit_approved">Audit approved</option>
                </select>
              </label>
              <div className="form-grid compact">
                <label>
                  <span>Submission date</span>
                  <input
                    type="date"
                    value={complianceForm.submission_date ?? ""}
                    onChange={(event) =>
                      setComplianceForm((current) => ({
                        ...current,
                        submission_date: event.target.value || null,
                      }))
                    }
                  />
                </label>
                <label>
                  <span>Approval date</span>
                  <input
                    type="date"
                    value={complianceForm.approval_date ?? ""}
                    onChange={(event) =>
                      setComplianceForm((current) => ({
                        ...current,
                        approval_date: event.target.value || null,
                      }))
                    }
                  />
                </label>
              </div>
              <label>
                <span>Case or reference ID</span>
                <input
                  value={complianceForm.case_reference ?? ""}
                  onChange={(event) =>
                    setComplianceForm((current) => ({
                      ...current,
                      case_reference: event.target.value || null,
                    }))
                  }
                  maxLength={255}
                />
              </label>
              <label>
                <span>Administrative note</span>
                <textarea
                  value={complianceForm.admin_note ?? ""}
                  onChange={(event) =>
                    setComplianceForm((current) => ({
                      ...current,
                      admin_note: event.target.value || null,
                    }))
                  }
                  rows={3}
                  maxLength={2000}
                />
              </label>
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={Boolean(complianceForm.confirm_audit_approved)}
                  onChange={(event) =>
                    setComplianceForm((current) => ({
                      ...current,
                      confirm_audit_approved: event.target.checked,
                    }))
                  }
                />
                <span>I confirm that YouTube compliance approval has been granted for this Google API project.</span>
              </label>
              <div className="button-row">
                <button type="submit" disabled={isSavingCompliance}>
                  {isSavingCompliance ? "Saving..." : "Save compliance status"}
                </button>
                <button type="button" className="secondary" onClick={() => loadAuditReport("json")} disabled={isLoadingReport}>
                  {isLoadingReport && reportMode === "json" ? "Loading report..." : "View audit report"}
                </button>
                <button type="button" className="secondary" onClick={() => loadAuditReport("markdown")} disabled={isLoadingReport}>
                  {isLoadingReport && reportMode === "markdown" ? "Loading markdown..." : "Load markdown export"}
                </button>
              </div>
            </form>

            {showReport && reportMode === "json" && report ? (
              <div className="panel inset stack">
                <div className="panel-header">
                  <div>
                    <h4>YouTube audit-readiness report</h4>
                    <p className="subtle">Generated {formatDateTime(report.generated_at)}.</p>
                  </div>
                  <CopyButton text={JSON.stringify(report, null, 2)} label="JSON report" />
                </div>
                <div className="key-grid">
                  <div><span>Application</span><strong>{report.application_name}</strong></div>
                  <div><span>Status</span><strong>{formatComplianceLabel(report.current_compliance_status)}</strong></div>
                  <div><span>Version</span><strong>{report.application_version ?? "Unavailable"}</strong></div>
                </div>
                <p>{report.application_purpose}</p>
                <div className="stack compact">
                  <strong>OAuth scopes</strong>
                  {report.scope_justifications.map((item) => (
                    <p key={item.scope}><code>{item.scope}</code> - {item.required_for}</p>
                  ))}
                </div>
                {report.sections.map((section) => (
                  <div key={section.key} className="notice-card">
                    <strong>{section.title}</strong>
                    <p>{section.summary}</p>
                    <p className="subtle">Status: {formatSectionStatus(section.status)}</p>
                    <ul>
                      {section.bullets.map((bullet) => <li key={bullet}>{bullet}</li>)}
                    </ul>
                  </div>
                ))}
              </div>
            ) : null}

            {showReport && reportMode === "markdown" && reportMarkdown ? (
              <div className="panel inset stack">
                <div className="panel-header">
                  <div>
                    <h4>YouTube audit-readiness markdown</h4>
                    <p className="subtle">Markdown export from the backend report endpoint.</p>
                  </div>
                  <CopyButton text={reportMarkdown} label="markdown report" />
                </div>
                <pre>{reportMarkdown}</pre>
              </div>
            ) : null}
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
          <p>{formatConnectionLabel(activeConnection)}</p>
          <small>{activeConnection.external_identity_hint}</small>
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
              onChange={(event) => setDraft((current) => ({ ...current, caption: event.target.value }))}
              rows={5}
              maxLength={5000}
            />
          </label>
          <label>
            <span>Tags</span>
            <input
              value={tagsInput}
              onChange={(event) => setTagsInput(event.target.value)}
              placeholder="api, backend, frontend"
            />
          </label>
          <div className="form-grid compact">
            <label>
              <span>Category</span>
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
            <p>Job: {job.status.replace(/_/g, " ")}</p>
          </div>
          {target ? (
            <div className="panel inset">
              <div className="key-grid">
                <div><span>Target state</span><strong>{formatTargetState(target)}</strong></div>
                <div><span>Requested visibility</span><strong>{target.visibility}</strong></div>
                <div><span>Actual visibility</span><strong>{target.actual_visibility ?? "Unavailable"}</strong></div>
                <div><span>Attempt count</span><strong>{String(target.attempt_count)}</strong></div>
                <div><span>Video ID</span><strong>{target.provider_video_id ?? "Unavailable"}</strong></div>
                <div><span>PlatformPost</span><strong>{target.platform_post_id ?? "Not created"}</strong></div>
              </div>
              {typeof target.upload_progress_percent === "number" ? (
                <p className="subtle">Upload progress: {target.upload_progress_percent}%</p>
              ) : null}
              {target.public_post_url ? (
                <p>
                  <a href={target.public_post_url} target="_blank" rel="noreferrer">Open canonical YouTube URL</a>
                </p>
              ) : null}
              {target.last_error_message ? <p className="error-text">{target.last_error_message}</p> : null}
            </div>
          ) : null}

          {job.status === "draft" ? (
            <div className="stack">
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={approvalChecked}
                  onChange={(event) => setApprovalChecked(event.target.checked)}
                />
                <span>I approve publication of this frozen final video with the reviewed YouTube metadata.</span>
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
              <p>Google may have forced this upload to remain private. Story Engine will not create a PlatformPost until YouTube confirms unlisted or public visibility.</p>
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
