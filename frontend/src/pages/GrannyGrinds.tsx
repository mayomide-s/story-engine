import { FormEvent, useEffect, useMemo, useState } from "react";

import {
  api,
  GrannyCharacter,
  GrannyGrindJob,
  GrannyGrindRightsStatus,
} from "../api/client";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api";
const BACKEND_BASE = API_BASE.replace(/\/api\/?$/, "");

const ACTIVE_STATUSES = new Set(["queued", "ingesting", "submitted", "generating", "postprocessing", "publishing"]);
const REVIEWED_STATUSES = new Set(["approved", "published"]);
const FIRST_BATCH_TARGET = 10;

function mediaUrl(value?: string | null) {
  if (!value) return "";
  if (/^https?:\/\//i.test(value)) return value;
  if (value.startsWith("/")) return `${BACKEND_BASE}${value}`;
  return value;
}

function statusTone(status: string) {
  if (["approved", "published"].includes(status)) return "success";
  if (["failed", "rejected"].includes(status)) return "danger";
  if (status === "needs_review") return "warning";
  return "";
}

function formatStatus(status: string) {
  return status.replace(/_/g, " ");
}

function formatNumber(value: unknown, digits = 0) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  return number.toFixed(digits);
}

function qcItems(job: GrannyGrindJob) {
  const qc = job.qc_json ?? {};
  return [
    ["Resolution", qc.resolution_match, "same width × height"],
    ["Duration", qc.duration_match, `Δ ${formatNumber(qc.duration_delta_seconds, 3)}s`],
    ["Frame rate", qc.fps_match, `Δ ${formatNumber(qc.fps_delta, 3)} fps`],
    ["Original audio", qc.audio_preserved, qc.original_audio_present ? "restored from source" : "source had no audio"],
  ] as Array<[string, unknown, string]>;
}

