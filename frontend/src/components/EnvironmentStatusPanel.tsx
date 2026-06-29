import { useEffect, useState } from "react";

import { api, HealthDetails } from "../api/client";

function CheckRow({ label, status, detail }: { label: string; status: string; detail: string }) {
  return (
    <div className="env-check-row">
      <div>
        <strong>{label}</strong>
        <p className="subtle">{detail}</p>
      </div>
      <span className={`status-pill ${status === "ok" ? "success" : "warning"}`}>{status}</span>
    </div>
  );
}

export function EnvironmentStatusPanel() {
  const [details, setDetails] = useState<HealthDetails | null>(null);
  const [error, setError] = useState<string>("");
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    api.getHealthDetails()
      .then((payload) => {
        setDetails(payload);
        setError("");
        setIsLoading(false);
      })
      .catch((requestError: Error) => {
        setError(requestError.message);
        setDetails(null);
        setIsLoading(false);
      });
  }, []);

  return (
    <section className="panel env-panel">
      <div className="panel-header">
        <h2>Environment</h2>
        <span className={`status-pill ${details?.status === "ok" ? "success" : "warning"}`}>
          {details?.status ?? (isLoading ? "checking" : "offline")}
        </span>
      </div>
      {!isLoading && !details ? <p className="error-text"><strong>Backend unavailable</strong></p> : null}
      {error ? (
        <div className="notice-card danger">
          <strong>Backend unavailable</strong>
          <p>{error}</p>
        </div>
      ) : null}
      {isLoading ? <p className="subtle">Checking backend readiness...</p> : null}
      {details ? (
        <div className="stack compact">
          <div className="key-grid">
            <div><span>Backend</span><strong>{details.backend_reachable ? "reachable" : "unreachable"}</strong></div>
            <div><span>Video Provider</span><strong>{details.video_provider}</strong></div>
            <div><span>Storage Provider</span><strong>{details.storage_provider}</strong></div>
            <div><span>R2 Public URL</span><strong>{details.r2_public_base_url_configured ? "configured" : "missing/not needed"}</strong></div>
          </div>
          {details.runway_mode_enabled ? (
            <div className="notice-card warning">
              <strong>Runway mode enabled</strong>
              <p>Resuming eligible runs can spend real provider credits.</p>
            </div>
          ) : null}
          <div className="stack compact">
            <CheckRow label="Configuration" status={details.checks.configuration.status} detail={details.checks.configuration.detail} />
            <CheckRow label="Database" status={details.checks.database.status} detail={details.checks.database.detail} />
            <CheckRow label="Redis" status={details.checks.redis.status} detail={details.checks.redis.detail} />
            <CheckRow label="Storage" status={details.checks.storage.status} detail={details.checks.storage.detail} />
            <CheckRow label="Video Provider" status={details.checks.video_provider.status} detail={details.checks.video_provider.detail} />
          </div>
        </div>
      ) : null}
    </section>
  );
}
