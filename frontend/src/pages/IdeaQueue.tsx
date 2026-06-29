import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { api, IdeaQueueItem } from "../api/client";

const STYLE_PRESETS = [
  "clean_3d_cartoon",
  "neon_club_metaphor",
  "whiteboard_character",
  "bug_monster",
  "office_comedy",
];

const TARGET_PLATFORMS = ["instagram", "tiktok", "youtube"];
const PRIORITIES = ["low", "normal", "high"];
const STATUSES = ["draft", "ready", "generated", "archived"];

function formatDate(value?: string | null) {
  if (!value) return "Unscheduled";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", year: "numeric" }).format(date);
}

function toDateInputValue(value?: string | null) {
  if (!value) return "";
  return new Date(value).toISOString().slice(0, 10);
}

export function IdeaQueuePage() {
  const [items, setItems] = useState<IdeaQueueItem[]>([]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [topic, setTopic] = useState("Rate limiting");
  const [stylePreset, setStylePreset] = useState("clean_3d_cartoon");
  const [targetPlatform, setTargetPlatform] = useState("instagram");
  const [priority, setPriority] = useState("normal");
  const [status, setStatus] = useState("draft");
  const [notes, setNotes] = useState("");
  const [plannedDate, setPlannedDate] = useState("");
  const [error, setError] = useState("");
  const [isSaving, setIsSaving] = useState(false);

  async function loadItems() {
    const data = await api.listIdeaQueue();
    setItems(data);
    if (!selectedId && data[0]) {
      setSelectedId(data[0].id);
    }
  }

  useEffect(() => {
    loadItems().catch((requestError: Error) => setError(requestError.message));
  }, []);

  const selectedItem = useMemo(() => items.find((item) => item.id === selectedId) ?? null, [items, selectedId]);

  useEffect(() => {
    if (!selectedItem) {
      return;
    }
    setTopic(selectedItem.topic);
    setStylePreset(selectedItem.style_preset);
    setTargetPlatform(selectedItem.target_platform);
    setPriority(selectedItem.priority);
    setStatus(selectedItem.status);
    setNotes(selectedItem.notes ?? "");
    setPlannedDate(toDateInputValue(selectedItem.planned_date));
  }, [selectedItem]);

  async function handleCreate() {
    try {
      setError("");
      setIsSaving(true);
      const created = await api.createIdeaQueueItem({
        topic,
        style_preset: stylePreset,
        target_platform: targetPlatform,
        priority,
        status,
        notes,
        planned_date: plannedDate ? `${plannedDate}T09:00:00` : null,
      });
      await loadItems();
      setSelectedId(created.id);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to create idea.");
    } finally {
      setIsSaving(false);
    }
  }

  async function handleSave() {
    if (!selectedId) return;
    try {
      setError("");
      setIsSaving(true);
      const updated = await api.patchIdeaQueueItem(selectedId, {
        topic,
        style_preset: stylePreset,
        target_platform: targetPlatform,
        priority,
        status,
        notes,
        planned_date: plannedDate ? `${plannedDate}T09:00:00` : null,
      });
      setItems((current) => current.map((item) => (item.id === updated.id ? updated : item)));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to save idea.");
    } finally {
      setIsSaving(false);
    }
  }

  async function handleArchive() {
    if (!selectedId) return;
    try {
      setError("");
      const archived = await api.archiveIdeaQueueItem(selectedId);
      setItems((current) => current.map((item) => (item.id === archived.id ? archived : item)));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to archive idea.");
    }
  }

  async function handleGenerateRun() {
    if (!selectedId) return;
    try {
      setError("");
      await api.generateRunFromIdeaQueueItem(selectedId);
      await loadItems();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to generate run from idea.");
    }
  }

  const calendarItems = [...items]
    .filter((item) => item.planned_date)
    .sort((left, right) => String(left.planned_date).localeCompare(String(right.planned_date)));

  return (
    <div className="page stack">
      <section className="hero panel">
        <div>
          <p className="eyebrow">Planning</p>
          <h2>Idea Queue And Manual Calendar</h2>
          <p className="subtle">Plan topics, styles, and platforms before spending anything on video generation.</p>
        </div>
        <div className="hero-actions">
          <input value={topic} onChange={(event) => setTopic(event.target.value)} placeholder="Topic" />
          <button onClick={handleCreate} disabled={isSaving}>{isSaving ? "Saving..." : "Create Idea"}</button>
        </div>
      </section>

      {error ? <p className="error">{error}</p> : null}

      <div className="grid">
        <div className="panel">
          <div className="panel-header">
            <h2>Idea Queue</h2>
            <span>{items.length} items</span>
          </div>
          <div className="list">
            {items.map((item) => (
              <button
                key={item.id}
                className={`run-card ${selectedId === item.id ? "active" : ""}`}
                onClick={() => setSelectedId(item.id)}
              >
                <div className="content-meta">
                  <strong>{item.topic}</strong>
                  <span>{item.status}</span>
                </div>
                <div className="run-card-badges">
                  <span className="status-pill">{item.style_preset}</span>
                  <span className="status-pill muted">{item.target_platform}</span>
                </div>
                <span>{formatDate(item.planned_date)}</span>
                {item.pipeline_run_id ? <span className="subtle">Run created</span> : null}
              </button>
            ))}
          </div>
        </div>

        <div className="stack">
          <div className="panel">
            <div className="panel-header">
              <h2>Idea Details</h2>
              {selectedItem?.pipeline_run_id ? (
                <Link className="inline-link" to={`/ideas?run=${selectedItem.pipeline_run_id}`}>Open Generated Run</Link>
              ) : null}
            </div>
            {selectedItem ? (
              <div className="form-grid">
                <label className="field">
                  <span>Topic</span>
                  <input value={topic} onChange={(event) => setTopic(event.target.value)} />
                </label>
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
                  <span>Target Platform</span>
                  <select value={targetPlatform} onChange={(event) => setTargetPlatform(event.target.value)}>
                    {TARGET_PLATFORMS.map((platform) => (
                      <option key={platform} value={platform}>
                        {platform}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  <span>Priority</span>
                  <select value={priority} onChange={(event) => setPriority(event.target.value)}>
                    {PRIORITIES.map((itemPriority) => (
                      <option key={itemPriority} value={itemPriority}>
                        {itemPriority}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  <span>Status</span>
                  <select value={status} onChange={(event) => setStatus(event.target.value)}>
                    {STATUSES.map((itemStatus) => (
                      <option key={itemStatus} value={itemStatus}>
                        {itemStatus}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  <span>Planned Date</span>
                  <input type="date" value={plannedDate} onChange={(event) => setPlannedDate(event.target.value)} />
                </label>
                <label className="field field-wide">
                  <span>Notes</span>
                  <textarea value={notes} onChange={(event) => setNotes(event.target.value)} rows={6} />
                </label>
                <div className="button-row field-wide">
                  <button onClick={handleSave} disabled={isSaving}>{isSaving ? "Saving..." : "Save Idea"}</button>
                  <button className="secondary" onClick={handleGenerateRun} disabled={Boolean(selectedItem.pipeline_run_id)}>
                    {selectedItem.pipeline_run_id ? "Run Already Generated" : "Generate Run From Idea"}
                  </button>
                  <button className="secondary" onClick={handleArchive}>Archive Idea</button>
                </div>
              </div>
            ) : (
              <p className="subtle">Create or select an idea to edit it.</p>
            )}
          </div>

          <div className="panel">
            <div className="panel-header">
              <h2>Manual Content Calendar</h2>
              <span>{calendarItems.length} planned</span>
            </div>
            {calendarItems.length > 0 ? (
              <div className="stack">
                {calendarItems.map((item) => (
                  <div key={item.id} className="content-card">
                    <div className="content-meta">
                      <strong>{formatDate(item.planned_date)}</strong>
                      <span>{item.target_platform}</span>
                    </div>
                    <p><strong>Idea:</strong> {item.topic}</p>
                    <p><strong>Status:</strong> {item.status}</p>
                    {item.pipeline_run_id ? (
                      <Link className="inline-link" to={`/review?run=${item.pipeline_run_id}`}>Open generated video</Link>
                    ) : (
                      <p className="subtle">No generated video yet.</p>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <p className="subtle">Add a planned date to an idea and it will appear here.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
