---
name: council-of-thinkers-channel-scoped-reel
description: |
  Build a CHANNEL-scoped multi-voice reel/roll-call in council-of-thinkers
  (one clip per speaker on a topic, restricted to a single show/channel),
  persisted as a shareable /synthesis/<id> page. Use when: (1) the user asks
  for "a reel of people from <show> talking about <topic>" and you must honour
  the channel filter, (2) the built-in `rollcall` MCP tool returns voices from
  every channel because it ignores channel scope, (3) `query_channel("20vc",...)`
  returns nothing because the stored channel_id is the full slugged show name,
  (4) a channel-scoped collection is swamped by the host instead of the guests.
  Covers: the rollcall/_balanced_query_council channel-scope blind spot, the
  exact `_hybrid_search` + `assemble_collection` pattern that does honour a
  channel, the 20VC channel_id naming gotcha, host exclusion, and getting a
  local share_url.
author: Claude Code
version: 1.0.0
date: 2026-06-13
---

# Council of Thinkers - channel-scoped reel

## Problem

You want a reel/roll-call (one clip per speaker on a topic) restricted to a
single show/channel, e.g. "people from 20VC talking about starting an AI
startup". The obvious tool, the `rollcall` MCP tool, does NOT support a channel
filter, so it pulls voices from every channel in the corpus. You need a
channel-scoped equivalent that still persists a shareable page.

## Context / Trigger conditions

- Request shaped like "give me a reel of people from `<show>` on `<topic>`".
- `rollcall(topic)` produces a mix of channels, ignoring "from `<show>`".
- `query_channel("20vc", ...)` returns zero chunks (wrong channel name).
- A channel-scoped collection is dominated by the interviewer/host.

## Key facts (verified 2026-06-13)

1. **`rollcall` and `_balanced_query_council` ignore channel scope.**
   `build_rollcall(topic, balanced_fn=_balanced_query_council, ...)` loops over
   ALL enrolled speakers (`load_speakers().keys()`) and calls
   `_hybrid_search(query, top_k, sid)` with speaker scope only - no
   `channel_id`. So there is no built-in channel-scoped roll-call.

2. **`_hybrid_search` DOES accept a channel scope.** Signature (in
   `council_mcp/server.py`):
   `_hybrid_search(query, top_k, speaker_id=None, channel_id=None,
   where_predicate=None, query_vector=None, table=None)
   -> (rows, candidate_count, reranker, dropped)`.
   Pass `speaker_id=None, channel_id=<channel_id>` for a channel-wide search.
   Returns RAW LanceDB rows (`speaker_id`, `speaker_name`, `raw_text`,
   `youtube_url_with_timestamp`, `timestamp_start/end`, `source_title`,
   `source_date`, `chunk_id`).

3. **channel_id is the slugged full show name, not a short alias.** The 20VC
   channel_id stored in LanceDB is **`20vc_with_harry_stebbings`** (slug of
   "20VC with Harry Stebbings"), NOT `20vc`. `_slug_channel("20vc")` -> `"20vc"`
   which matches nothing, so `query_channel("20vc", ...)` and any
   `channel_id="20vc"` prefilter return empty. Always discover the real value
   first (see Verification). As of writing, the channel_id values present are:
   `20vc_with_harry_stebbings` (~29.6k chunks), `founders_podcast` (~7.7k),
   `unknown` (~1k).

4. **The host dominates a single-channel corpus.** On 20VC the host
   `harry_stebbings` is ~59% of channel chunks (17k of ~29.6k) because he is the
   interviewer and diarisation leakage attributes guest speech to him. For a
   reel of *guests talking about* the topic, exclude the host speaker_id.

5. **share_url base comes from `SYNTHESIS_BASE_URL`.** `assemble_collection`
   returns `share_url = f"{SYNTHESIS_BASE_URL}/{id}"`. With the local dev stack
   that env is `http://localhost:3000/synthesis`, so a persisted build yields
   `http://localhost:3000/synthesis/<id>`. The frontend (:3000) fetches the
   record from the backend (:8766) via `SYNTHESIS_API_BASE_URL`, so both
   `dev-up.sh` processes must be running for the page to render.

6. **The relevance score lives in `_relevance_score`, NOT `_score`.** Raw rows
   from `_hybrid_search` carry the rerank score as `_relevance_score`.
   `build_clips_dict` reads `_score`, so persisted clips silently store
   `score=0.0` for every clip unless you copy it across:
   `row["_score"] = row.get("_relevance_score", 0.0)` BEFORE `clips_from_rows`.
   Skip this and you ship a reel with no relevance signal and a page that
   shows `0.0000` on every clip.

7. **Reranker score is similarity, NOT topicality - you MUST read the clip.**
   The cross-encoder scores chunk-vs-query similarity; chunks from an on-topic
   EPISODE routinely score high while the specific 30-60s slice is a tangent
   (a childhood anecdote, a pricing aside, market-sizing). Verified example:
   the top hit for "starting a startup in the AI world" scored **0.95** but was
   about OpenAI Codex pricing limits; a childhood story scored 0.85. NEVER
   infer topicality from `source_title` - episode titles are uniformly
   on-theme, which is exactly what fooled an earlier build into claiming "all
   on-topic". Read `raw_text` and gate on what the speaker actually says. A
   score floor alone is insufficient.

8. **Do not blanket-exclude the host - gate on content instead.** On 20VC many
   `harry_stebbings`-attributed chunks are genuinely on-topic (he states the
   thesis crisply, e.g. "the costings of starting an AI company") AND broken
   diarisation misattributes guest speech to him - so excluding the host
   discards real on-topic material. Prefer guest voices for a clean reel, but
   decide per clip by reading it, not by a blanket `speaker_id` skip.

