import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { AUDIENCE_LEVELS } from "../constants";
import {
  BATCH_CONTENT_ANGLES,
  BATCH_PRODUCTION_STATUSES,
  BATCH_STATUSES,
  BATCH_TARGET_PLATFORMS,
  ContentBatch,
  createDefaultBatch,
  createId,
  createStarterTopics,
  formatBatchStatus,
  loadBatches,
  saveBatches,
  saveDashboardPrefill,
  SPRINT_1_BATCH_NAME,
  type BatchContentAngle,
  type BatchProductionStatus,
  type BatchStatus,
  type BatchTargetPlatform,
  type BatchTopicIdea,
  upsertSprint1Batch,
} from "../utils/batchPlanner";

type Filters = {
  status: "all" | BatchProductionStatus;
  audienceLevel: "all" | string;
  platformFit: "all" | BatchTargetPlatform;
  hookScore: "all" | string;
  search: string;
};

const CONTENT_OPS_FILTERS: Filters = {
  status: "all",
  audienceLevel: "all",
  platformFit: "all",
  hookScore: "all",
  search: "",
};

function createBlankTopic(batch: ContentBatch): BatchTopicIdea {
  return {
    id: createId("topic"),
    topic: "",
    hookIdea: "",
    visualMetaphor: "",
    audienceLevel: batch.targetAudience,
    platformFit: batch.targetPlatform === "all" ? "tiktok" : batch.targetPlatform,
    estimatedDifficulty: "easy",
    hookScore: 3,
    productionStatus: "idea",
    notes: "",
  };
}

