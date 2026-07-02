type Props = {
  events: Record<string, unknown>[];
  title?: string;
  summary?: string;
  defaultOpen?: boolean;
};

export function EventTimeline({
  events,
  title = "Technical Timeline",
  summary = "Show technical timeline",
  defaultOpen = false,
}: Props) {
  return (
    <div className="panel timeline-panel">
      <details className="technical-disclosure" open={defaultOpen}>
        <summary>{summary}</summary>
        <div className="panel-header technical-panel-header">
          <h2>{title}</h2>
        </div>
        <div className="timeline scroll-panel">
          {events.map((event) => (
            <div key={String(event.id)} className="timeline-item">
              <strong>{String(event.event_type)}</strong>
              <p>{String(event.message)}</p>
              <span>{String(event.stage ?? "")}</span>
            </div>
          ))}
        </div>
      </details>
    </div>
  );
}
