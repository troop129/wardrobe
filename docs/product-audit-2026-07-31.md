# Wardrowbe product and systems audit

Date: 2026-07-31

This audit covers the repository, the running Windows deployment, aggregate
production data, routine tablet/phone use, indexing, recommendation generation,
learning, care tracking, analytics, and deployment safety. Production data was
inspected read-only. The application changes from this audit are not deployed by
this document.

## How the app works

### Indexing

1. The browser uploads one or more photos.
2. FastAPI validates the file, computes a perceptual hash for duplicate detection,
   and writes original/thumbnail/display images.
3. A `clothing_items` row is created. If vision tagging is enabled, an ARQ job is
   sent through Redis; otherwise the item becomes ready for manual tagging.
4. The worker asks the configured vision model for normalized type, color,
   material, pattern, style, formality, season, and description fields.
5. Optional background removal is a separate best-effort worker job.
6. Only ready, non-archived items are eligible for normal recommendations.

### Outfit recommendations

1. The backend filters the user's indexed wardrobe by readiness, archive state,
   wash state, explicit include/exclude choices, and the requested occasion.
2. It scores candidates using weather, season, formality, recency, favorites,
   underuse, explicit preferences, learned color/style preferences, and learned
   item-pair performance.
3. The default local rules composer combines color harmony, style overlap,
   weather, learned item pairs, layering limits, fragrance context, and
   recent/rejected combinations. It creates up to three complete options without
   a text-model call.
4. The first option is saved and later options are cached for **Try Another**.
   An AI stylist remains available as an explicit alternative for creative
   composition, with the same completeness validation.
5. Accept/reject feedback updates the learning profile. Detailed ratings and wear
   feedback also update pair evidence and performance metrics.

## Running-system snapshot

The Windows Docker deployment was healthy during the audit: frontend, backend,
worker, PostgreSQL, and Redis were running without worker failures in recent logs.

- 54 active indexed items; all 54 were ready and tagged.
- The owner reports this is about half of the physical closet.
- 7 items had no display name and 3 had no material; all had primary color,
  pattern, formality, season, and description data.
- No duplicate perceptual hashes were present.
- 26 saved outfits: 5 accepted, 17 rejected, and 4 pending.
- Only 3 detailed feedback records existed, all accepted; none was recorded as
  actually worn. Before this audit, the ordinary accept/reject buttons did not
  create learning feedback, so these numbers understated daily interaction.
- One historical rejected AI outfit was missing a bottom. It remains historical
  data; new recommendations are now structurally validated.
- One shirt needed washing. Footwear and cologne correctly had no default wash
  cycle; shoes were not incorrectly entering laundry state.

## Improvements implemented

### Recommendation quality and partial-closet behavior

- Make deterministic smart rules the default and text AI an explicit opt-in.
  This makes ordinary suggestions faster, cheaper, explainable, and usable when
  the text provider is offline.
- Strongly reward known-good garment pairs, color harmony, style overlap, and
  favorites while still rotating underused items and avoiding recently worn or
  rejected exact combinations.
- Add **Keep these together**. It records every pair in the current look as an
  immediate, idempotent preference; the same action is available conversationally
  with phrases such as "I would wear these together."
- Require a top + bottom + footwear, or a full-body item + footwear, before an AI
  option can be saved.
- Try later AI options when an earlier option is incomplete.
- Reject exact outfit combinations rather than banning every garment in a
  rejected look for the rest of the day. This is especially important while only
  half the closet is indexed.
- Tell the model that the supplied list is the indexed/available subset, not the
  user's entire physical closet.
- Verify required manually included items were not silently omitted by the model.
- Revalidate cached alternatives against current ready/clean/unarchived items and
  structural completeness.
- Record `last_suggested_at` and suggestion counts so underuse and analytics have
  accurate evidence.

### Feedback and daily routine

- The main **Love it** and reject actions now create idempotent feedback and
  recompute learned preferences.
- **Try Another** is now a neutral skip, closes the pending outfit, and consumes a
  cached alternative instead of leaving stale pending looks or forcing another AI
  call.
- Rejecting a look immediately offers another while preserving cached choices.
- Accepting explicitly does not claim the outfit was worn; the UI reminds the user
  to record that later from History.
- Reprocessing edited detailed feedback no longer double-counts item-pair events.

### Interactive outfit builder

- Replace the suggestion preview with a stacked, slot-based view for top, layers,
  bottom, shoes, fragrance, and accessories.
- Add left/right controls to swap one slot through eligible ready, clean wardrobe
  items while preserving the rest of the look.