export function BatchPlannerPage() {
  const navigate = useNavigate();
  const [batches, setBatches] = useState<ContentBatch[]>([]);
  const [selectedBatchId, setSelectedBatchId] = useState("");
  const [filters, setFilters] = useState<Filters>(CONTENT_OPS_FILTERS);
  const [plannerMessage, setPlannerMessage] = useState<string | null>(null);

  useEffect(() => {
    const stored = loadBatches();
    const initial = stored.length > 0 ? stored : [createDefaultBatch()];
    setBatches(initial);
    setSelectedBatchId(initial[0]?.id ?? "");
  }, []);

  useEffect(() => {
    if (batches.length > 0) {
      saveBatches(batches);
    }
  }, [batches]);

  const selectedBatch = useMemo(
    () => batches.find((batch) => batch.id === selectedBatchId) ?? batches[0] ?? null,
    [batches, selectedBatchId],
  );

  const filteredTopics = useMemo(() => {
    if (!selectedBatch) {
      return [];
    }
    return selectedBatch.topics.filter((topic) => {
      if (filters.status !== "all" && topic.productionStatus !== filters.status) return false;
      if (filters.audienceLevel !== "all" && topic.audienceLevel !== filters.audienceLevel) return false;
      if (filters.platformFit !== "all" && topic.platformFit !== filters.platformFit) return false;
      if (filters.hookScore !== "all" && topic.hookScore < Number(filters.hookScore)) return false;
      if (filters.search.trim()) {
        const haystack = `${topic.topic} ${topic.hookIdea} ${topic.visualMetaphor} ${topic.notes}`.toLowerCase();
        if (!haystack.includes(filters.search.trim().toLowerCase())) return false;
      }
      return true;
    });
  }, [filters, selectedBatch]);

  const sprintSummary = useMemo(() => {
    if (!selectedBatch) {
      return null;
    }
    return {
      totalIdeas: selectedBatch.topics.length,
      selected: selectedBatch.topics.filter((topic) => topic.productionStatus === "selected").length,
      inProduction: selectedBatch.topics.filter((topic) => topic.productionStatus === "in_production").length,
      generated: selectedBatch.topics.filter((topic) => topic.productionStatus === "generated").length,
      readyToPost: selectedBatch.topics.filter((topic) => topic.productionStatus === "ready_to_post").length,
      posted: selectedBatch.topics.filter((topic) => topic.productionStatus === "posted").length,
      winners: selectedBatch.topics.filter((topic) => topic.isWinner).length,
    };
  }, [selectedBatch]);

  const nextSelectedTopic = useMemo(() => {
    if (!selectedBatch) {
      return null;
    }
    return selectedBatch.topics.find((topic) => topic.productionStatus === "selected") ?? null;
  }, [selectedBatch]);

  function persistBatch(nextBatch: ContentBatch) {
    setBatches((current) => current.map((batch) => (batch.id === nextBatch.id ? nextBatch : batch)));
  }

  function updateBatchField<K extends keyof ContentBatch>(key: K, value: ContentBatch[K]) {
    if (!selectedBatch) return;
    persistBatch({
      ...selectedBatch,
      [key]: value,
      updatedAt: new Date().toISOString(),
    });
  }

  function updateTopic(topicId: string, patch: Partial<BatchTopicIdea>) {
    if (!selectedBatch) return;
    const nextTopics = selectedBatch.topics.map((topic) => (topic.id === topicId ? { ...topic, ...patch } : topic));
    persistBatch({
      ...selectedBatch,
      topics: nextTopics,
      updatedAt: new Date().toISOString(),
    });
  }

  function addBatch() {
    const batch = createDefaultBatch();
    setBatches((current) => [batch, ...current]);
    setSelectedBatchId(batch.id);
  }

  function addManualTopic() {
    if (!selectedBatch) return;
    const nextTopic = createBlankTopic(selectedBatch);
    persistBatch({
      ...selectedBatch,
      topics: [nextTopic, ...selectedBatch.topics],
      ideaCount: Math.max(selectedBatch.ideaCount, selectedBatch.topics.length + 1),
      updatedAt: new Date().toISOString(),
    });
  }

  function addStarterTopics() {
    if (!selectedBatch) return;
    persistBatch({
      ...selectedBatch,
      topics: [...selectedBatch.topics, ...createStarterTopics()],
      ideaCount: Math.max(selectedBatch.ideaCount, selectedBatch.topics.length + 10),
      updatedAt: new Date().toISOString(),
    });
  }

  function duplicateTopic(topic: BatchTopicIdea) {
    if (!selectedBatch) return;
    persistBatch({
      ...selectedBatch,
      topics: [{ ...topic, id: createId("topic"), productionStatus: "idea" }, ...selectedBatch.topics],
      updatedAt: new Date().toISOString(),
    });
  }

  function deleteTopic(topicId: string) {
    if (!selectedBatch) return;
    persistBatch({
      ...selectedBatch,
      topics: selectedBatch.topics.filter((topic) => topic.id !== topicId),
      updatedAt: new Date().toISOString(),
    });
  }

  function moveTopic(topicId: string, productionStatus: BatchProductionStatus) {
    updateTopic(topicId, { productionStatus });
  }

  function markWinner(topicId: string, isWinner: boolean) {
    updateTopic(topicId, { isWinner });
  }

  function createSprint1() {
    const sprintExists = batches.some((batch) => batch.batchName === SPRINT_1_BATCH_NAME);
    const next = upsertSprint1Batch(batches);
    setBatches(next.batches);
    setSelectedBatchId(next.batchId);
    setPlannerMessage(
      sprintExists
        ? "Sprint 1 already exists and has been selected."
        : `Created ${SPRINT_1_BATCH_NAME}.`,
    );
    window.setTimeout(() => setPlannerMessage(null), 2200);
  }

  function sendTopicToDashboard(topic: BatchTopicIdea) {
    if (!selectedBatch) {
      return;
    }
    const nextBatch = {
      ...selectedBatch,
      topics: selectedBatch.topics.map((currentTopic) => (
        currentTopic.id === topic.id
          ? { ...currentTopic, productionStatus: "in_production" as BatchProductionStatus }
          : currentTopic
      )),
      updatedAt: new Date().toISOString(),
    };
    const nextBatches = batches.map((batch) => (batch.id === selectedBatch.id ? nextBatch : batch));
    saveDashboardPrefill({
      topic: topic.topic,
      audienceLevel: topic.audienceLevel,
      contentFormat: selectedBatch?.contentAngle === "funny metaphor" ? "coding metaphor" : "quick concept explainer",
      sourceBatchName: selectedBatch.batchName,
    });
    setBatches(nextBatches);
    saveBatches(nextBatches);
    navigate("/");
  }

  function sendNextSelectedTopicToDashboard() {
    if (!selectedBatch) {
      return;
    }
    const nextTopic = selectedBatch.topics.find((topic) => topic.productionStatus === "selected");
    if (!nextTopic) {
      setPlannerMessage("No selected topics are waiting to be sent.");
      window.setTimeout(() => setPlannerMessage(null), 2200);
      return;
    }
    sendTopicToDashboard(nextTopic);
  }

  return (
    <div className="page stack">
      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Batch Planner</p>
            <h2>Plan repeatable batches of coding explainers before production.</h2>
          </div>
          <div className="button-row">
            <button className="secondary" type="button" onClick={createSprint1}>Create Sprint 1</button>
            <button type="button" onClick={addBatch}>New Batch</button>
          </div>
        </div>
        {plannerMessage ? <p className="subtle">{plannerMessage}</p> : null}
      </section>

      <div className="review-grid">
        <section className="panel">
          <div className="panel-header">
            <h2>Batches</h2>
            <span>{batches.length} total</span>
          </div>
          <div className="content-ops-list scroll-panel">
            {batches.map((batch) => (
              <button
                key={batch.id}
                className={`run-card ${selectedBatchId === batch.id ? "active" : ""}`}
                onClick={() => setSelectedBatchId(batch.id)}
              >
                <div className="content-meta">
                  <strong>{batch.batchName}</strong>
                  <span>{formatBatchStatus(batch.batchStatus)}</span>
                </div>
                <div className="run-card-badges">
                  <span className="status-pill">{formatBatchStatus(batch.targetPlatform)}</span>
                  <span className="status-pill muted">{batch.targetAudience}</span>
                </div>
                <span>{batch.batchGoal}</span>
                <span className="subtle">{batch.topics.length} topics planned</span>
              </button>
            ))}
          </div>
        </section>

        <section className="panel">
          {selectedBatch ? (
            <div className="stack">
              <div className="panel-header">
                <h2>Batch Setup</h2>
                <div className="button-row">
                  <button
                    className="secondary"
                    type="button"
                    onClick={sendNextSelectedTopicToDashboard}
                    disabled={!nextSelectedTopic}
                  >
                    {nextSelectedTopic ? `Send next: ${nextSelectedTopic.topic}` : "Send next selected topic"}
                  </button>
                  <button className="secondary" type="button" onClick={addManualTopic}>Add Topic</button>
                  <button className="secondary" type="button" onClick={addStarterTopics}>Add Starter Ideas</button>
                </div>
              </div>
              <p className="subtle">
                {nextSelectedTopic
                  ? `The next selected topic in this batch order is "${nextSelectedTopic.topic}".`
                  : "No selected topics are waiting to be sent to the Dashboard."}
              </p>
              {sprintSummary ? (
                <div className="key-grid">
                  <div><span>Total Ideas</span><strong>{sprintSummary.totalIdeas}</strong></div>
                  <div><span>Selected</span><strong>{sprintSummary.selected}</strong></div>
                  <div><span>In Production</span><strong>{sprintSummary.inProduction}</strong></div>
                  <div><span>Generated</span><strong>{sprintSummary.generated}</strong></div>
                  <div><span>Ready To Post</span><strong>{sprintSummary.readyToPost}</strong></div>
                  <div><span>Posted</span><strong>{sprintSummary.posted}</strong></div>
                  <div><span>Winners</span><strong>{sprintSummary.winners}</strong></div>
                </div>
              ) : null}
              <div className="form-grid">
                <label className="field">
                  <span>Batch Name</span>
                  <input value={selectedBatch.batchName} onChange={(event) => updateBatchField("batchName", event.target.value)} />
                </label>
                <label className="field">
                  <span>Batch Goal</span>
                  <input value={selectedBatch.batchGoal} onChange={(event) => updateBatchField("batchGoal", event.target.value)} />
                </label>
                <label className="field">
                  <span>Target Platform</span>
                  <select value={selectedBatch.targetPlatform} onChange={(event) => updateBatchField("targetPlatform", event.target.value as BatchTargetPlatform)}>
                    {BATCH_TARGET_PLATFORMS.map((option) => <option key={option} value={option}>{formatBatchStatus(option)}</option>)}
                  </select>
                </label>
                <label className="field">
                  <span>Target Audience</span>
                  <select value={selectedBatch.targetAudience} onChange={(event) => updateBatchField("targetAudience", event.target.value)}>
                    {AUDIENCE_LEVELS.map((option) => <option key={option} value={option}>{formatBatchStatus(option)}</option>)}
                  </select>
                </label>
                <label className="field">
                  <span>Content Angle</span>
                  <select value={selectedBatch.contentAngle} onChange={(event) => updateBatchField("contentAngle", event.target.value as BatchContentAngle)}>
                    {BATCH_CONTENT_ANGLES.map((option) => <option key={option} value={option}>{formatBatchStatus(option)}</option>)}
                  </select>
                </label>
                <label className="field">
                  <span>Ideas To Plan</span>
                  <input type="number" min={1} max={50} value={selectedBatch.ideaCount} onChange={(event) => updateBatchField("ideaCount", Number(event.target.value))} />
                </label>
                <label className="field">
                  <span>Batch Status</span>
                  <select value={selectedBatch.batchStatus} onChange={(event) => updateBatchField("batchStatus", event.target.value as BatchStatus)}>
                    {BATCH_STATUSES.map((option) => <option key={option} value={option}>{formatBatchStatus(option)}</option>)}
                  </select>
                </label>
              </div>

              <div className="form-grid compact">
                <label className="field">
                  <span>Status Filter</span>
                  <select value={filters.status} onChange={(event) => setFilters((current) => ({ ...current, status: event.target.value as Filters["status"] }))}>
                    <option value="all">All</option>
                    {BATCH_PRODUCTION_STATUSES.map((option) => <option key={option} value={option}>{formatBatchStatus(option)}</option>)}
                  </select>
                </label>
                <label className="field">
                  <span>Audience</span>
                  <select value={filters.audienceLevel} onChange={(event) => setFilters((current) => ({ ...current, audienceLevel: event.target.value }))}>
                    <option value="all">All</option>
                    {AUDIENCE_LEVELS.map((option) => <option key={option} value={option}>{formatBatchStatus(option)}</option>)}
                  </select>
                </label>
                <label className="field">
                  <span>Platform Fit</span>
                  <select value={filters.platformFit} onChange={(event) => setFilters((current) => ({ ...current, platformFit: event.target.value as Filters["platformFit"] }))}>
                    <option value="all">All</option>
                    {BATCH_TARGET_PLATFORMS.filter((option) => option !== "all").map((option) => <option key={option} value={option}>{formatBatchStatus(option)}</option>)}
                  </select>
                </label>
                <label className="field">
                  <span>Hook Score</span>
                  <select value={filters.hookScore} onChange={(event) => setFilters((current) => ({ ...current, hookScore: event.target.value }))}>
                    <option value="all">All</option>
                    <option value="5">5 only</option>
                    <option value="4">4+</option>
                    <option value="3">3+</option>
                  </select>
                </label>
                <label className="field field-wide">
                  <span>Search</span>
                  <input value={filters.search} onChange={(event) => setFilters((current) => ({ ...current, search: event.target.value }))} placeholder="Search by topic or hook" />
                </label>
              </div>
            </div>
          ) : (
            <p className="subtle">Create a batch to start planning topics.</p>
          )}
        </section>
      </div>

      {selectedBatch ? (
        <section className="panel">
          <div className="panel-header">
            <h2>Topic Ideas</h2>
            <span>{filteredTopics.length} visible</span>
          </div>
          <div className="content-ops-detail-scroll scroll-panel">
            <div className="batch-topic-grid">
              {filteredTopics.map((topic) => (
                <article key={topic.id} className="content-card batch-topic-card">
                  <div className="content-meta">
                    <strong>{topic.topic || "Untitled topic"}</strong>
                    <span>{formatBatchStatus(topic.productionStatus)}</span>
                  </div>
                  <div className="run-card-badges">
                    <span className="status-pill">{formatBatchStatus(topic.platformFit)}</span>
                    <span className="status-pill muted">{formatBatchStatus(topic.audienceLevel)}</span>
                    <span className="status-pill muted">Hook {topic.hookScore}/5</span>
                    {topic.isWinner ? <span className="status-pill success">Winner</span> : null}
                  </div>
                  <div className="form-grid">
                    <label className="field">
                      <span>Topic / Title</span>
                      <input value={topic.topic} onChange={(event) => updateTopic(topic.id, { topic: event.target.value })} />
                    </label>
                    <label className="field">
                      <span>Hook Idea</span>
                      <input value={topic.hookIdea} onChange={(event) => updateTopic(topic.id, { hookIdea: event.target.value })} />
                    </label>
                    <label className="field">
                      <span>Visual Metaphor</span>
                      <input value={topic.visualMetaphor} onChange={(event) => updateTopic(topic.id, { visualMetaphor: event.target.value })} />
                    </label>
                    <label className="field">
                      <span>Audience</span>
                      <select value={topic.audienceLevel} onChange={(event) => updateTopic(topic.id, { audienceLevel: event.target.value })}>
                        {AUDIENCE_LEVELS.map((option) => <option key={option} value={option}>{formatBatchStatus(option)}</option>)}
                      </select>
                    </label>
                    <label className="field">
                      <span>Platform Fit</span>
                      <select value={topic.platformFit} onChange={(event) => updateTopic(topic.id, { platformFit: event.target.value as BatchTargetPlatform })}>
                        {BATCH_TARGET_PLATFORMS.filter((option) => option !== "all").map((option) => <option key={option} value={option}>{formatBatchStatus(option)}</option>)}
                      </select>
                    </label>
                    <label className="field">
                      <span>Estimated Difficulty</span>
                      <select value={topic.estimatedDifficulty} onChange={(event) => updateTopic(topic.id, { estimatedDifficulty: event.target.value })}>
                        <option value="easy">Easy</option>
                        <option value="medium">Medium</option>
                        <option value="hard">Hard</option>
                      </select>
                    </label>
                    <label className="field">
                      <span>Hook Score</span>
                      <input type="number" min={1} max={5} value={topic.hookScore} onChange={(event) => updateTopic(topic.id, { hookScore: Number(event.target.value) })} />
                    </label>
                    <label className="field">
                      <span>Production Status</span>
                      <select value={topic.productionStatus} onChange={(event) => updateTopic(topic.id, { productionStatus: event.target.value as BatchProductionStatus })}>
                        {BATCH_PRODUCTION_STATUSES.map((option) => <option key={option} value={option}>{formatBatchStatus(option)}</option>)}
                      </select>
                    </label>
                    <label className="field field-wide">
                      <span>Notes</span>
                      <textarea value={topic.notes} onChange={(event) => updateTopic(topic.id, { notes: event.target.value })} rows={4} />
                    </label>
                  </div>
                  <div className="button-row">
                    <button className="secondary" type="button" onClick={() => duplicateTopic(topic)}>Duplicate Topic</button>
                    <button className="secondary" type="button" onClick={() => moveTopic(topic.id, "selected")}>Mark Selected</button>
                    <button className="secondary" type="button" onClick={() => moveTopic(topic.id, "in_production")}>Mark In Production</button>
                    <button className="secondary" type="button" onClick={() => moveTopic(topic.id, "ready_to_post")}>Mark Ready To Post</button>
                    <button className="secondary" type="button" onClick={() => markWinner(topic.id, !topic.isWinner)}>
                      {topic.isWinner ? "Remove Winner" : "Mark Winner"}
                    </button>
                    <button type="button" onClick={() => sendTopicToDashboard(topic)}>Send to Dashboard</button>
                    <button className="secondary" type="button" onClick={() => deleteTopic(topic.id)}>Delete</button>
                  </div>
                </article>
              ))}
            </div>
          </div>
        </section>
      ) : null}
    </div>
  );
}
