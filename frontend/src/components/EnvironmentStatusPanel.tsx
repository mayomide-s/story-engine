import { useEffect, useState } from "react";

import { api, HealthDetails } from "../api/client";

type Props = {
  showAccessNote?: boolean;
};

export function EnvironmentStatusPanel({ showAccessNote = false }: Props) {
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
          <div className="env-chip-grid">
            <div className="env-chip"><span>Backend</span><strong>{details.backend_reachable ? "reachable" : "unreachable"}</strong></div>
            <div className="env-chip"><span>Private Access</span><strong>{details.auth_enabled ? "enabled" : "disabled"}</strong></div>
            <div className="env-chip"><span>Video</span><strong>{details.video_provider}</strong></div>
            <div className="env-chip"><span>Storage</span><strong>{details.storage_provider}</strong></div>
            <div className="env-chip"><span>R2 URL</span><strong>{details.r2_public_base_url_configured ? "configured" : "missing"}</strong></div>
          </div>
          <div className="status-chip-row env-status-row">
            <span className={`status-pill ${details.checks.database.status === "ok" ? "success" : "warning"}`}>DB {details.checks.database.status}</span>
            <span className={`status-pill ${details.checks.redis.status === "ok" ? "success" : "warning"}`}>Redis {details.checks.redis.status}</span>
            <span className={`status-pill ${details.checks.storage.status === "ok" ? "success" : "warning"}`}>Storage {details.checks.storage.status}</span>
          </div>
          {details.runway_mode_enabled ? (
            <div className="notice-card warning">
              <strong>Runway mode enabled</strong>
              <p>Resuming eligible runs can spend real provider credits.</p>
            </div>
          ) : null}
          {showAccessNote && details.auth_enabled ? (
            <div className="notice-card">
              <strong>Private access enabled</strong>
              <p>The lightweight staging access gate is active.</p>
            </div>
          ) : null}
          <p className="subtle env-footnote">
            Config: {details.checks.configuration.status} | Provider: {details.checks.video_provider.status}
          </p>
        </div>
      ) : null}
    </section>
  );
}
