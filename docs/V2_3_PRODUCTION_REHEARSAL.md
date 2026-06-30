# V2.3 Production Rehearsal

## Goal

Run the app like a real content operator in safe local mode and confirm the end-to-end mock/R2 workflow is usable before building more features.

Rehearsal mode:

- `AUTH_ENABLED=false`
- `VIDEO_PROVIDER=mock`
- `STORAGE_PROVIDER=r2`

## Rehearsal Results

- 15 realistic coding-content ideas were created in Idea Queue
- batch planning and idea scoring were used to select the top 5
- 5 mock/R2 runs were generated one at a time
- all 5 completed assets finished in `completed` / `approved`
- Video Review was verified for all 5 completed assets
- Asset Library was verified for all 5 completed assets
- Export Pack was verified for all 5 completed assets
- TikTok, Instagram Reels, and YouTube Shorts copy actions were verified
- export-pack download was verified
- manual posting status updates were verified

## Non-Blocking Observations

- `Improve Prompt` can push prompts close to the provider target ceiling even while staying valid
- run and idea pickers feel crowded once many historic items accumulate

These were not treated as blocking bugs during the rehearsal.

## Conclusion

- the app is ready for private staging in `mock/r2` mode
- no paid Runway test was needed during this rehearsal

## Verification

After the rehearsal:

- `pytest -q` passed
- `npm run build` passed
- no code changes were needed
