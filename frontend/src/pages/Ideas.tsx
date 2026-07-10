import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api, PipelineRunDetail, PipelineRunSummary } from "../api/client";

const STYLE_PRESETS = [
  "clean_3d_cartoon",
  "neon_club_metaphor",
  "whiteboard_character",
  "bug_monster",
  "office_comedy",
];

type SceneDraft = {
  time: string;
  visual: string;
  dialogue: string;
  on_screen_text: string;
  motion_camera: string;
};

const REVIEW_SECTION_LABELS: Record<string, string> = {
  concept_clarity: "Concept Clarity",
  hook_strength: "Hook Strength",
  visual_metaphor: "Visual Metaphor",
  scene_timing: "Scene Timing",
  final_cta: "Final CTA",
  caption_strength: "Caption Strength",
  risk_issues: "Risk / Issues",
};

function toSceneDrafts(script: Record<string, unknown> | null): SceneDraft[] {
  const rawScenes = Array.isArray(script?.script_json && typeof script.script_json === "object"
    ? (script.script_json as Record<string, unknown>).scenes
    : [])
    ? ((script?.script_json as Record<string, unknown>).scenes as Record<string, unknown>[])
    : [];
  return rawScenes.map((scene) => ({
    time: String(scene.time ?? ""),
    visual: String(scene.visual ?? ""),
    dialogue: String(scene.dialogue ?? ""),
    on_screen_text: String(scene.on_screen_text ?? ""),
    motion_camera: String(scene.motion_camera ?? ""),
  }));
}

function toStoryboardFrames(scenes: SceneDraft[]) {
  return {
    storyboard_frames: scenes.map((scene, index) => ({
      frame: index + 1,
      description: scene.visual,
      on_screen_text: scene.on_screen_text,
      motion_camera: scene.motion_camera,
    })),
  };
}

