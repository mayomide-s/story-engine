import { NavLink, Route, Routes } from "react-router-dom";

import { EnvironmentStatusPanel } from "./components/EnvironmentStatusPanel";
import { DashboardPage } from "./pages/Dashboard";
import { AssetLibraryPage } from "./pages/AssetLibrary";
import { IdeaQueuePage } from "./pages/IdeaQueue";
import { IdeasPage } from "./pages/Ideas";
import { SettingsPage } from "./pages/Settings";
import { VideoReviewPage } from "./pages/VideoReview";

export default function App() {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div>
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
        <EnvironmentStatusPanel />
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
