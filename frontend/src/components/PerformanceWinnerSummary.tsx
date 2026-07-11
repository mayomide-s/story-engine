import { Link } from "react-router-dom";

import { WinnerSelection } from "../api/client";

function formatWinnerPlatformLabel(winnerSelection: WinnerSelection | null) {
  const post = winnerSelection?.post;
  if (!post) return "Manual winner";
  if (post.platform === "other") {
    return post.custom_platform_name || "Other";
  }
  if (post.platform === "tiktok") return "TikTok";
  if (post.platform === "instagram") return "Instagram";
  if (post.platform === "youtube") return "YouTube";
  return post.platform;
}

function formatTimestamp(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

type Props = {
  winnerSelection: WinnerSelection | null;
  performanceHref?: string;
  compact?: boolean;
  heading?: string;
};

export function PerformanceWinnerSummary({
  winnerSelection,
  performanceHref,
  compact = false,
  heading = "Manual winner",
}: Props) {
  const post = winnerSelection?.post ?? null;

  return (
    <div className={`panel inset stack${compact ? " compact" : ""}`}>
      <div className="panel-header">
        <h3>{heading}</h3>
        {post ? <span className="status-pill success">Manual winner</span> : null}
      </div>
      {!post ? (
        <div className="stack compact">
          <p className="subtle">No manual winner selected yet.</p>
          {performanceHref ? <Link className="inline-link" to={performanceHref}>Open Performance</Link> : null}
        </div>
      ) : (
        <div className="stack compact">
          <div className="key-grid">
            <div><span>Platform</span><strong>{formatWinnerPlatformLabel(winnerSelection)}</strong></div>
            <div><span>Selected at</span><strong>{formatTimestamp(winnerSelection?.selected_at)}</strong></div>
          </div>
          <p className="subtle">Selected manually and independent of metric-leader badges.</p>
          <div className="button-row">
            <a className="inline-link" href={post.post_url} target="_blank" rel="noreferrer">Open public post</a>
            {performanceHref ? <Link className="inline-link" to={performanceHref}>Open Performance</Link> : null}
          </div>
        </div>
      )}
    </div>
  );
}