export function GrannyGrindsPage() {
  const [jobs, setJobs] = useState<GrannyGrindJob[]>([]);
  const [characters, setCharacters] = useState<GrannyCharacter[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [sourcePostUrl, setSourcePostUrl] = useState("");
  const [sourceMediaUrl, setSourceMediaUrl] = useState("");
  const [sourceCreatorHandle, setSourceCreatorHandle] = useState("");
  const [sourceCreditText, setSourceCreditText] = useState("");
  const [rightsStatus, setRightsStatus] = useState<GrannyGrindRightsStatus>("credited");
  const [confirmPaidGeneration, setConfirmPaidGeneration] = useState(false);
  const [reviewNotes, setReviewNotes] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  async function refresh() {
    const [jobData, characterData] = await Promise.all([
      api.listGrannyGrindJobs(),
      api.listGrannyCharacters(),
    ]);
    setJobs(jobData);
    setCharacters(characterData);
    setSelectedId((current) => current || jobData[0]?.id || "");
  }

  useEffect(() => {
    refresh().catch((requestError: Error) => setError(requestError.message));
  }, []);

  const hasActiveJobs = jobs.some((job) => ACTIVE_STATUSES.has(job.status));

  useEffect(() => {
    if (!hasActiveJobs) return;
    const timer = window.setInterval(() => {
      refresh().catch(() => undefined);
    }, 10000);
    return () => window.clearInterval(timer);
  }, [hasActiveJobs]);

  const selected = useMemo(
    () => jobs.find((job) => job.id === selectedId) ?? jobs[0] ?? null,
    [jobs, selectedId],
  );

  const reviewedCount = jobs.filter((job) => REVIEWED_STATUSES.has(job.status)).length;
  const progressCount = Math.min(reviewedCount, FIRST_BATCH_TARGET);
  const nextCharacter = characters.length ? characters[jobs.length % characters.length] : null;

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!confirmPaidGeneration) {
      setError("Confirm the paid Aleph generation before creating the clip.");
      return;
    }
    try {
      setBusy("create");
      setError("");
      const created = await api.createGrannyGrindJob({
        source_post_url: sourcePostUrl.trim(),
        source_media_url: sourceMediaUrl.trim(),
        source_creator_handle: sourceCreatorHandle.trim() || null,
        source_credit_text: sourceCreditText.trim() || null,
        rights_status: rightsStatus,
        confirm_paid_generation: true,
      });
      setJobs((current) => [created, ...current]);
      setSelectedId(created.id);
      setSourcePostUrl("");
      setSourceMediaUrl("");
      setSourceCreatorHandle("");
      setSourceCreditText("");
      setConfirmPaidGeneration(false);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Could not create GrannyGrinds clip.");
    } finally {
      setBusy("");
    }
  }

  async function handleReview(decision: "approve" | "reject") {
    if (!selected) return;
    try {
      setBusy(decision);
      setError("");
      const updated = decision === "approve"
        ? await api.approveGrannyGrindJob(selected.id, reviewNotes)
        : await api.rejectGrannyGrindJob(selected.id, reviewNotes);
      setJobs((current) => current.map((job) => job.id === updated.id ? updated : job));
      setReviewNotes("");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Review action failed.");
    } finally {
      setBusy("");
    }
  }

  async function handlePublish() {
    if (!selected) return;
    try {
      setBusy("publish");
      setError("");
      const updated = await api.publishGrannyGrindJob(selected.id);
      setJobs((current) => current.map((job) => job.id === updated.id ? updated : job));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Instagram publish failed.");
    } finally {
      setBusy("");
    }
  }

  return (
    <div className="page stack">
      <section className="panel granny-hero">
        <div className="panel-header">
          <div>
            <p className="eyebrow">GrannyGrinds</p>
            <h2>Same skate clip. Different skater.</h2>
            <p className="subtle">
              First batch is deliberately review-gated: source motion, camera, board, environment and original audio stay intact.
            </p>
          </div>
          <div className="granny-progress">
            <strong>{progressCount}/{FIRST_BATCH_TARGET}</strong>
            <span>approved clips</span>
          </div>
        </div>
        <div className="granny-progress-track" aria-label={`${progressCount} of ${FIRST_BATCH_TARGET} first-batch clips approved`}>
          <span style={{ width: `${(progressCount / FIRST_BATCH_TARGET) * 100}%` }} />
        </div>
      </section>

      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="eyebrow">New source</p>
            <h2>Add a skate clip</h2>
          </div>
          {nextCharacter ? (
            <span className="status-pill">Next: {nextCharacter.name}</span>
          ) : null}
        </div>

        <form className="stack" onSubmit={handleCreate}>
          <div className="form-grid">
            <label className="field field-wide">
              <span>Original post URL</span>
              <input
                required
                type="url"
                value={sourcePostUrl}
                onChange={(event) => setSourcePostUrl(event.target.value)}
                placeholder="https://www.instagram.com/reel/..."
              />
            </label>
            <label className="field field-wide">
              <span>Direct source video URL</span>
              <input
                required
                type="url"
                value={sourceMediaUrl}
                onChange={(event) => setSourceMediaUrl(event.target.value)}
                placeholder="https://.../clip.mp4"
              />
              <small className="subtle">For the first 10, paste a direct downloadable MP4/HTTPS media URL. Discovery comes after quality is proven.</small>
            </label>
            <label className="field">
              <span>Creator / source handle</span>
              <input
                value={sourceCreatorHandle}
                onChange={(event) => setSourceCreatorHandle(event.target.value)}
                placeholder="@skater"
              />
            </label>
            <label className="field">
              <span>Source record</span>
              <select value={rightsStatus} onChange={(event) => setRightsStatus(event.target.value as GrannyGrindRightsStatus)}>
                <option value="credited">Credited source</option>
                <option value="permission_confirmed">Permission confirmed</option>
                <option value="unreviewed">Unreviewed</option>
              </select>
            </label>
            <label className="field field-wide">
              <span>Credit text</span>
              <input
                value={sourceCreditText}
                onChange={(event) => setSourceCreditText(event.target.value)}
                placeholder="Original clip: @skater / filmed by @filmer"
              />
            </label>
          </div>

          <label className="toggle-chip paid-confirmation">
            <input
              type="checkbox"
              checked={confirmPaidGeneration}
              onChange={(event) => setConfirmPaidGeneration(event.target.checked)}
            />
            <span>I want to submit this source to paid Runway Aleph 2.0 generation.</span>
          </label>

          <div className="button-row">
            <button type="submit" disabled={busy === "create" || !confirmPaidGeneration}>
              {busy === "create" ? "Submitting…" : "Create GrannyGrind"}
            </button>
            <button type="button" className="secondary" onClick={() => refresh().catch((requestError: Error) => setError(requestError.message))}>
              Refresh queue
            </button>
          </div>
        </form>
        {error ? <div className="notice-card danger"><strong>Action failed</strong><p>{error}</p></div> : null}
      </section>

      <section className="granny-character-grid">
        {characters.map((character) => (
          <article className="panel granny-character-card" key={character.key}>
            <div className="panel-header">
              <div>
                <p className="eyebrow">Granny {character.rotation_order}</p>
                <h3>{character.name}</h3>
              </div>
              <span className="status-pill muted">fixed look</span>
            </div>
            <p>{character.wardrobe}</p>
          </article>
        ))}
      </section>

      <section className="grid granny-workspace">
        <div className="panel scroll-panel granny-job-list">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Queue</p>
              <h2>{jobs.length} clips</h2>
            </div>
          </div>
          <div className="list">
            {jobs.map((job) => (
              <button
                type="button"
                key={job.id}
                className={`run-card run-card-button ${selected?.id === job.id ? "active" : ""}`}
                onClick={() => setSelectedId(job.id)}
              >
                <div className="run-card-toolbar panel-header">
                  <strong>{job.granny_name}</strong>
                  <span className={`status-pill ${statusTone(job.status)}`}>{formatStatus(job.status)}</span>
                </div>
                <span className="subtle">{job.source_creator_handle || "source handle not set"}</span>
                <span className="subtle">{new Date(job.created_at).toLocaleString()}</span>
              </button>
            ))}
            {!jobs.length ? <p className="subtle">No GrannyGrinds clips yet.</p> : null}
          </div>
        </div>

        <div className="stack">
          {selected ? (
            <>
              <section className="panel">
                <div className="panel-header">
                  <div>
                    <p className="eyebrow">Selected clip</p>
                    <h2>{selected.granny_name}</h2>
                  </div>
                  <span className={`status-pill ${statusTone(selected.status)}`}>{formatStatus(selected.status)}</span>
                </div>
                <div className="key-grid">
                  <div><span>Granny</span><strong>{selected.granny_name}</strong></div>
                  <div><span>Source</span><strong>{selected.source_creator_handle || "—"}</strong></div>
                  <div><span>Rights record</span><strong>{formatStatus(selected.rights_status)}</strong></div>
                  <div><span>Runway task</span><strong>{selected.runway_task_id ? "submitted" : "—"}</strong></div>
                </div>
                <div className="link-row">
                  <a className="inline-link" href={selected.source_post_url} target="_blank" rel="noreferrer">Open original post</a>
                  {selected.instagram_permalink ? (
                    <a className="inline-link" href={selected.instagram_permalink} target="_blank" rel="noreferrer">Open published Reel</a>
                  ) : null}
                </div>
                {selected.last_error ? (
                  <div className="notice-card danger">
                    <strong>Pipeline error</strong>
                    <p>{selected.last_error}</p>
                  </div>
                ) : null}
              </section>

              <section className="panel">
                <div className="panel-header">
                  <div>
                    <p className="eyebrow">Reference comparison</p>
                    <h2>Source vs Granny</h2>
                  </div>
                  <span className="status-pill muted">original audio retained</span>
                </div>
                <div className="granny-video-grid">
                  <div className="stack">
                    <strong>Source</strong>
                    <video className="video-player large" controls playsInline src={mediaUrl(selected.source_public_url || selected.source_media_url)} />
                  </div>
                  <div className="stack">
                    <strong>Transformed</strong>
                    {selected.transformed_public_url ? (
                      <video className="video-player large" controls playsInline src={mediaUrl(selected.transformed_public_url)} />
                    ) : (
                      <div className="granny-video-placeholder">
                        <span>{ACTIVE_STATUSES.has(selected.status) ? "Generating granny…" : "No transformed video yet"}</span>
                      </div>
                    )}
                  </div>
                </div>
              </section>

              {Object.keys(selected.qc_json ?? {}).length ? (
                <section className="panel">
                  <div className="panel-header">
                    <div>
                      <p className="eyebrow">Preservation QA</p>
                      <h2>Structural checks</h2>
                    </div>
                    <span className={`status-pill ${selected.qc_json.structural_pass ? "success" : "danger"}`}>
                      {selected.qc_json.structural_pass ? "pass" : "fail"}
                    </span>
                  </div>
                  <div className="quality-list">
                    {qcItems(selected).map(([label, passed, note]) => (
                      <div className={`quality-item ${passed ? "pass" : "fail"}`} key={label}>
                        <div>
                          <strong>{label}</strong>
                          <p className="subtle">{note}</p>
                        </div>
                        <span className={`status-pill ${passed ? "success" : "danger"}`}>{passed ? "pass" : "fail"}</span>
                      </div>
                    ))}
                  </div>
                  <div className="notice-card warning">
                    <strong>Human visual check is mandatory</strong>
                    <p>Confirm the skater is the only changed person, the board/contact points are intact, trick timing matches, and the scene/camera did not drift.</p>
                  </div>
                </section>
              ) : null}

              {selected.status === "needs_review" ? (
                <section className="panel">
                  <p className="eyebrow">Human review</p>
                  <h2>Would you post this?</h2>
                  <label className="field">
                    <span>Review notes</span>
                    <textarea
                      value={reviewNotes}
                      onChange={(event) => setReviewNotes(event.target.value)}
                      placeholder="Board stayed clean; face and cardigan consistent; no background drift…"
                    />
                  </label>
                  <div className="button-row">
                    <button
                      type="button"
                      onClick={() => handleReview("approve")}
                      disabled={Boolean(busy) || selected.qc_json.structural_pass !== true}
                    >
                      {busy === "approve" ? "Approving…" : "Approve clip"}
                    </button>
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => handleReview("reject")}
                      disabled={Boolean(busy)}
                    >
                      {busy === "reject" ? "Rejecting…" : "Reject"}
                    </button>
                  </div>
                </section>
              ) : null}

              {selected.status === "approved" ? (
                <section className="panel">
                  <div className="notice-card warning">
                    <strong>First-10 publishing gate</strong>
                    <p>Instagram API publishing is wired, but auto-publish stays off. Add the photorealistic AI Info disclosure in Instagram until we verify an API-supported disclosure flag.</p>
                  </div>
                  <button type="button" onClick={handlePublish} disabled={Boolean(busy)}>
                    {busy === "publish" ? "Publishing…" : "Publish approved Reel"}
                  </button>
                </section>
              ) : null}
            </>
          ) : (
            <section className="panel">
              <p className="subtle">Add the first source clip to start GrannyGrinds.</p>
            </section>
          )}
        </div>
      </section>
    </div>
  );
}
