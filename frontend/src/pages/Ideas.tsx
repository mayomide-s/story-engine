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

export function IdeasPage() {
  const [searchParams] = useSearchParams();
  const [runs, setRuns] = useState<PipelineRunSummary[]>([]);
  const [detail, setDetail] = useState<PipelineRunDetail | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string>("");
  const [ideaTitle, setIdeaTitle] = useState("");
  const [ideaHook, setIdeaHook] = useState("");
  const [scriptJsonText, setScriptJsonText] = useState("");
  const [promptOverride, setPromptOverride] = useState("");
  const [captionOverride, setCaptionOverride] = useState("");
  const [stylePreset, setStylePreset] = useState("clean_3d_cartoon");
  const [isSaving, setIsSaving] = useState(false);
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
    if (selectedRunId) {
      api.getRun(selectedRunId).then((payload) => {
        setDetail(payload);
        const idea = payload.idea as Record<string, unknown> | null;
        const script = payload.script as Record<string, unknown> | null;
        const run = payload.pipeline_run as Record<string, unknown> | null;
        setIdeaTitle(String(idea?.title ?? ""));
        setIdeaHook(String(idea?.hook ?? ""));
        setScriptJsonText(JSON.stringify(script?.script_json ?? {}, null, 2));
        setPromptOverride(String(run?.prompt_override ?? ""));
        setCaptionOverride(String(run?.caption_override ?? ""));
        setStylePreset(String(run?.style_preset ?? "clean_3d_cartoon"));
        setError("");
      }).catch((requestError: Error) => setError(requestError.message));
    }
  }, [selectedRunId]);

  async function handleSaveEdits() {
    if (!selectedRunId || !detail?.idea || !detail?.script) return;
    try {
      setIsSaving(true);
      setError("");
      const parsedScriptJson = JSON.parse(scriptJsonText);
      await api.patchIdea(selectedRunId, { title: ideaTitle, hook: ideaHook });
      await api.patchScript(selectedRunId, { hook: ideaHook, script_json: parsedScriptJson });
      const updated = await api.patchReviewConfig(selectedRunId, {
        prompt_override: promptOverride,
        caption_override: captionOverride,
        style_preset: stylePreset,
      });
      setDetail(updated);
      setScriptJsonText(JSON.stringify((updated.script as Record<string, unknown>)?.script_json ?? {}, null, 2));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to save review edits.");
    } finally {
      setIsSaving(false);
    }
  }

  const idea = detail?.idea as Record<string, unknown> | null;
  const storyboard = detail?.storyboard as Record<string, unknown> | null;
  const critique = detail?.content_critique ?? null;
  const promptPreview = useMemo(() => {
    if (promptOverride.trim()) {
      return promptOverride;
    }
    return String(detail?.prompt_preview ?? "");
  }, [detail?.prompt_preview, promptOverride]);

  const storyboardFrames = Array.isArray((storyboard?.frames_json as { storyboard_frames?: unknown[] } | undefined)?.storyboard_frames)
    ? (((storyboard?.frames_json as { storyboard_frames?: unknown[] }).storyboard_frames ?? []) as Record<string, unknown>[])
    : [];

  return (
    <div className="page stack">
      <section className="panel">
        <div className="panel-header">
          <h2>Ideas And Story Structure</h2>
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
            <div className="panel inset">
              <div className="panel-header">
                <h3>Review Edits</h3>
                <button onClick={handleSaveEdits} disabled={isSaving}>
                  {isSaving ? "Saving..." : "Save Review Edits"}
                </button>
              </div>
              <div className="form-grid">
                <label className="field">
                  <span>Style Preset</span>
                  <select value={stylePreset} onChange={(event) => setStylePreset(event.target.value)}>
                    {STYLE_PRESETS.map((preset) => (
                      <option key={preset} value={preset}>
                        {preset}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  <span>Idea Title</span>
                  <input value={ideaTitle} onChange={(event) => setIdeaTitle(event.target.value)} />
                </label>
                <label className="field">
                  <span>Hook</span>
                  <textarea value={ideaHook} onChange={(event) => setIdeaHook(event.target.value)} rows={3} />
                </label>
                <label className="field field-wide">
                  <span>Script / Scenes JSON</span>
                  <textarea value={scriptJsonText} onChange={(event) => setScriptJsonText(event.target.value)} rows={14} />
                </label>
                <label className="field field-wide">
                  <span>Final Video Prompt Override</span>
                  <textarea value={promptOverride} onChange={(event) => setPromptOverride(event.target.value)} rows={8} />
                </label>
                <label className="field field-wide">
                  <span>Caption Override</span>
                  <textarea value={captionOverride} onChange={(event) => setCaptionOverride(event.target.value)} rows={5} />
                </label>
              </div>
            </div>

            <div className="panel inset">
              <h3>Prompt Preview</h3>
              <p className="subtle">This is the exact prompt that will be used for the paid Runway request after your latest saved edits.</p>
              <pre className="preview-block">{promptPreview}</pre>
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
