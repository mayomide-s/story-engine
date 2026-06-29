type Props = {
  events: Record<string, unknown>[];
};

export function EventTimeline({ events }: Props) {
  return (
    <div className="panel">
      <div className="panel-header">
        <h2>Event Timeline</h2>
      </div>
      <div className="timeline">
        {events.map((event) => (
          <div key={String(event.id)} className="timeline-item">
            <strong>{String(event.event_type)}</strong>
            <p>{String(event.message)}</p>
            <span>{String(event.stage ?? "")}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
