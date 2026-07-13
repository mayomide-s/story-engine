# Public Compliance Pages

Story Engine now exposes four unauthenticated frontend routes for public legal and compliance review:

- `/`
  Public homepage for Story Engine with product summary, support contact, and links into the app and legal pages.
- `/privacy`
  Operational privacy-policy draft describing the currently implemented data-handling, token, disconnect, retention, and account-deletion behaviour.
- `/terms`
  Operational terms-of-service draft describing service scope, user responsibility, publishing approval, and legal-review placeholders.
- `/data-deletion`
  Public account and data deletion instructions that mirror the in-app Settings flow at a high level.

## Notes

- These pages are unauthenticated and render without requiring private API data.
- The authenticated application dashboard moved to `/app` so `/` can remain a public entry point without weakening route protection for the private app.
- The legal wording remains an operational draft pending legal review.
- Governing-law wording referencing the Federal Republic of Nigeria remains explicitly marked as pending legal review.
- Production URLs are still to be chosen later. When they are finalized, these pages should map to the compliance profile URL fields for homepage, privacy policy, terms of service, and account/data deletion instructions.