## Solution

1. Start the stack (`scripts/dev-up.sh`, or the `council-of-thinkers-local-dev`
   skill). Confirm :8766 and :3000 are up.
2. Discover the real `channel_id` for the show (do not assume the short name).
3. Run ONE channel-scoped `_hybrid_search` with generous breadth, dedup to one
   clip per speaker (skipping the host), cap to N voices, then persist via
   `assemble_collection` with `store=_open_synth_store()`.

Working script (run with `uv run python` from the repo root):

```python
import council_mcp.server as s
from council_mcp import collections as C
from council_mcp.collection_url import rollcall_url

CHANNEL  = "20vc_with_harry_stebbings"   # the REAL channel_id, not "20vc"
HOST     = "harry_stebbings"             # exclude the interviewer
TOPIC    = "starting a startup in the AI world"
N_VOICES = 12

# One broad channel-scoped pass (speaker_id=None, channel_id=CHANNEL).
# Pull a WIDE candidate pool with the channel scope. Do NOT just take the top
# N - the reranker has false positives (see fact 7), so the pool is input to a
# content gate, not the answer.
rows, candidates, reranker, dropped = s._hybrid_search(TOPIC, 60, None, channel_id=CHANNEL)

# CONTENT GATE: print each candidate's _relevance_score + raw_text, READ them,
# and keep only the clips where the speaker genuinely discusses the topic. The
# reliable selection key is a verbatim distinctive phrase from the clip text
# (robust + transparent), not rank, not score, not episode title:
PHRASES = [                                   # one per verified on-topic clip
    "monster funding rounds very early",      # Clem Delangue - cost of starting an AI co
    "Are moats dead",                         # Varun Mohan
    "increased fatality for startups",        # Des Traynor
    # ... add a phrase per clip you have actually read and confirmed on-topic
]
picked = []
for ph in PHRASES:
    m = next((r for r in rows if ph.lower() in (r.get("raw_text") or "").lower()), None)
    if m:
        m["_score"] = m.get("_relevance_score", 0.0)   # fact 6: surface the real score
        picked.append(m)
picked.sort(key=lambda r: r.get("_relevance_score", 0.0), reverse=True)

clips = C.clips_from_rows(picked, projected=False)   # RAW rows -> clip dict
blocks = [{"type": "p", "html": f"{len(clips)} guests from the show on {TOPIC} - one voice each."}]
for k, clip in clips.items():
    blocks.append({"type": "h2", "text": clip["speaker"]})
    blocks.append({"type": "clip", "ref": k})

trace = [
    {"k": "Collection", "v": "reel (channel-scoped roll-call)"},
    {"k": "Channel", "v": CHANNEL},
    {"k": "Arrangement", "v": "one voice per guest by relevance; host excluded"},
    {"k": "Voices", "v": str(len(clips))},
]

res = C.assemble_collection(
    query=f"{TOPIC} - voices from the channel",
    blocks=blocks, clips=clips, trace=trace,
    route_url=rollcall_url(TOPIC),
    store=s._open_synth_store(),          # persist -> returns id + share_url
    model="reel-v1", candidate_count=len(rows),
)
print(res["id"], res["share_url"])        # e.g. http://localhost:3000/synthesis/<id>
```

Notes on the pattern:
- `clips_from_rows(picked, projected=False)` because `_hybrid_search` returns
  RAW rows. Use `projected=True` only for projected sources (balanced query,
  `get_chunks_by_ids`).
- `route_url` (`/rollcall/<topic-slug>`) is build-on-demand and NOT channel
  scoped, so give the user the **share_url** (`/synthesis/<id>`), which is the
  persisted, channel-correct artefact.
- The env may have the cross-encoder reranker enabled
  (`BAAI/bge-reranker-v2-m3` on mps); first call blocks ~30s-2min while it
  loads. The whole build can take a minute - run it backgrounded.

## Verification

Discover the channel_id and confirm the page renders:

```bash
# 1. Real channel_id values in the corpus
uv run python - <<'PY'
import lancedb, collections
t = lancedb.connect("lancedb/council").open_table("chunks")
c = collections.Counter(t.to_arrow().column("channel_id").to_pylist())
print(c.most_common(10))
PY

# 2. Backend has the record, frontend renders it (after building)
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8766/synthesis/<id>   # 200
curl -s http://localhost:3000/synthesis/<id> | grep -o -iE "<a guest name>"      # present
```

## Notes

- To get all distinct speakers within a channel (to sanity-check that a
  multi-voice reel is even feasible), filter the arrow table on `channel_id`
  and count `speaker_id`.
- Including the host is a one-line change (drop the `sid == HOST` guard) if the
  user wants the interviewer's takes too.
- The native `/rollcall/<topic>` route is NOT a substitute for this scoped
  build: it calls `_rollcall_impl` -> `_balanced_query_council`, which is
  all-channel, host-included, content-ungated, and CAPS NOTHING - measured at
  **382 voices / ~405 KB** for a broad topic, with a cold build of **~184 s**
  (the per-speaker fan-out over ~384 enrolled speakers, each reranked). It does
  render (RollcallView maps every clip), but it is a slow, giant, off-topic
  wall. Use it only to demo the rollcall UI; for a tight reel use this scoped +
  content-gated build and serve it via `/synthesis/<id>`.
- Related skills: `council-of-thinkers-local-dev` (start/stop the stack),
  `council-of-thinkers-synthesis-share-url-404`,
  `council-of-thinkers-synthesis-invalid-json-unescaped-quotes`.
