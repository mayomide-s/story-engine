import { Link } from "react-router-dom";

import { PerformanceLearning, PerformanceLearningsSummary as PerformanceLearningsSummaryData } from "../api/client";

const LEARNING_TYPE_LABELS = {
  worked: "Worked",
  did_not_work: "Did not work",
  next_test: "Test next",
  observation: "Observation",
} as const;

function formatTimestamp(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

export function getPerformanceLearningTypeLabel(type: PerformanceLearning["learning_type"]) {
  return LEARNING_TYPE_LABELS[type] ?? type;
}

export function formatPerformanceLearningAssociatedPostLabel(learning: Pick<PerformanceLearning, "associated_post">) {
  const post = learning.associated_post;
  if (!post) return null;
  if (post.platform === "other") {
    return post.custom_platform_name || "Other";
  }
  if (post.platform === "tiktok") return "TikTok";
  if (post.platform === "instagram") return "Instagram";
  if (post.platform === "youtube") return "YouTube";
  return post.platform;
}

type Props = {
  summary?: PerformanceLearningsSummaryData | null;
  performanceHref?: string;
  heading?: string;
  compact?: boolean;
};

export function PerformanceLearningsSummary({
  summary,
  performanceHref,
  heading = "Performance learnings",
  compact = false,
}: Props) {
  const activeCount = summary?.active_count ?? 0;
  const items = summary?.items ?? [];

  return (
    <div className={`panel inset stack${compact ? " compact" : ""}`}>
      <div className="panel-header">
        <h3>{heading}</h3>
        <span>{activeCount} active</span>
      </div>
      <p className="subtle">User-authored observations; not proof of causation.</p>
      {!items.length ? (
        <div className="stack compact">
          <p className="subtle">No active performance learnings yet.</p>
          {performanceHref ? <Link className="inline-link" to={performanceHref}>Open Performance</Link> : null}
        </div>
      ) : (
        <div className="stack compact">
          {activeCount > items.length ? (
            <p className="subtle">Showing the latest {items.length} of {activeCount} active learnings.</p>
          ) : null}
          {items.map((learning) => {
            const associatedLabel = formatPerformanceLearningAssociatedPostLabel(learning);
            return (
              <div key={learning.id} className="panel inset stack compact">
                <div className="panel-header">
                  <span className="status-pill muted">{getPerformanceLearningTypeLabel(learning.learning_type)}</span>
                  <span>{formatTimestamp(learning.updated_at)}</span>
                </div>
                <p style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{learning.observation}</p>
                {associatedLabel ? <p className="subtle">Associated post: {associatedLabel}</p> : null}
              </div>
            );
          })}
          {performanceHref ? <Link className="inline-link" to={performanceHref}>Open Performance</Link> : null}
        </div>
      )}
    </div>
  );
}
