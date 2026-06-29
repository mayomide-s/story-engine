import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api, PipelineRunDetail, PipelineRunSummary } from "../api/client";

export function IdeasPage() {
  const [searchParams] = useSearchParams();
  const [runs, setRuns] = useState<PipelineRunSummary[]>([]);
  const [detail, setDetail] = useState<PipelineRunDetail | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string>("");

  useEffect(() => {
    const requestedRunId = searchParams.get("run");
    api.listRuns().then((data) => {
      setRuns(data);
      if (requestedRunId && data.some((run) => run.id === requestedRunId)) {
        setSelectedRunId(requestedRunId);
      } else if (data[0]) {
        setSelectedRunId(data[0].id);
      }
    });
  }, [searchParams]);

  useEffect(() => {
    if (selectedRunId) {
      api.getRun(selectedRunId).then(setDetail);
    }
  }, [selectedRunId]);

  async function refreshScript() {
    if (!selectedRunId || !detail?.script) return;
    const currentScriptJson = (detail.script.script_json as Record<string, unknown> | undefined) ?? {};
    const scenes = Array.isArray(currentScriptJson.scenes) ? currentScriptJson.scenes : [];
    const nextScript = {
      ...currentScriptJson,
      scenes: [...scenes, { time: "24-25s", visual: "End tag flashes", dialogue: "Made by CodeToons AI" }]
    };
    const updated = await api.patchScript(selectedRunId, nextScript);
    setDetail(updated);
  }

  const idea = detail?.idea as Record<string, unknown> | null;
  const script = detail?.script as Record<string, unknown> | null;
  const storyboard = detail?.storyboard as Record<string, unknown> | null;
  const scriptJson = (script?.script_json as Record<string, unknown> | undefined) ?? {};
  const scenes = Array.isArray(scriptJson.scenes) ? (scriptJson.scenes as Record<string, unknown>[]) : [];
  const storyboardFrames = Array.isArray((storyboard?.frames_json as { storyboard_frames?: unknown[] } | undefined)?.storyboard_frames)
    ? (((storyboard?.frames_json as { storyboard_frames?: unknown[] }).storyboard_frames ?? []) as Record<string, unknown>[])
    : [];

  return (
    <div className="page stack">
      <section className="panel">
        <div className="panel-header">
          <h2>Ideas And Story Structure</h2>
          <select value={selectedRunId} onChange={(event) => setSelectedRunId(event.target.value)}>
            <option value="">Select a run</option>
            {runs.map((run) => (
              <option key={run.id} value={run.id}>
                {run.topic}
              </option>
            ))}
          </select>
        </div>
        {idea ? (
          <div className="stack">
            <div className="panel inset">
              <div className="panel-header">
                <h3>{String(idea.title)}</h3>
                {selectedRunId ? <Link className="inline-link" to={`/review?run=${selectedRunId}`}>Go To Video Review</Link> : null}
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
              <div className="panel-header">
                <h3>Script</h3>
                <button onClick={refreshScript}>Append End Scene</button>
              </div>
              <p className="subtle">{String(script?.hook ?? "")}</p>
              <div className="stack">
                {scenes.map((scene, index) => (
                  <div key={`${String(scene.time)}-${index}`} className="content-card">
                    <div className="content-meta">
                      <strong>{String(scene.time)}</strong>
                    </div>
                    <p><strong>Visual:</strong> {String(scene.visual)}</p>
                    <p><strong>Dialogue:</strong> {String(scene.dialogue)}</p>
                  </div>
                ))}
              </div>
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