- Add a local, no-LLM refinement box that understands requests such as "different
  shoes," "add a layer," "no cologne," and "use the blue Nike jacket."
- Add a visible **Smart rules / AI stylist** choice so model use is intentional.

### Layering, cologne, and brands

- Make layering weather-aware instead of accidental: skip optional layers in hot
  weather, add one in mild/cool conditions, permit more in genuinely cold weather,
  and allow a direct chat override. Rain can still justify a protective layer.
- Treat cologne as an optional outfit slot rather than laundry. Date, dinner,
  party, wedding, and formal contexts can add a scent; sport and gym contexts do
  not. Fragrance family is matched to temperature when known.
- Index and edit structured fragrance family, notes, concentration, longevity,
  and sillage, and display a dedicated fragrance profile on cologne items.
- Strengthen visual brand/logo/label extraction without encouraging guesses, add
  brand-aware chat matching, and add a wardrobe brand filter backed by a brand
  distribution endpoint.

### Indexing reliability and responsiveness

- Commit item rows before enqueueing workers, eliminating the fast-worker
  "item not found" race.
- Persist bulk job IDs, which makes cancellation and recovery reliable.
- Surface queue outages as an actionable item error instead of leaving items
  permanently processing.
- Move Pillow image decoding/resizing off the FastAPI event loop so one large
  upload does not stall unrelated requests.
- Constrain wash intervals to 1-100 wears at the API boundary.

### Mobile and analytics correctness

- Centralize desktop drawer, mobile drawer, bottom-nav, and page-title labels.
- Add a visible mobile header title, including nested pages.
- Parse date-only values as local calendar dates instead of UTC, preventing the
  previous-day display bug in Pacific and other negative-offset time zones.
- Show a real 0% acceptance rate instead of "No data".
- Count all ready never-worn items rather than reporting the five-row preview size.
- Clarify that analytics cover indexed items and recorded wears, not the whole
  physical closet.

### Deployment safety

- Bind PostgreSQL, Redis, and the backend host ports to loopback. The frontend
  remains available on the LAN and proxies API requests, while raw infrastructure
  is no longer intentionally exposed to every LAN device after redeployment.

## Remaining opportunities, in priority order

### 1. Make "what I actually wore" effortless

The largest learning gap is not model sophistication; it is missing outcome data.
Add a one-tap evening card or notification: **Wore it**, **Changed pieces**, or
**Wore something else**. Accepting in the morning should remain intent, while the
evening action supplies the stronger outcome signal.

### 2. Add an explicit indexing mode

Half-indexed closets need a capture workflow rather than isolated uploads:
session progress, rack/drawer/location, rapid retake, multi-angle grouping,
duplicate-review, and a "not indexed yet" completeness indicator. Do not treat
missing categories as proof the user owns none. The current improvement makes
errors honest, but it cannot recommend an unphotographed item.

### 3. Model garment care, not just washing

Footwear should keep no wash cycle by default, as it does now. Add a care policy
such as machine wash, hand wash, dry clean, spot clean, shoe clean, and no routine
cleaning. Track reminders appropriate to the policy (for example leather care or
sneaker cleaning) instead of overloading `needs_wash`.

### 4. Improve situational recommendations

- Use forecast weather for the actual scheduled time, not merely current weather.
- Store waterproofness, warmth, breathability, and traction; rain logic currently
  cannot reliably distinguish suitable footwear.
- Add dress-code nuance, trip/packing mode, activity duration, indoor/outdoor,
  commute, and "I feel like wearing..." free-text intent.
- Allow "laundry planned today" and temporary unavailable/location states.

### 5. Improve item data and retrieval

- Add per-item size and structured fit notes; body measurements alone do not tell
  whether a specific garment currently fits.
- Add storage location and season-away state for faster morning retrieval.
- Use multiple photos in tagging and duplicate review. A single perceptual hash
  catches the same photo, not two different photos of the same garment.
- Add a guided review queue for the 7 unnamed and 3 material-missing live items.

### 6. Operations

- Add tested, scheduled backups for PostgreSQL and the wardrobe image volume.
- Add worker queue depth/job-age monitoring and alerts for stuck processing.
- Replace development/default signing secrets in every non-development deployment.
- Consider a PWA/offline shell for the bedroom tablet after the core feedback loop
  is settled.

## Verification

- Backend: 470 tests passed in an isolated PostgreSQL/Redis environment.
- Frontend: 93 tests passed, TypeScript passed, production build passed.
- Python compilation and `git diff --check` passed.

The audit did not delete or rewrite production wardrobe records, repair the one
historical incomplete outfit, backfill old accept/reject feedback, or deploy the
changes. Those are separate data-migration/deployment decisions.
