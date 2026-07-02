# Demo Walkthrough

## Overview

This is the current private staging MVP for `CodeToons AI / Story Engine`.

- Staging URL: `https://story.soremekun.org`
- Current safe environment: `mock/R2 safe mode`
- Featured Demo: `CORS`
- Demo video: generated with `Runway`, stored in `R2`
- Duration: `10s`
- Quality score: `0.92`
- Video dimensions: `720 x 1280`
- Manual posting package exists for:
  - TikTok
  - Instagram Reels
  - YouTube Shorts

## 60-90 Second Spoken Script

"This is CodeToons AI, our Story Engine for turning coding concepts into short visual explainer videos. Right now you're looking at the private staging MVP.

At the top of the dashboard, you can see the environment is in safe mock/R2 mode by default, which means the system is safe to review without spending video credits. Right below that is our Featured Demo card. This is a CORS explainer that already went all the way through the pipeline.

If I open the review page, you can see the generated vertical video, the stored MP4 and thumbnail assets, and the quality result. This video was generated with Runway, stored in Cloudflare R2, and it passed review with a 0.92 quality score at 720 by 1280.

Below that, you can see the manual posting package. We already have platform-ready output for TikTok, Instagram Reels, and YouTube Shorts.

What's important is that new runs do not immediately spend money. The system pauses after storyboard review, and paid Runway generation requires explicit confirmation before resume. So the MVP already proves the end-to-end workflow, while keeping the expensive step deliberately protected."

## 2-3 Minute Spoken Script

"This is CodeToons AI, powered by our Story Engine. The goal is to take a coding topic, generate a concept, script, and storyboard, then produce a short visual video and a manual posting package for short-form platforms.

This environment is a working private staging MVP, not a production launch. The current environment is intentionally kept in mock/R2 safe mode most of the time, so we can inspect the app, review content, and show completed examples without accidentally spending provider credits.

On the dashboard, the clearest path is the Featured Demo card. This is our CORS example. It represents a real successful run that generated a 10-second vertical video using Runway, stored the MP4 and thumbnail in Cloudflare R2, passed quality review with a 0.92 score, and produced a manual posting package.

If I open the review page, the first thing you see is the actual generated video. Under that, we expose the generated assets, so the video and thumbnail are both visible as first-class outputs. Then we show the quality checklist, which is how we validate that the output is usable and correctly structured. In this case, the video is vertical, provider-generated, stored correctly, and approved.

Then we get to the manual posting package. That's important because this MVP is intentionally manual-posting-first. Instead of pretending we have full scheduling or auto-posting, we generate the platform-ready copy and export materials for TikTok, Instagram Reels, and YouTube Shorts.

What makes the workflow practical is the review pause. New runs stop after storyboard review before the expensive video step. So we can inspect and edit the idea before spending money. And when Runway is enabled, the app still requires explicit confirmation before it will resume into paid generation.

Operationally, we also have demo readiness checks and R2 inventory checks in place. That means before showing this to someone, we can confirm the app is healthy, the environment is in safe mode, the featured demo assets still exist in R2, and the asset inventory reports zero missing DB-referenced objects.

So the main takeaway is: this is already a real end-to-end private MVP. It can plan content, review content, generate a real short video, store the assets, validate the output, and hand off a manual posting package, while still keeping the paid generation step intentionally protected."

## Step-By-Step Click Path

1. Open `https://story.soremekun.org`
2. Start on the `Dashboard`
3. Point out the environment line showing `mock/R2 safe mode`
4. Point out the `Featured Demo` card for `CORS`
5. Click `Watch / Open Review`
6. On `Video Review`, show:
   - generated video player
   - asset section with MP4 and thumbnail
   - quality checklist and score
   - manual posting package
7. Scroll through the platform-specific posting sections for:
   - TikTok
   - Instagram Reels
   - YouTube Shorts
8. Mention that new runs pause after storyboard review before spending credits
9. Mention that paid Runway generation requires explicit confirmation before resume

## Key Talking Points

- This is a working private staging MVP, not a public launch.
- The system already supports the full content path from concept to approved short video.
- The current default environment is intentionally safe: `mock/R2`.
- The featured CORS example proves a real Runway-generated result exists in the pipeline.
- Assets are stored durably in Cloudflare R2, not just shown temporarily in the UI.
- Review and quality checks are built into the workflow before posting.
- The output includes a practical manual posting package for short-form channels.
- Paid generation is protected by a deliberate review-and-confirmation step.

## What This Proves

- Story Engine can generate a real coding mini-story video end to end.
- The system can store and retrieve production assets from R2.
- The app can review output quality before handoff.
- The workflow can produce manual posting materials for multiple short-form platforms.
- The expensive Runway step is integrated, but still intentionally controlled.

## What Is Intentionally Protected

- New runs pause after storyboard review before video generation.
- Runway paid generation requires explicit confirmation before resume.
- The safe default environment remains `mock/R2`.
- Demo readiness and asset inventory checks exist so staging can be validated before showing it.
- R2 inventory confirms zero missing DB-referenced objects.

## Fallback Line If Someone Asks Why Runway Is Currently Disabled

"We keep staging in mock/R2 safe mode by default so we can demo, review, and inspect the system without accidentally spending provider credits. When we want a real paid test, we open a controlled Runway window deliberately instead of leaving it on."

## Pre-demo Checklist

1. SSH to the VPS
2. Run:

```bash
cd /opt/story-engine
bash scripts/vps-demo-readiness-check.sh
```

3. Confirm the result ends with:

```bash
DEMO READINESS PASSED
```

4. Confirm the site opens at:

```bash
https://story.soremekun.org
```
