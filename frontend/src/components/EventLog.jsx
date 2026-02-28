import { useEffect, useRef } from "react";

export default function EventLog({ events, isPipelineRunning = false }) {
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events.length]);

  if (events.length === 0) {
    return (
      <div className="card empty-state">
        {isPipelineRunning ? (
          <>
            <span className="spinner" style={{ display: "inline-block", marginBottom: "0.75rem" }} />
            <p>Waiting for pipeline events…</p>
          </>
        ) : (
          <p>No events recorded.</p>
        )}
      </div>
    );
  }

  return (
    <div className="card">
      <h2>📡 Live Events</h2>
      <div className="event-log">
        {events.map((evt, i) => (
          <div key={i} className="event-log-entry">
            <span className="event-name">{evt.event || "message"}</span>{" "}
            {evt.stage && <span>stage={evt.stage} </span>}
            {evt.campaign_id && (
              <span style={{ color: "var(--color-text-dim)" }}>
                campaign={evt.campaign_id.slice(0, 8)}…
              </span>
            )}
            {evt.error && (
              <span style={{ color: "var(--color-danger)" }}> error: {evt.error}</span>
            )}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
