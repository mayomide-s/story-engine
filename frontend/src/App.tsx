import { FormEvent, useEffect, useState } from "react";
import { NavLink, Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";

import { api, AccessStatus, clearStoredAccessToken, setStoredAccessToken } from "./api/client";
import { EnvironmentStatusPanel } from "./components/EnvironmentStatusPanel";
import { AssetLibraryPage } from "./pages/AssetLibrary";
import { DashboardPage } from "./pages/Dashboard";
import { IdeaQueuePage } from "./pages/IdeaQueue";
import { IdeasPage } from "./pages/Ideas";
import { LandingPage } from "./pages/LandingPage";
import { SettingsPage } from "./pages/Settings";
import { VideoReviewPage } from "./pages/VideoReview";

const SIDEBAR_COLLAPSED_STORAGE_KEY = "story-engine-sidebar-collapsed";

function LegacyRedirect({ to }: { to: string }) {
  const location = useLocation();
  return <Navigate replace to={`${to}${location.search}`} />;
}

function PrivateAppShell() {
  const location = useLocation();
  const [accessStatus, setAccessStatus] = useState<AccessStatus | null>(null);
  const [password, setPassword] = useState("");
  const [isCheckingAccess, setIsCheckingAccess] = useState(true);
  const [isLoggingIn, setIsLoggingIn] = useState(false);
  const [accessError, setAccessError] = useState("");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    if (typeof window === "undefined") {
      return false;
    }
    return window.localStorage.getItem(SIDEBAR_COLLAPSED_STORAGE_KEY) === "true";
  });

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
  }, [location.pathname]);

  useEffect(() => {
    function handleAccessExpired() {
      setAccessStatus((current) => current ? { ...current, authenticated: false } : current);
      setAccessError("Your access session expired. Enter the app password again.");
    }

    window.addEventListener("app-access-expired", handleAccessExpired);
    return () => window.removeEventListener("app-access-expired", handleAccessExpired);
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    window.localStorage.setItem(SIDEBAR_COLLAPSED_STORAGE_KEY, String(sidebarCollapsed));
  }, [sidebarCollapsed]);

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
    <div className={`app-shell ${sidebarCollapsed ? "sidebar-collapsed" : ""}`}>
      <aside className="sidebar">
        <div className="sidebar-top">
          <div className="sidebar-brand">
            <div className="sidebar-brand-row">
              <div>
                <p className="eyebrow brand-eyebrow">CodeToons AI</p>
                <h1 className="brand-full">Story Engine</h1>
                <h1 className="brand-short">CT</h1>
              </div>
              <button
                className="sidebar-toggle"
                type="button"
                onClick={() => setSidebarCollapsed((current) => !current)}
                aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
                title={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
              >
                {sidebarCollapsed ? ">" : "<"}
              </button>
            </div>
            <p className="subtle brand-tagline">Topic in. Animated video out.</p>
          </div>
          <nav className="nav">
            <NavLink to="/app/dashboard" title="Dashboard">
              <span className="nav-icon">D</span>
              <span className="nav-label">Dashboard</span>
            </NavLink>
            <NavLink to="/app/idea-queue" title="Idea Queue">
              <span className="nav-icon">Q</span>
              <span className="nav-label">Idea Queue</span>
            </NavLink>
            <NavLink to="/app/assets" title="Asset Library">
              <span className="nav-icon">A</span>
              <span className="nav-label">Asset Library</span>
            </NavLink>
            <NavLink to="/app/settings" title="Settings">
              <span className="nav-icon">S</span>
              <span className="nav-label">Settings</span>
            </NavLink>
            <NavLink to="/app/ideas" title="Ideas">
              <span className="nav-icon">I</span>
              <span className="nav-label">Ideas</span>
            </NavLink>
            <NavLink to="/app/review" title="Video Review">
              <span className="nav-icon">V</span>
              <span className="nav-label">Video Review</span>
            </NavLink>
          </nav>
        </div>
        <div className="sidebar-footer">
          <details className="sidebar-diagnostics">
            <summary>
              <span className="nav-icon">D</span>
              <span className="nav-label">Diagnostics</span>
            </summary>
            <EnvironmentStatusPanel showAccessNote={accessStatus.auth_enabled} />
          </details>
          {accessStatus.auth_enabled ? (
            <button className="secondary sidebar-logout" type="button" onClick={handleLogout} title="Logout">
              <span className="nav-icon">L</span>
              <span className="nav-label">Logout</span>
            </button>
          ) : null}
        </div>
      </aside>
      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/app" element={<PrivateAppShell />}>
        <Route index element={<Navigate replace to="/app/dashboard" />} />
        <Route path="dashboard" element={<DashboardPage />} />
        <Route path="idea-queue" element={<IdeaQueuePage />} />
        <Route path="assets" element={<AssetLibraryPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="ideas" element={<IdeasPage />} />
        <Route path="review" element={<VideoReviewPage />} />
      </Route>
      <Route path="/dashboard" element={<Navigate replace to="/app/dashboard" />} />
      <Route path="/queue" element={<Navigate replace to="/app/idea-queue" />} />
      <Route path="/assets" element={<Navigate replace to="/app/assets" />} />
      <Route path="/settings" element={<Navigate replace to="/app/settings" />} />
      <Route path="/ideas" element={<LegacyRedirect to="/app/ideas" />} />
      <Route path="/review" element={<LegacyRedirect to="/app/review" />} />
      <Route path="*" element={<Navigate replace to="/" />} />
    </Routes>
  );
}
