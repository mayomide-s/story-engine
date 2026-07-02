import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { api, AccountDefaults, IdeaQueueItem, IdeaScore } from "../api/client";
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

type Filters = {
  status: string;
  priority: string;
  platform: string;
  stylePreset: string;
  runState: string;
  sort: string;
};

const DEFAULT_FILTERS: Filters = {
  status: "all",
  priority: "all",
  platform: "all",
  stylePreset: "all",
  runState: "all",
  sort: "planned_date",
};

export function IdeaQueuePage() {
  const [items, setItems] = useState<IdeaQueueItem[]>([]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
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
  const [isBatchUpdating, setIsBatchUpdating] = useState(false);
  const [isScoring, setIsScoring] = useState(false);
  const [batchPlannedDate, setBatchPlannedDate] = useState("");
  const [batchStatus, setBatchStatus] = useState("");
  const [batchPriority, setBatchPriority] = useState("");
  const [batchPlatform, setBatchPlatform] = useState("");
  const [batchStylePreset, setBatchStylePreset] = useState("");
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [search, setSearch] = useState("");

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

  async function refreshScores(itemIds?: string[]) {
    const ids = itemIds ?? items.map((item) => item.id);
    if (!ids.length) {
      return;
    }
    setIsScoring(true);
    try {
      const scores = await api.scoreIdeaQueueItems(ids);
      const scoreMap = new Map(scores.map((score) => [score.item_id, score]));
      setItems((current) => current.map((item) => ({ ...item, idea_score: scoreMap.get(item.id) ?? item.idea_score ?? null })));
    } finally {
      setIsScoring(false);
    }
  }

  useEffect(() => {
    api.getAccountDefaults().then((data) => {
      setDefaults(data);
      applyDefaults(data.account_config_json);
    }).catch((requestError: Error) => setError(requestError.message));
    loadItems().catch((requestError: Error) => setError(requestError.message));
  }, []);

  useEffect(() => {
    if (items.length > 0) {
      refreshScores(items.map((item) => item.id)).catch((requestError: Error) => setError(requestError.message));
    }
  }, [items.length]);

  const filteredItems = useMemo(() => {
    const normalizedQuery = search.trim().toLowerCase();
    const next = items.filter((item) => {
      if (filters.status !== "all" && item.status !== filters.status) return false;
      if (filters.priority !== "all" && item.priority !== filters.priority) return false;
      if (filters.platform !== "all" && item.target_platform !== filters.platform) return false;
      if (filters.stylePreset !== "all" && item.style_preset !== filters.stylePreset) return false;
      if (filters.runState === "with_run" && !item.pipeline_run_id) return false;
      if (filters.runState === "without_run" && item.pipeline_run_id) return false;
      if (normalizedQuery && !`${item.topic} ${item.notes ?? ""}`.toLowerCase().includes(normalizedQuery)) return false;
      return true;
    });
    if (filters.sort === "score_desc") {
      return [...next].sort((left, right) => (right.idea_score?.overall_score ?? 0) - (left.idea_score?.overall_score ?? 0));
    }
    if (filters.sort === "planned_date") {
      return [...next].sort((left, right) => String(left.planned_date ?? "9999").localeCompare(String(right.planned_date ?? "9999")));
    }
    return [...next].sort((left, right) => String(right.created_at).localeCompare(String(left.created_at)));
  }, [filters, items, search]);

  const selectedItem = useMemo(() => filteredItems.find((item) => item.id === selectedId) ?? items.find((item) => item.id === selectedId) ?? null, [filteredItems, items, selectedId]);
  const selectedItems = useMemo(() => items.filter((item) => selectedIds.includes(item.id)), [items, selectedIds]);

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

  function toggleSelected(itemId: string) {
    setSelectedIds((current) => current.includes(itemId) ? current.filter((id) => id !== itemId) : [...current, itemId]);
  }

  function toggleSelectAllVisible() {
    const visibleIds = filteredItems.map((item) => item.id);
    const allSelected = visibleIds.length > 0 && visibleIds.every((id) => selectedIds.includes(id));
    if (allSelected) {
      setSelectedIds((current) => current.filter((id) => !visibleIds.includes(id)));
      return;
    }
    setSelectedIds((current) => Array.from(new Set([...current, ...visibleIds])));
  }

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
      setSelectedIds((current) => Array.from(new Set([...current, created.id])));
      await refreshScores([created.id]);
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
      await refreshScores([updated.id]);
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

  async function handleGenerateRun(itemId: string) {
    try {
      setError("");
      await api.generateRunFromIdeaQueueItem(itemId);
      await loadItems();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to generate run from idea.");
    }
  }

  async function handleBatchUpdate(archiveSelected = false) {
    if (!selectedIds.length) return;
    try {
      setError("");
      setIsBatchUpdating(true);
      const updates: Record<string, unknown> = { item_ids: selectedIds, archive_selected: archiveSelected };
      if (!archiveSelected) {
        if (batchStatus) updates.status = batchStatus;
        if (batchPriority) updates.priority = batchPriority;
        if (batchPlatform) updates.target_platform = batchPlatform;
        if (batchStylePreset) updates.style_preset = batchStylePreset;
        if (batchPlannedDate) updates.planned_date = `${batchPlannedDate}T09:00:00`;
      }
      const updatedItems = await api.batchUpdateIdeaQueueItems(updates);
      const updatedMap = new Map(updatedItems.map((item) => [item.id, item]));
      setItems((current) => current.map((item) => updatedMap.get(item.id) ?? item));
      await refreshScores(selectedIds);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to batch update ideas.");
    } finally {
      setIsBatchUpdating(false);
    }
  }

  const calendarItems = [...items]
    .filter((item) => item.planned_date)
    .sort((left, right) => String(left.planned_date).localeCompare(String(right.planned_date)));

  const visibleIds = filteredItems.map((item) => item.id);
  const allVisibleSelected = visibleIds.length > 0 && visibleIds.every((id) => selectedIds.includes(id));

  return (
    <div className="page stack">
      <section className="page-header-card panel">
        <div>
          <p className="eyebrow">Planning</p>
          <h2>Idea Queue And Manual Calendar</h2>
          <p className="subtle">Plan, score, and prioritize ideas before you decide which single run to prepare next.</p>
          <p className="subtle">
            Generating a run only creates idea/script/storyboard work and still pauses before any paid video generation.
          </p>
          <p className="subtle">
            No bulk video generation exists here. There is no bulk Resume and no bulk Runway submission path.
          </p>
        </div>
        <div className="hero-actions">
          <input value={topic} onChange={(event) => setTopic(event.target.value)} placeholder="Topic" />
          <button onClick={handleCreate} disabled={isSaving}>{isSaving ? "Saving..." : "Create Idea"}</button>
        </div>
      </section>

      {error ? <p className="error">{error}</p> : null}

      <section className="panel">
        <div className="panel-header">
          <h2>Filters And Sorting</h2>
          <button className="secondary" type="button" onClick={() => setFilters(DEFAULT_FILTERS)}>Reset Filters</button>
        </div>
        <div className="form-grid compact">
          <label className="field">
            <span>Search</span>
            <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Topic or notes" />
          </label>
          <label className="field">
            <span>Status</span>
            <select value={filters.status} onChange={(event) => setFilters((current) => ({ ...current, status: event.target.value }))}>
              <option value="all">all</option>
              {IDEA_STATUSES.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
          </label>
          <label className="field">
            <span>Priority</span>
            <select value={filters.priority} onChange={(event) => setFilters((current) => ({ ...current, priority: event.target.value }))}>
              <option value="all">all</option>
              {PRIORITIES.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
          </label>
          <label className="field">
            <span>Platform</span>
            <select value={filters.platform} onChange={(event) => setFilters((current) => ({ ...current, platform: event.target.value }))}>
              <option value="all">all</option>
              {TARGET_PLATFORMS.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
          </label>
          <label className="field">
            <span>Style</span>
            <select value={filters.stylePreset} onChange={(event) => setFilters((current) => ({ ...current, stylePreset: event.target.value }))}>
              <option value="all">all</option>
              {STYLE_PRESETS.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
          </label>
          <label className="field">
            <span>Run State</span>
            <select value={filters.runState} onChange={(event) => setFilters((current) => ({ ...current, runState: event.target.value }))}>
              <option value="all">all</option>
              <option value="with_run">has generated run</option>
              <option value="without_run">no generated run</option>
            </select>
          </label>
          <label className="field">
            <span>Sort</span>
            <select value={filters.sort} onChange={(event) => setFilters((current) => ({ ...current, sort: event.target.value }))}>
              <option value="planned_date">planned date</option>
              <option value="score_desc">score high to low</option>
              <option value="created_desc">newest first</option>
            </select>
          </label>
        </div>
      </section>

      <div className="grid">
        <div className="panel">
          <div className="panel-header">
            <h2>Idea Queue</h2>
            <div className="panel-actions">
              <span>{filteredItems.length} visible</span>
              <button className="secondary" type="button" onClick={toggleSelectAllVisible}>
                {allVisibleSelected ? "Clear Visible" : "Select Visible"}
              </button>
            </div>
          </div>
          <div className="list scroll-panel idea-list-scroll">
            {filteredItems.map((item) => (
              <div key={item.id} className={`run-card ${selectedId === item.id ? "active" : ""}`}>
                <div className="content-meta">
                  <label className="select-row">
                    <input type="checkbox" checked={selectedIds.includes(item.id)} onChange={() => toggleSelected(item.id)} />
                    <strong>{item.topic}</strong>
                  </label>
                  <button className="text-link" type="button" onClick={() => setSelectedId(item.id)}>Open</button>
                </div>
                <div className="run-card-badges">
                  <span className="status-pill">{item.style_preset}</span>
                  <span className="status-pill muted">{item.target_platform}</span>
                  <span className="status-pill muted">{item.priority}</span>
                </div>
                <span>{item.status}</span>
                <span>{formatDate(item.planned_date)}</span>
                <span className="subtle">score: {item.idea_score?.overall_score?.toFixed(2) ?? "..."}</span>
                {item.pipeline_run_id ? <span className="subtle">Run created</span> : <span className="subtle">No run yet</span>}
              </div>
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
                    {STYLE_PRESETS.map((preset) => <option key={preset} value={preset}>{preset}</option>)}
                  </select>
                </label>
                <label className="field">
                  <span>Target Platform</span>
                  <select value={targetPlatform} onChange={(event) => setTargetPlatform(event.target.value)}>
                    {TARGET_PLATFORMS.map((platform) => <option key={platform} value={platform}>{platform}</option>)}
                  </select>
                </label>
                <label className="field">
                  <span>Caption Tone</span>
                  <input value={captionTone} onChange={(event) => setCaptionTone(event.target.value)} />
                </label>
                <label className="field">
                  <span>Duration Preference</span>
                  <input type="number" min={5} max={30} value={durationPreferenceSeconds} onChange={(event) => setDurationPreferenceSeconds(Number(event.target.value))} />
                </label>
                <label className="field">
                  <span>Audience Level</span>
                  <select value={audienceLevel} onChange={(event) => setAudienceLevel(event.target.value)}>
                    {AUDIENCE_LEVELS.map((item) => <option key={item} value={item}>{item}</option>)}
                  </select>
                </label>
                <label className="field">
                  <span>Content Format</span>
                  <select value={contentFormat} onChange={(event) => setContentFormat(event.target.value)}>
                    {CONTENT_FORMATS.map((item) => <option key={item} value={item}>{item}</option>)}
                  </select>
                </label>
                <label className="field">
                  <span>Priority</span>
                  <select value={priority} onChange={(event) => setPriority(event.target.value)}>
                    {PRIORITIES.map((itemPriority) => <option key={itemPriority} value={itemPriority}>{itemPriority}</option>)}
                  </select>
                </label>
                <label className="field">
                  <span>Status</span>
                  <select value={status} onChange={(event) => setStatus(event.target.value)}>
                    {IDEA_STATUSES.map((itemStatus) => <option key={itemStatus} value={itemStatus}>{itemStatus}</option>)}
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
                  <button className="secondary" type="button" onClick={() => defaults ? applyDefaults(defaults.account_config_json) : undefined}>Reset To Defaults</button>
                  <button className="secondary" onClick={() => handleGenerateRun(selectedItem.id)} disabled={Boolean(selectedItem.pipeline_run_id)}>
                    {selectedItem.pipeline_run_id ? "Run Already Generated" : "Generate Run From Idea"}
                  </button>
                  <button className="secondary" onClick={handleArchive}>Archive Idea</button>
                </div>
                {defaults ? (
                  <div className="notice-card field-wide">
                    <strong>Applied Defaults</strong>
                    <p>Style: {defaults.account_config_json.default_style_preset} | Platform: {defaults.account_config_json.target_platforms[0] ?? "instagram"} | Tone: {defaults.account_config_json.default_caption_tone}</p>
                    <p>Audience: {defaults.account_config_json.default_audience_level} | Format: {defaults.account_config_json.default_content_format} | Duration: {defaults.account_config_json.default_duration_seconds}s</p>
                  </div>
                ) : null}
              </div>
            ) : (
              <p className="subtle">Create or select an idea to edit it.</p>
            )}
          </div>

          <div className="panel">
            <div className="panel-header">
              <h2>Batch Review</h2>
              <div className="panel-actions">
                <span>{selectedItems.length} selected</span>
                <button className="secondary" type="button" onClick={() => refreshScores(selectedIds)} disabled={!selectedIds.length || isScoring}>
                  {isScoring ? "Scoring..." : "Refresh Scores"}
                </button>
              </div>
            </div>
            <p className="subtle">Batch planning is allowed. Batch paid generation is not. There is no bulk generate, Resume, or Runway submit action here.</p>
            <div className="form-grid compact">
              <label className="field">
                <span>Status</span>
                <select value={batchStatus} onChange={(event) => setBatchStatus(event.target.value)}>
                  <option value="">leave unchanged</option>
                  <option value="ready">mark as ready</option>
                  <option value="draft">mark as draft</option>
                </select>
              </label>
              <label className="field">
                <span>Priority</span>
                <select value={batchPriority} onChange={(event) => setBatchPriority(event.target.value)}>
                  <option value="">leave unchanged</option>
                  {PRIORITIES.map((item) => <option key={item} value={item}>{item}</option>)}
                </select>
              </label>
              <label className="field">
                <span>Platform</span>
                <select value={batchPlatform} onChange={(event) => setBatchPlatform(event.target.value)}>
                  <option value="">leave unchanged</option>
                  {TARGET_PLATFORMS.map((item) => <option key={item} value={item}>{item}</option>)}
                </select>
              </label>
              <label className="field">
                <span>Style Preset</span>
                <select value={batchStylePreset} onChange={(event) => setBatchStylePreset(event.target.value)}>
                  <option value="">leave unchanged</option>
                  {STYLE_PRESETS.map((item) => <option key={item} value={item}>{item}</option>)}
                </select>
              </label>
              <label className="field">
                <span>Planned Date</span>
                <input type="date" value={batchPlannedDate} onChange={(event) => setBatchPlannedDate(event.target.value)} />
              </label>
            </div>
            <div className="button-row">
              <button onClick={() => handleBatchUpdate(false)} disabled={!selectedIds.length || isBatchUpdating}>
                {isBatchUpdating ? "Updating..." : "Apply Batch Changes"}
              </button>
              <button className="secondary" onClick={() => handleBatchUpdate(true)} disabled={!selectedIds.length || isBatchUpdating}>
                Archive Selected
              </button>
            </div>
            <div className="stack compact scroll-panel batch-review-scroll">
              {selectedItems.map((item) => {
                const score = item.idea_score as IdeaScore | undefined;
                return (
                  <div key={item.id} className="content-card">
                    <div className="content-meta">
                      <strong>{item.topic}</strong>
                      <span>{item.pipeline_run_id ? "Run exists" : "No run yet"}</span>
                    </div>
                    <div className="key-grid">
                      <div><span>Style</span><strong>{item.style_preset}</strong></div>
                      <div><span>Platform</span><strong>{item.target_platform}</strong></div>
                      <div><span>Planned</span><strong>{formatDate(item.planned_date)}</strong></div>
                      <div><span>Priority</span><strong>{item.priority}</strong></div>
                      <div><span>Status</span><strong>{item.status}</strong></div>
                      <div><span>Score</span><strong>{score?.overall_score?.toFixed(2) ?? "..."}</strong></div>
                    </div>
                    <p>{item.notes || "No notes yet."}</p>
                    {score ? (
                      <div className="key-grid">
                        <div><span>Hook</span><strong>{score.hook_strength.toFixed(2)}</strong></div>
                        <div><span>Clarity</span><strong>{score.beginner_clarity.toFixed(2)}</strong></div>
                        <div><span>Visual</span><strong>{score.visual_potential.toFixed(2)}</strong></div>
                        <div><span>Platform Fit</span><strong>{score.platform_fit.toFixed(2)}</strong></div>
                        <div><span>Production</span><strong>{score.estimated_production_value.toFixed(2)}</strong></div>
                        <div><span>Scored By</span><strong>{score.provider}</strong></div>
                      </div>
                    ) : null}
                    <div className="button-row">
                      <button className="secondary" type="button" onClick={() => setSelectedId(item.id)}>Open Details</button>
                      <button className="secondary" type="button" onClick={() => handleGenerateRun(item.id)} disabled={Boolean(item.pipeline_run_id)}>
                        {item.pipeline_run_id ? "Run Already Generated" : "Generate Single Run"}
                      </button>
                    </div>
                  </div>
                );
              })}
              {!selectedItems.length ? <p className="subtle">Select ideas to review them together here.</p> : null}
            </div>
          </div>

          <div className="panel">
            <div className="panel-header">
              <h2>Manual Content Calendar</h2>
              <span>{calendarItems.length} planned</span>
            </div>
            {calendarItems.length > 0 ? (
              <div className="stack scroll-panel calendar-scroll">
                {calendarItems.map((item) => (
                  <div key={item.id} className="content-card">
                    <div className="content-meta">
                      <strong>{formatDate(item.planned_date)}</strong>
                      <span>{item.target_platform}</span>
                    </div>
                    <p><strong>Idea:</strong> {item.topic}</p>
                    <p><strong>Status:</strong> {item.status}</p>
                    {item.pipeline_run_id ? (
                      <Link className="inline-link" to={`/review?run=${item.pipeline_run_id}`}>Open generated run</Link>
                    ) : (
                      <p className="subtle">No generated run yet.</p>
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
