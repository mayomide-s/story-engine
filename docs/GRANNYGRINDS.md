# GrannyGrinds

GrannyGrinds turns an existing skateboarding clip into the same clip with only the primary skateboarder replaced by one of three recurring photorealistic grannies.

## Non-negotiable transformation rule

The transformed video should preserve:

- source duration and frame rate
- source resolution and orientation
- original camera movement and cuts
- skateboard and trick trajectory
- obstacles, rails, stairs, ground and background
- bystanders and other people
- lighting and scene timing
- original audio

The intended visible change is the primary skateboarder: age/identity/body appearance and the assigned granny's fixed wardrobe.

## Granny rotation

Jobs are assigned round-robin:

1. Mabel — powder-blue floral midi dress, cream knitted cardigan, white ankle socks, off-white low-top skate shoes.
2. Gloria — burgundy headscarf, burgundy velour tracksuit, gold hoops, black low-top skate shoes.
3. Dorothy — short white curls and glasses, mustard knitted vest, pale blouse, brown plaid calf-length skirt, beige ankle socks and low-top skate shoes.

Each granny also has a fixed Runway seed. Prompts and wardrobe descriptions should remain stable across clips unless a deliberate character revision is made.

## First-10 workflow

The first ten clips are intentionally not a fully autonomous content loop.

1. Find a strong skate clip manually.
2. Record the original post URL, direct HTTPS video URL, source handle/credit, and rights status.
3. Explicitly confirm paid Aleph generation.
4. GrannyGrinds downloads and probes the source.
5. Reject unsupported source inputs before generation: under 2 seconds, over 30 seconds, over 30 FPS, or above the preservation-first 1080p input ceiling.
6. Assign the next granny in the three-character rotation.
7. Submit the source to Runway Aleph 2.0.
8. When the edit finishes, restore the original source audio.
9. Compare output metadata with the source.
10. Require human visual review.
11. Approve or reject the clip.
12. For approved first-10 clips, keep Instagram AI disclosure handling human-verified before posting.

The first-10 target is quality validation, not volume.

## Structural QA

Automatic QA currently requires:

- exact source width and height
- duration drift <= 0.20 seconds
- FPS drift <= 0.02 FPS
- source audio still present when the original had audio

Passing structural QA never replaces visual review. A person must still check:

- only the primary skater changed
- board geometry/contact points did not deform
- takeoff, rotation, catch, landing and roll-away still match
- background, camera, rails, stairs and bystanders did not change
- assigned granny identity and wardrobe are convincing

## Storage and processing

Story Engine infrastructure is reused:

- FastAPI API
- PostgreSQL / Alembic
- Redis / Celery
- Cloudflare R2 for durable public media
- FFmpeg / FFprobe for media post-processing and QA
- Runway Aleph 2.0 for video-to-video editing

Production generation should use public HTTPS R2 URLs.

## Instagram publishing

The adapter uses the Instagram Reels publishing flow:

1. create a REELS media container
2. poll until the container reports FINISHED
3. call media_publish
4. store the media ID and permalink

GRANNYGRINDS_AUTOPUBLISH=false is the safe default.

For the first ten clips, publishing stays review-gated because a documented server-side field for manually applying Instagram's photorealistic AI disclosure has not yet been confirmed.

## Environment

Paid generation needs RUNWAY_API_KEY plus production R2 settings. Instagram API publishing needs INSTAGRAM_ACCESS_TOKEN and INSTAGRAM_USER_ID. The Graph API defaults to v26.0 and GrannyGrinds auto-publishing defaults to false.

## After the first 10

Only after the first ten clips establish a reliable transformation recipe:

- add automated candidate discovery
- rank candidate clips by recency/engagement signals available from permitted sources
- add source-media acquisition adapters where allowed and reliable
- keep provenance/credit on every candidate
- auto-transform only clips meeting source-quality rules
- add automated visual similarity checks to catch background/board drift
- verify the Instagram AI-disclosure path
- then enable approved-only auto-publishing

Do not make fragile browser scraping a dependency before the transformation itself is proven.
