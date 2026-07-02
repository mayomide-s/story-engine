import { Link } from "react-router-dom";

const DEMO_VIDEO_URL = "https://pub-fb81a8cf89e64ed1ace4e9278b7ea269.r2.dev/videos/30ea2e8e-780a-471b-b85e-80ff8d84fe51.mp4";
const DEMO_THUMBNAIL_URL = "https://pub-fb81a8cf89e64ed1ace4e9278b7ea269.r2.dev/thumbnails/30ea2e8e-780a-471b-b85e-80ff8d84fe51.jpg";

const WORKFLOW_STEPS = [
  { title: "Topic", detail: "Start with a coding concept like CORS, rate limiting, or APIs." },
  { title: "Storyboard", detail: "Generate the idea, script, and visual metaphor before spending on video." },
  { title: "Review", detail: "Edit the story, prompt, and posting copy before continuing." },
  { title: "Generate", detail: "Create the short animated explainer with the reviewed prompt." },
  { title: "Posting package", detail: "Export manual posting copy for TikTok, Instagram Reels, and YouTube Shorts." },
];

const TARGET_USERS = [
  "Coding educators",
  "Developer creators",
  "Bootcamps",
  "Student communities",
  "Technical content teams",
];

export function LandingPage() {
  return (
    <main className="landing-page">
      <section className="landing-hero">
        <div className="landing-nav">
          <div>
            <p className="eyebrow">CodeToons AI</p>
            <h1>Story Engine</h1>
          </div>
          <Link className="landing-ghost-link" to="/app">
            Open private app
          </Link>
        </div>
        <div className="landing-hero-grid">
          <div className="landing-hero-copy">
            <span className="status-pill muted">Private staging MVP</span>
            <h2>Turn coding topics into short animated explainers.</h2>
            <p className="landing-lead">
              CodeToons AI helps create storyboarded, reviewable coding mini-stories and generate platform-ready videos
              for TikTok, Instagram Reels, and YouTube Shorts.
            </p>
            <div className="button-row landing-cta-row">
              <a className="landing-primary-link" href="#demo">Watch demo</a>
              <Link className="landing-secondary-link" to="/app">
                Open private app
              </Link>
            </div>
          </div>
          <div className="landing-highlight-card">
            <p className="eyebrow">Why it matters</p>
            <h3>Short visual coding content is hard to make consistently.</h3>
            <p>
              CodeToons AI creates a reviewed story, generated video, quality check, and posting copy in one focused
              workflow.
            </p>
          </div>
        </div>
      </section>

      <section id="demo" className="landing-section">
        <div className="landing-section-header">
          <div>
            <p className="eyebrow">Featured Demo</p>
            <h2>CORS as a visual coding metaphor.</h2>
          </div>
          <span className="status-pill success">Runway generated</span>
        </div>
        <div className="landing-demo-grid">
          <div className="panel landing-video-card">
            <video className="video-player large" controls preload="metadata" poster={DEMO_THUMBNAIL_URL} src={DEMO_VIDEO_URL}>
              Your browser does not support the demo video.
            </video>
          </div>
          <div className="panel landing-demo-copy">
            <div className="key-grid">
              <div><span>Topic</span><strong>CORS</strong></div>
              <div><span>Duration</span><strong>10s</strong></div>
              <div><span>Quality Score</span><strong>0.92</strong></div>
              <div><span>Status</span><strong>Approved</strong></div>
            </div>
            <p className="subtle">Generated with Runway, stored in R2.</p>
            <p>
              This demo shows the current end-to-end MVP flow: topic to storyboard, review pause, video generation,
              quality check, and manual posting package.
            </p>
            <div className="button-row">
              <Link className="inline-link" to="/app/review">
                Open private review
              </Link>
            </div>
          </div>
        </div>
      </section>

      <section className="landing-section">
        <div className="landing-section-header">
          <div>
            <p className="eyebrow">How It Works</p>
            <h2>From coding topic to posting-ready short.</h2>
          </div>
        </div>
        <div className="landing-step-grid">
          {WORKFLOW_STEPS.map((step) => (
            <article key={step.title} className="panel landing-step-card">
              <span className="landing-step-index">{step.title}</span>
              <p>{step.detail}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="landing-section landing-duo-grid">
        <article className="panel">
          <p className="eyebrow">Problem</p>
          <h2>Developer education content takes too many tools and too much time.</h2>
          <p>
            Turning a technical idea into something short, visual, and postable usually means juggling ideation,
            scripting, storyboarding, video generation, and posting prep across separate tools.
          </p>
        </article>
        <article className="panel">
          <p className="eyebrow">Solution</p>
          <h2>Build the story first, then choose when to spend on generation.</h2>
          <p>
            CodeToons AI gives you a review-first workflow so you can shape the idea, inspect the storyboard, and only
            continue when the explainer is worth turning into a final video.
          </p>
        </article>
      </section>

      <section className="landing-section landing-duo-grid">
        <article className="panel">
          <p className="eyebrow">Safety And Control</p>
          <ul className="steps-list">
            <li>New runs pause before paid video generation.</li>
            <li>Runway generation requires explicit paid confirmation.</li>
            <li>Default staging mode is safe mock/R2 mode.</li>
          </ul>
        </article>
        <article className="panel">
          <p className="eyebrow">Who It Is For</p>
          <div className="landing-tag-grid">
            {TARGET_USERS.map((user) => (
              <span key={user} className="status-pill muted">{user}</span>
            ))}
          </div>
        </article>
      </section>

      <section className="landing-section">
        <article className="panel landing-final-cta">
          <p className="eyebrow">Beta Access</p>
          <h2>Private staging MVP, not production-ready yet.</h2>
          <p>
            CodeToons AI is currently being tested as a private staging MVP. The core workflow is working, but access is
            still controlled while the product and operator experience are refined.
          </p>
          <div className="button-row landing-cta-row">
            <a className="landing-primary-link" href="mailto:hello@codetoons.ai?subject=CodeToons%20AI%20beta%20access">
              Request beta access
            </a>
            <Link className="landing-secondary-link" to="/app">
              Open private app
            </Link>
          </div>
        </article>
      </section>
    </main>
  );
}