export function IdeasPage() {
  const [searchParams] = useSearchParams();
  const [runs, setRuns] = useState<PipelineRunSummary[]>([]);
  const [detail, setDetail] = useState<PipelineRunDetail | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string>("");
  const [ideaTitle, setIdeaTitle] = useState("");
  const [ideaHook, setIdeaHook] = useState("");
  const [sceneDrafts, setSceneDrafts] = useState<SceneDraft[]>([]);
  const [captionOverride, setCaptionOverride] = useState("");
  const [hashtagsText, setHashtagsText] = useState("");
  const [stylePreset, setStylePreset] = useState("clean_3d_cartoon");
  const [endingFrameGuidance, setEndingFrameGuidance] = useState("");
  const [reviewSections, setReviewSections] = useState<Record<string, string>>({});
  const [promptOverride, setPromptOverride] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [isRefreshingText, setIsRefreshingText] = useState(false);
  const [isPromptWorking, setIsPromptWorking] = useState<"" | "improve" | "shorten">("");
  const [error, setError] = useState("");

  useEffect(() => {
    const requestedRunId = searchParams.get("run");
    api.listRuns()
      .then((data) => {
        setRuns(data);
        setError("");
        if (requestedRunId && data.some((run) => run.id === requestedRunId)) {
          setSelectedRunId(requestedRunId);
        } else if (data[0]) {
          setSelectedRunId(data[0].id);
        }
      })
      .catch((requestError: Error) => setError(requestError.message));
  }, [searchParams]);

  useEffect(() => {
    if (!selectedRunId) {
      return;
    }
    api.getRun(selectedRunId)
      .then((payload) => {
        setDetail(payload);
        const idea = payload.idea as Record<string, unknown> | null;
        const run = payload.pipeline_run as Record<string, unknown> | null;
        const inputConfig = run?.input_config_json && typeof run.input_config_json === "object"
          ? run.input_config_json as Record<string, unknown>
          : {};
        setIdeaTitle(String(idea?.title ?? ""));
        setIdeaHook(String(idea?.hook ?? ""));
        setSceneDrafts(toSceneDrafts(payload.script));
        setPromptOverride(String(run?.prompt_override ?? ""));
        setCaptionOverride(String(run?.caption_override ?? ""));
        setStylePreset(String(run?.style_preset ?? "clean_3d_cartoon"));
        setEndingFrameGuidance(String(inputConfig.ending_frame_guidance ?? ""));
        setReviewSections((payload.review_sections ?? {}) as Record<string, string>);
        setHashtagsText(Array.isArray(inputConfig.hashtag_set) ? inputConfig.hashtag_set.join(" ") : "");
        setError("");
      })
      .catch((requestError: Error) => setError(requestError.message));
  }, [selectedRunId]);

  async function refreshRun(payload: PipelineRunDetail) {
    setDetail(payload);
    const run = payload.pipeline_run as Record<string, unknown> | null;
    const inputConfig = run?.input_config_json && typeof run.input_config_json === "object"
      ? run.input_config_json as Record<string, unknown>
      : {};
    setPromptOverride(String(run?.prompt_override ?? ""));
    setCaptionOverride(String(run?.caption_override ?? ""));
    setSceneDrafts(toSceneDrafts(payload.script));
    setReviewSections((payload.review_sections ?? {}) as Record<string, string>);
    setHashtagsText(Array.isArray(inputConfig.hashtag_set) ? inputConfig.hashtag_set.join(" ") : "");
    setEndingFrameGuidance(String(inputConfig.ending_frame_guidance ?? ""));
  }

  function updateScene(index: number, key: keyof SceneDraft, value: string) {
    setSceneDrafts((current) => current.map((scene, sceneIndex) => (sceneIndex === index ? { ...scene, [key]: value } : scene)));
  }

  async function handleSaveEdits() {
    if (!selectedRunId || !detail?.idea || !detail?.script) return;
    try {
      setIsSaving(true);
      setError("");
      const script = detail.script as Record<string, unknown>;
      const scriptJson = script?.script_json && typeof script.script_json === "object"
        ? script.script_json as Record<string, unknown>
        : {};
      await api.patchIdea(selectedRunId, { title: ideaTitle, hook: ideaHook });
      await api.patchScript(selectedRunId, {
        hook: ideaHook,
        script_json: {
          ...scriptJson,
          hook: ideaHook,
          final_tag: endingFrameGuidance || scriptJson.final_tag,
          scenes: sceneDrafts,
        },
      });
      await api.patchStoryboard(selectedRunId, { frames_json: toStoryboardFrames(sceneDrafts) });
      const updated = await api.patchReviewConfig(selectedRunId, {
        prompt_override: promptOverride || null,
        caption_override: captionOverride,
        style_preset: stylePreset,
        hashtag_set: hashtagsText.split(/\s+/).filter(Boolean),
        ending_frame_guidance: endingFrameGuidance,
        review_sections: reviewSections,
      });
      await refreshRun(updated);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to save review edits.");
    } finally {
      setIsSaving(false);
    }
  }

  async function handleRegenerateTextOnly() {
    if (!selectedRunId) return;
    try {
      setIsRefreshingText(true);
      setError("");
      const updated = await api.regenerateRunText(selectedRunId, "Refresh text-only review pass");
      setIdeaTitle(String((updated.idea as Record<string, unknown> | null)?.title ?? ""));
      setIdeaHook(String((updated.idea as Record<string, unknown> | null)?.hook ?? ""));
      await refreshRun(updated);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to regenerate text.");
    } finally {
      setIsRefreshingText(false);
    }
  }

  async function handlePromptAction(action: "improve" | "shorten") {
    if (!selectedRunId) return;
    try {
      setIsPromptWorking(action);
      setError("");
      const updated = await api.runPromptAction(selectedRunId, action);
      await refreshRun(updated);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to update prompt preview.");
    } finally {
      setIsPromptWorking("");
    }
  }

  const idea = detail?.idea as Record<string, unknown> | null;
  const storyboard = detail?.storyboard as Record<string, unknown> | null;
  const critique = detail?.content_critique ?? null;
  const storyAdherence = detail?.story_adherence_review as Record<string, unknown> | null;
  const promptPreview = useMemo(() => promptOverride.trim() || String(detail?.prompt_preview ?? ""), [detail?.prompt_preview, promptOverride]);
  const promptLength = detail?.review_preflight?.prompt_length;
  const preflightScores = detail?.review_preflight?.scores ?? {};
  const preflightSummary = detail?.review_preflight?.summary ?? "";
  const preflightLow = Boolean(detail?.review_preflight?.low_score_warning);
  const promptTooLong = Boolean(promptLength?.too_long);
  const currentRunStatus = String((detail?.pipeline_run as Record<string, unknown> | null)?.status ?? "");
  const existingProviderJob = Boolean((detail?.video as Record<string, unknown> | null)?.provider_job_id);
  const editingLocked = existingProviderJob || ["completed", "failed", "cancelled"].includes(currentRunStatus);

  const storyboardFrames = Array.isArray((storyboard?.frames_json as { storyboard_frames?: unknown[] } | undefined)?.storyboard_frames)
    ? (((storyboard?.frames_json as { storyboard_frames?: unknown[] }).storyboard_frames ?? []) as Record<string, unknown>[])
    : [];

  return (
    <div className="page stack">
      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Ideas</p>
            <h2>Shape the story before generating the video.</h2>
          </div>
          <div className="panel-actions">
            {selectedRunId ? <Link className="inline-link" to={`/review?run=${selectedRunId}`}>Go To Video Review</Link> : null}
            <select value={selectedRunId} onChange={(event) => setSelectedRunId(event.target.value)}>
              <option value="">Select a run</option>
              {runs.map((run) => (
                <option key={run.id} value={run.id}>
                  {run.topic}
                </option>
              ))}
            </select>
          </div>
        </div>
        {error ? <p className="error">{error}</p> : null}
        {idea ? (
          <div className="stack">
            {editingLocked ? (
              <div className="notice-card warning">
                <strong>Review edits locked</strong>
                <p>This run already moved past text review, so prompt and scene edits are read-only to avoid changing a paid generation after submission.</p>
              </div>
            ) : null}

            <div className="panel inset">
              <div className="panel-header">
                <h3>Structured Review</h3>
                <div className="button-row">
                  <button className="secondary" onClick={handleRegenerateTextOnly} disabled={isRefreshingText || editingLocked}>
                    {isRefreshingText ? "Refreshing..." : "Regenerate Text Only"}
                  </button>
                  <button onClick={handleSaveEdits} disabled={isSaving || editingLocked}>
                    {isSaving ? "Saving..." : "Save Review Edits"}
                  </button>
                </div>
              </div>
              <div className="form-grid">
                {Object.entries(REVIEW_SECTION_LABELS).map(([key, label]) => (
                  <label key={key} className="field">
                    <span>{label}</span>
                    <textarea
                      value={reviewSections[key] ?? ""}
                      onChange={(event) => setReviewSections((current) => ({ ...current, [key]: event.target.value }))}
                      rows={3}
                      disabled={editingLocked}
                    />
                  </label>
                ))}
              </div>
            </div>

            <div className="panel inset">
              <div className="panel-header">
                <h3>Review Edits</h3>
                <label className="select-row">
                  <span className="subtle">Style Preset</span>
                  <select value={stylePreset} onChange={(event) => setStylePreset(event.target.value)} disabled={editingLocked}>
                    {STYLE_PRESETS.map((preset) => (
                      <option key={preset} value={preset}>
                        {preset}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <div className="form-grid">
                <label className="field">
                  <span>Idea Title</span>
                  <input value={ideaTitle} onChange={(event) => setIdeaTitle(event.target.value)} disabled={editingLocked} />
                </label>
                <label className="field">
                  <span>Hook</span>
                  <textarea value={ideaHook} onChange={(event) => setIdeaHook(event.target.value)} rows={3} disabled={editingLocked} />
                </label>
                <label className="field field-wide">
                  <span>Caption</span>
                  <textarea value={captionOverride} onChange={(event) => setCaptionOverride(event.target.value)} rows={4} disabled={editingLocked} />
                </label>
                <label className="field field-wide">
                  <span>Hashtags</span>
                  <input value={hashtagsText} onChange={(event) => setHashtagsText(event.target.value)} disabled={editingLocked} placeholder="#coding #webdev #codetoonsai" />
                </label>
                <label className="field field-wide">
                  <span>Ending Frame / End Tag</span>
                  <textarea value={endingFrameGuidance} onChange={(event) => setEndingFrameGuidance(event.target.value)} rows={3} disabled={editingLocked} />
                </label>
              </div>
            </div>

            <div className="panel inset">
              <div className="panel-header">
                <h3>Scene-by-Scene Review</h3>
                <span className="subtle">{sceneDrafts.length} scenes</span>
              </div>
              <div className="stack">
                {sceneDrafts.map((scene, index) => (
                  <div key={`${scene.time}-${index}`} className="content-card">
                    <div className="content-meta">
                      <strong>Scene {index + 1}</strong>
                      <span>{scene.time}</span>
                    </div>
                    <div className="form-grid">
                      <label className="field">
                        <span>Visual Description</span>
                        <textarea value={scene.visual} onChange={(event) => updateScene(index, "visual", event.target.value)} rows={4} disabled={editingLocked} />
                      </label>
                      <label className="field">
                        <span>Dialogue / Voice</span>
                        <textarea value={scene.dialogue} onChange={(event) => updateScene(index, "dialogue", event.target.value)} rows={4} disabled={editingLocked} />
                      </label>
                      <label className="field">
                        <span>On-Screen Text Guidance</span>
                        <textarea value={scene.on_screen_text} onChange={(event) => updateScene(index, "on_screen_text", event.target.value)} rows={3} disabled={editingLocked} />
                      </label>
                      <label className="field">
                        <span>Motion / Camera Guidance</span>
                        <textarea value={scene.motion_camera} onChange={(event) => updateScene(index, "motion_camera", event.target.value)} rows={3} disabled={editingLocked} />
                      </label>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="panel inset">
              <div className="panel-header">
                <h3>Prompt Preview</h3>
                <div className="button-row">
                  <button className="secondary" onClick={() => handlePromptAction("improve")} disabled={isPromptWorking !== "" || editingLocked}>
                    {isPromptWorking === "improve" ? "Improving..." : "Improve Prompt"}
                  </button>
                  <button className="secondary" onClick={() => handlePromptAction("shorten")} disabled={isPromptWorking !== "" || editingLocked}>
                    {isPromptWorking === "shorten" ? "Shortening..." : "Shorten Prompt"}
                  </button>
                </div>
              </div>
              <p className="subtle">This is the saved paid-provider prompt preview. Improve and shorten are text-only review actions and do not call Runway.</p>
              {promptLength ? (
                <div className={`notice-card ${promptTooLong || preflightLow ? "warning" : ""}`}>
                  <strong>Prompt length</strong>
                  <p>
                    {promptLength.current} chars | target {promptLength.target} | limit {promptLength.limit}
                  </p>
                  <p>{promptTooLong ? "Prompt is too long and must be fixed before Resume." : promptLength.warning ? "Prompt is safe but getting long for the provider target." : "Prompt length is in a healthy range."}</p>
                </div>
              ) : null}
              <label className="field field-wide">
                <span>Saved Prompt Override</span>
                <textarea value={promptOverride} onChange={(event) => setPromptOverride(event.target.value)} rows={8} disabled={editingLocked} />
              </label>
              {!promptPreview.includes("Story beats:") ? (
                <div className="notice-card">
                  <strong>Prompt structure check</strong>
                  <p>The preview uses the direct outcome-adherence format and does not include duplicated "Story beats" wording.</p>
                </div>
              ) : null}
              <pre className="preview-block">{promptPreview}</pre>
            </div>

            <div className="panel inset">
              <h3>Preflight Score</h3>
              {detail?.review_preflight ? (
                <div className="stack">
                  <div className="score-grid">
                    {Object.entries(preflightScores).map(([key, value]) => (
                      <div key={key} className="quality-item pass">
                        <strong>{key.split("_").join(" ")}</strong>
                        <span>{Number(value).toFixed(2)}</span>
                      </div>
                    ))}
                  </div>
                  <div className={`notice-card ${preflightLow || promptTooLong ? "warning" : ""}`}>
                    <strong>{preflightLow ? "Low-score warning" : "Preflight summary"}</strong>
                    <p>{preflightSummary}</p>
                  </div>
                </div>
              ) : (
                <p className="subtle">No preflight score found for this run yet.</p>
              )}
            </div>

            <div className="panel inset">
              <h3>Outcome Adherence Plan</h3>
              {storyAdherence ? (
                <div className="stack compact">
                  <div className="key-grid">
                    <div><span>Subject</span><strong>{String(storyAdherence.subject ?? "n/a")}</strong></div>
                    <div><span>Setup</span><strong>{String((storyAdherence.duration_plan as Record<string, unknown> | undefined)?.setup ?? "n/a")}</strong></div>
                    <div><span>Transformation</span><strong>{String((storyAdherence.duration_plan as Record<string, unknown> | undefined)?.transformation ?? "n/a")}</strong></div>
                    <div><span>Final Hold</span><strong>{String((storyAdherence.duration_plan as Record<string, unknown> | undefined)?.final_state_hold ?? "n/a")}</strong></div>
                  </div>
                  <div className="content-card">
                    <div className="content-meta"><strong>Initial state</strong></div>
                    <p>{String(storyAdherence.initial_state ?? "")}</p>
                  </div>
                  <div className="content-card">
                    <div className="content-meta"><strong>Trigger</strong></div>
                    <p>{String(storyAdherence.trigger ?? "")}</p>
                  </div>
                  <div className="content-card">
                    <div className="content-meta"><strong>Required transformation</strong></div>
                    <p>{String(storyAdherence.required_transformation ?? "")}</p>
                  </div>
                  <div className="content-card">
                    <div className="content-meta"><strong>Required final state</strong></div>
                    <p>{String(storyAdherence.required_final_state ?? "")}</p>
                  </div>
                  <div className="content-card">
                    <div className="content-meta"><strong>Final-state hold</strong></div>
                    <p>{String(storyAdherence.final_state_hold ?? "")}</p>
                  </div>
                  <div className="content-card">
                    <div className="content-meta"><strong>Prohibited actions</strong></div>
                    <p>{Array.isArray(storyAdherence.prohibited_actions) ? storyAdherence.prohibited_actions.map(String).join(", ") : String(storyAdherence.prohibited_actions ?? "")}</p>
                  </div>
                </div>
              ) : (
                <p className="subtle">No outcome adherence plan found for this run yet.</p>
              )}
            </div>

            <div className="panel inset">
              <h3>Pre-Video Critique</h3>
              {critique ? (
                <div className="stack compact">
                  {Object.entries(critique).map(([key, value]) => {
                    if (typeof value === "object" && value !== null) {
                      const typedValue = value as Record<string, unknown>;
                      return (
                        <div key={key} className="content-card">
                          <div className="content-meta">
                            <strong>{key.split("_").join(" ")}</strong>
                            {"score" in typedValue ? <span>{String(typedValue.score)}</span> : null}
                            {"flagged" in typedValue ? <span>{typedValue.flagged ? "Warning" : "OK"}</span> : null}
                          </div>
                          <p>{String(typedValue.notes ?? "")}</p>
                        </div>
                      );
                    }
                    return (
                      <div key={key} className="content-card">
                        <div className="content-meta">
                          <strong>{key.split("_").join(" ")}</strong>
                          <span>{String(value)}</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="subtle">No critique data found for this run yet.</p>
              )}
            </div>

            <div className="panel inset">
              <div className="panel-header">
                <h3>{String(idea.title)}</h3>
              </div>
              <div className="key-grid">
                <div><span>Topic</span><strong>{String(idea.topic)}</strong></div>
                <div><span>Format</span><strong>{String(idea.format)}</strong></div>
                <div><span>Difficulty</span><strong>{String(idea.difficulty)}</strong></div>
                <div><span>Trend Score</span><strong>{String(idea.trend_score)}</strong></div>
              </div>
              <p><strong>Hook:</strong> {String(idea.hook)}</p>
              <p className="subtle">{String(idea.concept)}</p>
            </div>

            <div className="panel inset">
              <h3>Storyboard</h3>
              <div className="stack">
                {storyboardFrames.map((frame, index) => (
                  <div key={`${String(frame.frame)}-${index}`} className="content-card">
                    <div className="content-meta">
                      <strong>Frame {String(frame.frame)}</strong>
                    </div>
                    <p>{String(frame.description)}</p>
                    {frame.on_screen_text ? <p><strong>On-screen text:</strong> {String(frame.on_screen_text)}</p> : null}
                    {frame.motion_camera ? <p><strong>Motion / camera:</strong> {String(frame.motion_camera)}</p> : null}
                  </div>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <p className="subtle">No runs yet. Create one from the dashboard.</p>
        )}
      </section>
    </div>
  );
}
