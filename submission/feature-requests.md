# Feature Requests — Ask-Along

## 1. A "companion track" alongside subtitles in Fire TV players — Important
**What**: A standard way for a Fire TV video app to ship time-coded side content (like our question cards) next to subtitle tracks, so the system player and partner apps can show it.
**Why it matters**: Ask-Along only works on videos it plays itself. A shared track format would let kids' services (e.g. Amazon Kids+) add co-viewing questions without building a custom player.

## 2. Frame timestamps in Nova video responses — Important
**What**: Return the timestamps of the frames Nova actually sampled (or the effective FPS) with each video request.
**Why it matters**: Any feature that needs "when" (cards, chapters, highlights) cannot trust times the model writes in text today.

## 3. "Invocable by this account" in Bedrock model listings — Nice-to-have
**What**: Show whether the caller can actually invoke a model (and why not) in `list-foundation-models`.
**Why it matters**: We designed around models that turned out to need extra forms or were not available.
