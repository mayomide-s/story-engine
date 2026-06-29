import { NavLink, Route, Routes } from "react-router-dom";

import { DashboardPage } from "./pages/Dashboard";
import { IdeaQueuePage } from "./pages/IdeaQueue";
import { IdeasPage } from "./pages/Ideas";
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
          <NavLink to="/ideas">Ideas</NavLink>
          <NavLink to="/review">Video Review</NavLink>
        </nav>
      </aside>
      <main className="content">
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/queue" element={<IdeaQueuePage />} />
          <Route path="/ideas" element={<IdeasPage />} />
          <Route path="/review" element={<VideoReviewPage />} />
        </Routes>
      </main>
    </div>
  );
}
