import { FormEvent, useEffect, useState } from "react";
import { NavLink, Route, Routes } from "react-router-dom";

import { api, AccessStatus, clearStoredAccessToken, setStoredAccessToken } from "./api/client";
import { EnvironmentStatusPanel } from "./components/EnvironmentStatusPanel";
import { DashboardPage } from "./pages/Dashboard";
import { AssetLibraryPage } from "./pages/AssetLibrary";
import { IdeaQueuePage } from "./pages/IdeaQueue";
import { IdeasPage } from "./pages/Ideas";
import { SettingsPage } from "./pages/Settings";
import { VideoReviewPage } from "./pages/VideoReview";

export default function App() {
  const [accessStatus, setAccessStatus] = useState<AccessStatus | null>(null);
  const [password, setPassword] = useState("");
  const [isCheckingAccess, setIsCheckingAccess] = useState(true);
  const [isLoggingIn, setIsLoggingIn] = useState(false);
  const [accessError, setAccessError] = useState("");

  async function refreshAccessStatus() {
    try {
      const status = await api.getAccessStatus();
      setAccessStatus(status);
      setAccessError("");
    } catch (error) {
      setAccessStatus(null);
      setAccessError(error instanceof Error ? error.message : "Backend unavailable");
    } finally {
      setIsCheckingAccess(false);
    }
  }

  useEffect(() => {
    refreshAccessStatus().catch(() => undefined);
  }, []);

  useEffect(() => {
    function handleAccessExpired() {
      setAccessStatus((current) => current ? { ...current, authenticated: false } : current);
      setAccessError("Your access session expired. Enter the app password again.");
    }

    window.addEventListener("app-access-expired", handleAccessExpired);
    return () => window.removeEventListener("app-access-expired", handleAccessExpired);
  }, []);

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      setIsLoggingIn(true);
      setAccessError("");
      const result = await api.login(password);
      setStoredAccessToken(result.token);
      setPassword("");
      await refreshAccessStatus();
    } catch (error) {
      setAccessError(error instanceof Error ? error.message : "Login failed.");
    } finally {
      setIsLoggingIn(false);
    }
  }

  function handleLogout() {
    clearStoredAccessToken();
    setAccessStatus((current) => current ? { ...current, authenticated: false } : current);
    setAccessError("");
  }

  if (isCheckingAccess) {
    return (
      <main className="access-shell">
        <section className="panel access-panel">
          <p className="eyebrow">CodeToons AI</p>
          <h1>Checking private access</h1>
          <p className="subtle">Waiting for backend status before loading the app.</p>
        </section>
      </main>
    );
  }

  if (!accessStatus) {
    return (
      <main className="access-shell">
        <section className="panel access-panel">
          <p className="eyebrow">CodeToons AI</p>
          <h1>Backend unavailable</h1>
          <p className="subtle">{accessError || "The backend could not be reached."}</p>
        </section>
      </main>
    );
  }

  if (accessStatus.auth_enabled && !accessStatus.authenticated) {
    return (
      <main className="access-shell">
        <section className="panel access-panel">
          <p className="eyebrow">Private staging</p>
          <h1>Enter app access password</h1>
          <p className="subtle">This is a lightweight private access gate for staging, not a full SaaS auth system.</p>
          <form className="stack" onSubmit={handleLogin}>
            <label className="field">
              <span>Access Password</span>
              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="Enter the private staging password"
              />
            </label>
            <button type="submit" disabled={isLoggingIn || !password.trim()}>
              {isLoggingIn ? "Unlocking..." : "Enter App"}
            </button>
          </form>
          <div className="notice-card">
            <strong>Auth enabled</strong>
            <p>Protected API routes stay locked until the backend issues a valid access token.</p>
          </div>
          {accessError ? <p className="error">{accessError}</p> : null}
        </section>
      </main>
    );
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <p className="eyebrow">CodeToons AI</p>
          <h1>Story Engine</h1>
          <p className="subtle">Topic in. Animated video out.</p>
        </div>
        <nav className="nav">
          <NavLink to="/">Dashboard</NavLink>
          <NavLink to="/queue">Idea Queue</NavLink>
          <NavLink to="/assets">Asset Library</NavLink>
          <NavLink to="/settings">Settings</NavLink>
          <NavLink to="/ideas">Ideas</NavLink>
          <NavLink to="/review">Video Review</NavLink>
        </nav>
        <div className="sidebar-footer">
          <EnvironmentStatusPanel />
          {accessStatus.auth_enabled ? (
            <div className="stack compact">
              <div className="notice-card">
                <strong>Private access enabled</strong>
                <p>You are using the lightweight staging access gate.</p>
              </div>
              <button className="secondary" type="button" onClick={handleLogout}>Logout</button>
            </div>
          ) : null}
        </div>
      </aside>
      <main className="content">
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/queue" element={<IdeaQueuePage />} />
          <Route path="/assets" element={<AssetLibraryPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/ideas" element={<IdeasPage />} />
          <Route path="/review" element={<VideoReviewPage />} />
        </Routes>
      </main>
    </div>
  );
}
