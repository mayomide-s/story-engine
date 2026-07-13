import { FormEvent, useEffect, useState } from "react";
import { NavLink, Route, Routes, useLocation } from "react-router-dom";

import { api, AccessStatus, clearStoredAccessToken, setStoredAccessToken } from "./api/client";
import { EnvironmentStatusPanel } from "./components/EnvironmentStatusPanel";
import { DashboardPage } from "./pages/Dashboard";
import { AssetLibraryPage } from "./pages/AssetLibrary";
import { ContentOpsPage } from "./pages/ContentOps";
import { BatchPlannerPage } from "./pages/BatchPlanner";
import { IdeaQueuePage } from "./pages/IdeaQueue";
import { IdeasPage } from "./pages/Ideas";
import { SettingsPage } from "./pages/Settings";
import { VideoReviewPage } from "./pages/VideoReview";
import { PerformancePage } from "./pages/Performance";
import {
  PublicDataDeletionPage,
  PublicHomePage,
  PublicPrivacyPage,
  PublicTermsPage,
} from "./pages/PublicPages";

const SIDEBAR_COLLAPSED_STORAGE_KEY = "story-engine-sidebar-collapsed";
const ACCOUNT_DELETION_NOTICE_KEY = "story-engine-account-deletion-notice";
const PUBLIC_ROUTES = new Set(["/", "/privacy", "/terms", "/data-deletion"]);

export default function App() {
  const location = useLocation();
  const isPublicRoute = PUBLIC_ROUTES.has(location.pathname);
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
  const [accountDeletionNotice, setAccountDeletionNotice] = useState(() => {
    if (typeof window === "undefined") {
      return "";
    }
    const message = window.sessionStorage.getItem(ACCOUNT_DELETION_NOTICE_KEY) ?? "";
    if (message) {
      window.sessionStorage.removeItem(ACCOUNT_DELETION_NOTICE_KEY);
    }
    return message;
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
    if (isPublicRoute) {
      setIsCheckingAccess(false);
      return;
    }
    refreshAccessStatus().catch(() => undefined);
  }, [isPublicRoute]);

  useEffect(() => {
    if (isPublicRoute) {
      return;
    }
    async function handleAccessExpired() {
      try {
        const status = await api.getAccessStatus();
        setAccessStatus(status);
        if (status.account_deleted) {
          setAccessError("");
          return;
        }
        setAccessError("Your access session expired. Enter the app password again.");
      } catch (error) {
        setAccessStatus(null);
        setAccessError(error instanceof Error ? error.message : "Backend unavailable");
      }
    }

    async function handleAccountDeleted(event: Event) {
      if (event instanceof CustomEvent && typeof event.detail?.message === "string") {
        setAccountDeletionNotice(event.detail.message);
      }
      try {
        const status = await api.getAccessStatus();
        setAccessStatus(status);
        setAccessError("");
      } catch (error) {
        setAccessStatus(null);
        setAccessError(error instanceof Error ? error.message : "Backend unavailable");
      }
    }

    window.addEventListener("app-access-expired", handleAccessExpired);
    window.addEventListener("story-engine-account-deleted", handleAccountDeleted);
    return () => {
      window.removeEventListener("app-access-expired", handleAccessExpired);
      window.removeEventListener("story-engine-account-deleted", handleAccountDeleted);
    };
  }, [isPublicRoute]);

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

  if (isPublicRoute) {
    return (
      <Routes>
        <Route path="/" element={<PublicHomePage />} />
        <Route path="/privacy" element={<PublicPrivacyPage />} />
        <Route path="/terms" element={<PublicTermsPage />} />
        <Route path="/data-deletion" element={<PublicDataDeletionPage />} />
      </Routes>
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

  if (accessStatus.account_deleted) {
    return (
      <main className="access-shell">
        <section className="panel access-panel">
          <p className="eyebrow">Story Engine</p>
          <h1>Account deleted</h1>
          <p className="subtle">
            {accountDeletionNotice || "This Story Engine account has been permanently deleted and can no longer be used."}
          </p>
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
          {accountDeletionNotice ? (
            <div className="notice-card success">
              <strong>Account deletion complete</strong>
              <p>{accountDeletionNotice}</p>
            </div>
          ) : null}
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
            <NavLink to="/app" title="Dashboard">
              <span className="nav-icon">D</span>
              <span className="nav-label">Dashboard</span>
            </NavLink>
            <NavLink to="/queue" title="Idea Queue">
              <span className="nav-icon">Q</span>
              <span className="nav-label">Idea Queue</span>
            </NavLink>
            <NavLink to="/assets" title="Asset Library">
              <span className="nav-icon">A</span>
              <span className="nav-label">Asset Library</span>
            </NavLink>
            <NavLink to="/app/batch-planner" title="Batch Planner">
              <span className="nav-icon">B</span>
              <span className="nav-label">Batch Planner</span>
            </NavLink>
            <NavLink to="/app/content-ops" title="Content Ops">
              <span className="nav-icon">C</span>
              <span className="nav-label">Content Ops</span>
            </NavLink>
            <NavLink to="/settings" title="Settings">
              <span className="nav-icon">S</span>
              <span className="nav-label">Settings</span>
            </NavLink>
            <NavLink to="/ideas" title="Ideas">
              <span className="nav-icon">I</span>
              <span className="nav-label">Ideas</span>
            </NavLink>
            <NavLink to="/review" title="Video Review">
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
        <Routes>
          <Route path="/app" element={<DashboardPage />} />
          <Route path="/queue" element={<IdeaQueuePage />} />
          <Route path="/assets" element={<AssetLibraryPage />} />
          <Route path="/app/batch-planner" element={<BatchPlannerPage />} />
          <Route path="/app/content-ops" element={<ContentOpsPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/ideas" element={<IdeasPage />} />
          <Route path="/review" element={<VideoReviewPage />} />
          <Route path="/performance/:runId" element={<PerformancePage />} />
        </Routes>
      </main>
    </div>
  );
}
