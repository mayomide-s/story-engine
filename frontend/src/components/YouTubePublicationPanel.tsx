import { FormEvent, useEffect, useMemo, useState } from "react";

import {
  api,
  FinalAssetSelection,
  PublicationJob,
  PublicationJobDraftPayload,
  PublicationTarget,
  SocialConnectionSummary,
} from "../api/client";

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

type Props = {
  runId: string;
  runStatus: string;
  finalAssetSelection: FinalAssetSelection | null;
  manualPostPackage?: Record<string, unknown> | null;
};

export function YouTubePublicationPanel({ runId, runStatus, finalAssetSelection, manualPostPackage }: Props) {
  const [connections, setConnections] = useState<SocialConnectionSummary[]>([]);
  const [job, setJob] = useState<PublicationJob | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isWorking, setIsWorking] = useState(false);
  const [error, setError] = useState("");
  const [approvalChecked, setApprovalChecked] = useState(false);
  const [draft, setDraft] = useState<PublicationJobDraftPayload>(() => defaultDraftPayload(finalAssetSelection, manualPostPackage ?? null));
  const [tagsInput, setTagsInput] = useState(() => defaultDraftPayload(finalAssetSelection, manualPostPackage ?? null).tags.join(", "));

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

  useEffect(() => {
    const nextDefault = defaultDraftPayload(finalAssetSelection, manualPostPackage ?? null);
    setDraft((current) => job ? current : nextDefault);
    setTagsInput((current) => job ? current : nextDefault.tags.join(", "));
  }, [finalAssetSelection, manualPostPackage, job]);

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
      {isLoading ? <p className="subtle">Loading YouTube publication state…</p> : null}

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
            {isWorking ? "Opening YouTube…" : "Connect YouTube"}
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
          <p className="subtle">An unverified Google project may force a requested unlisted or public upload to remain private.</p>
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
                value={draft.privacy}
                onChange={(event) => setDraft((current) => ({ ...current, privacy: event.target.value as PublicationJobDraftPayload["privacy"] }))}
              >
                <option value="private">Private</option>
                <option value="unlisted">Unlisted</option>
                <option value="public">Public</option>
              </select>
            </label>
          </div>
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
            {isSaving ? "Saving draft…" : "Publish to YouTube"}
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
                  {isWorking ? "Approving…" : "Approve publication"}
                </button>
                <button type="button" className="secondary" onClick={() => runJobAction(() => api.cancelPublicationJob(job.id))} disabled={isWorking}>
                  Cancel draft
                </button>
              </div>
            </div>
          ) : null}

          {job.available_actions.includes("dispatch") ? (
            <button type="button" onClick={() => runJobAction(() => api.dispatchPublicationJob(job.id))} disabled={isWorking}>
              {isWorking ? "Dispatching…" : "Start YouTube upload"}
            </button>
          ) : null}

          {target?.available_actions.includes("retry") ? (
            <button type="button" className="secondary" onClick={() => runJobAction(() => api.retryPublicationTarget(target.id))} disabled={isWorking}>
              {isWorking ? "Retrying…" : "Retry target"}
            </button>
          ) : null}

          {target?.available_actions.includes("reconcile") ? (
            <button type="button" className="secondary" onClick={() => runJobAction(() => api.reconcilePublicationTarget(target.id))} disabled={isWorking}>
              {isWorking ? "Reconciling…" : "Reconcile target"}
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
