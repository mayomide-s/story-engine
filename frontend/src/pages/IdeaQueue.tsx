import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { api, AccountDefaults, IdeaQueueItem } from "../api/client";
import { AUDIENCE_LEVELS, CONTENT_FORMATS, IDEA_STATUSES, PRIORITIES, STYLE_PRESETS, TARGET_PLATFORMS } from "../constants";

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
  const [captionTone, setCaptionTone] = useState("playful explainer");
  const [durationPreferenceSeconds, setDurationPreferenceSeconds] = useState(18);
  const [audienceLevel, setAudienceLevel] = useState("beginner");
  const [contentFormat, setContentFormat] = useState("coding metaphor");
  const [priority, setPriority] = useState("normal");
  const [status, setStatus] = useState("draft");
  const [notes, setNotes] = useState("");
  const [plannedDate, setPlannedDate] = useState("");
  const [defaults, setDefaults] = useState<AccountDefaults | null>(null);
  const [error, setError] = useState("");
  const [isSaving, setIsSaving] = useState(false);

  function applyDefaults(config: AccountDefaults["account_config_json"]) {
    setStylePreset(String(config.default_style_preset ?? "clean_3d_cartoon"));
    setTargetPlatform(String(config.target_platforms?.[0] ?? "instagram"));
    setCaptionTone(String(config.default_caption_tone ?? "playful explainer"));
    setDurationPreferenceSeconds(Number(config.default_duration_seconds ?? 18));
    setAudienceLevel(String(config.default_audience_level ?? "beginner"));
    setContentFormat(String(config.default_content_format ?? "coding metaphor"));
  }

  async function loadItems() {
    const data = await api.listIdeaQueue();
    setItems(data);
    if (!selectedId && data[0]) {
      setSelectedId(data[0].id);
    }
  }

  useEffect(() => {
    api.getAccountDefaults().then((data) => {
      setDefaults(data);
      applyDefaults(data.account_config_json);
    }).catch((requestError: Error) => setError(requestError.message));
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
    setCaptionTone(String(selectedItem.input_config_json?.caption_tone ?? defaults?.account_config_json.default_caption_tone ?? "playful explainer"));
    setDurationPreferenceSeconds(Number(selectedItem.input_config_json?.duration_preference_seconds ?? defaults?.account_config_json.default_duration_seconds ?? 18));
    setAudienceLevel(String(selectedItem.input_config_json?.audience_level ?? defaults?.account_config_json.default_audience_level ?? "beginner"));
    setContentFormat(String(selectedItem.input_config_json?.content_format ?? defaults?.account_config_json.default_content_format ?? "coding metaphor"));
    setPriority(selectedItem.priority);
    setStatus(selectedItem.status);
    setNotes(selectedItem.notes ?? "");
    setPlannedDate(toDateInputValue(selectedItem.planned_date));
  }, [defaults?.account_config_json.default_audience_level, defaults?.account_config_json.default_caption_tone, defaults?.account_config_json.default_content_format, defaults?.account_config_json.default_duration_seconds, selectedItem]);

  async function handleCreate() {
    try {
      setError("");
      setIsSaving(true);
      const created = await api.createIdeaQueueItem({
        topic,
        style_preset: stylePreset,
        target_platform: targetPlatform,
        caption_tone: captionTone,
        duration_preference_seconds: durationPreferenceSeconds,
        audience_level: audienceLevel,
        content_format: contentFormat,
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
        caption_tone: captionTone,
        duration_preference_seconds: durationPreferenceSeconds,
        audience_level: audienceLevel,
        content_format: contentFormat,
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
          <p className="subtle">
            New ideas start from brand defaults in
            {" "}
            <Link className="inline-link" to="/settings">Settings</Link>
            {" "}
            and can still be overridden per idea.
          </p>
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
                  <span>Caption Tone</span>
                  <input value={captionTone} onChange={(event) => setCaptionTone(event.target.value)} />
                </label>
                <label className="field">
                  <span>Duration Preference</span>
                  <input
                    type="number"
                    min={5}
                    max={30}
                    value={durationPreferenceSeconds}
                    onChange={(event) => setDurationPreferenceSeconds(Number(event.target.value))}
                  />
                </label>
                <label className="field">
                  <span>Audience Level</span>
                  <select value={audienceLevel} onChange={(event) => setAudienceLevel(event.target.value)}>
                    {AUDIENCE_LEVELS.map((item) => (
                      <option key={item} value={item}>{item}</option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  <span>Content Format</span>
                  <select value={contentFormat} onChange={(event) => setContentFormat(event.target.value)}>
                    {CONTENT_FORMATS.map((item) => (
                      <option key={item} value={item}>{item}</option>
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
                    {IDEA_STATUSES.map((itemStatus) => (
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
                  <button className="secondary" type="button" onClick={() => defaults ? applyDefaults(defaults.account_config_json) : undefined}>
                    Reset To Defaults
                  </button>
                  <button className="secondary" onClick={handleGenerateRun} disabled={Boolean(selectedItem.pipeline_run_id)}>
                    {selectedItem.pipeline_run_id ? "Run Already Generated" : "Generate Run From Idea"}
                  </button>
                  <button className="secondary" onClick={handleArchive}>Archive Idea</button>
                </div>
                {defaults ? (
                  <div className="notice-card field-wide">
                    <strong>Applied Defaults</strong>
                    <p>
                      Style: {defaults.account_config_json.default_style_preset} | Platform: {defaults.account_config_json.target_platforms[0] ?? "instagram"} | Tone: {defaults.account_config_json.default_caption_tone}
                    </p>
                    <p>
                      Audience: {defaults.account_config_json.default_audience_level} | Format: {defaults.account_config_json.default_content_format} | Duration: {defaults.account_config_json.default_duration_seconds}s
                    </p>
                  </div>
                ) : null}
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
