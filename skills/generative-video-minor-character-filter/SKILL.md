---
name: generative-video-minor-character-filter
description: |
  Fix for generative video tools (Grok Imagine, Sora 2, Veo 3, Kling 2.1,
  Runway Gen-4, Luma Ray 2) silently rejecting prompts that feature minors
  or child characters, even in clearly wholesome contexts (family moments,
  school drop-offs, graduations, coaching, birthdays). Use when: (1) a
  prompt mentioning "teenage", "young", "child", "schoolboy", "schoolgirl",
  "student", "kid", or any under-18 character returns a generic "something
  went wrong", "couldn't generate", or "content policy" error, (2) planning
  family / school / coming-of-age / sports-team scenes for merch reveals,
  emotional montages, or social video. Covers the age-up workaround,
  vocabulary swaps, and fallback compositions that preserve the emotional
  beat without tripping child-safety filters.
author: Claude Code
version: 1.0.0
date: 2026-04-17
---

# Generative Video Minor-Character Filter

## Problem

All major generative video tools run an aggressive child-safety filter that blocks prompts featuring minors, regardless of context or intent. A wholesome dad-sees-son-off-to-school prompt is indistinguishable from a problematic one to the filter, so it rejects everything that looks age-ambiguous.

The filter is over-tuned: it fires on `teenage`, `young`, `student`, `school`, `child`, `kid`, `boy`, `girl`, `playground`, `schoolbus`, even in combinations that are obviously benign. The error message is typically generic ("something went wrong", "couldn't generate this prompt", "violates content policy") with no indication of the specific trigger, so users don't realise it's the age/child framing.

This is a real blocker for social-video patterns that lean on family, graduation, mentoring, or coaching emotional beats.

## Context / Trigger Conditions

Apply this skill when a prompt hits any of these symptoms:

- Generic "something went wrong" or "couldn't generate" error on a prompt that seemed innocuous
- "Content policy" warning without specifics
- Tool accepts a variant of the prompt without the child/teen framing but rejects the original
- Prompt includes any of: `teenage`, `teen`, `young boy`, `young girl`, `child`, `kid`, `schoolboy`, `schoolgirl`, `student`, `schoolbus`, `playground`, `classroom`, `graduation`, `toddler`, `baby`, `minor`

Affected tools (verified 2026-04):

- Grok Imagine (most aggressive — blocks even indirect age cues)
- OpenAI Sora 2 (blocks outright, clear policy language)
- Google Veo 3 (blocks with safety classifier)
- Kling 2.1 (blocks, also blocks "young adult" in some contexts)
- Runway Gen-4 (blocks minors, allows adults freely)
- Luma Ray 2 (blocks minors)

## Solution

Three escalating strategies. Start with the lightest.

### Strategy 1: Age up the character

Swap minor descriptors for adult ones:

| Blocked | Use instead |
|---|---|
| teenage son | young adult son, man in his mid-twenties, grown son |
| teenage daughter | young woman, daughter in her twenties |
| schoolboy / schoolgirl | young professional, junior employee |
| student | intern, apprentice, new hire, junior colleague |
| child / kid | adult, man, woman, person |
| young athlete | runner, player, athlete, team member |
| schoolbus / playground | parked car, office, training ground |

The emotional beat usually survives the swap. "Father sees son off to school" becomes "father sees son off on a commute" — same pride, no filter trip.

### Strategy 2: Remove the age cue entirely

If the scene doesn't require a specific age, just say "a man" or "a person". The filter's default assumption is adult.

Blocked: `A teenage boy walks toward a yellow school bus.`
Safe: `A man walks toward a parked car.`

### Strategy 3: Split into single-character clips

If the emotional beat requires two characters and one of them *must* be young (rare), generate them as separate single-character clips and intercut in post:

- Clip A: the adult alone, looking off-camera with a proud expression
- Clip B: the younger character alone, but described as an adult (mid-twenties, young professional, etc.)

Cut them together. The viewer reads the relationship from context. No two-person scene means no age-ambiguity trigger.

## Safe / Unsafe Vocabulary Cheatsheet

**Safe words (reliably accepted):**

- man, woman, adult, person, individual
- professional, businessman, businesswoman, executive, manager
- runner, athlete, player, coach, mentor, colleague
- father, mother, parent (when paired with adult children)
- in his/her twenties, mid-thirties, middle-aged, older

**Unsafe words (filter triggers):**

- teen, teenager, teenage, adolescent
- child, kid, young boy, young girl, toddler, baby, infant
- schoolboy, schoolgirl, student, pupil, schoolkid
- playground, classroom, schoolbus, schoolyard, nursery
- graduation (ambiguous), prom, prep school

**Context traps (safe in isolation, trigger in combination):**

- "young" + "boy/girl" → blocks. "Young man" alone is usually safe.
- "school" + any person → blocks. "Office" or "workplace" is safe.
- "hand on shoulder" + "young" or "small" → blocks. Fine with adults.

## Verification

A prompt is safe when:

- It returns a successful generation (not an error)
- No character in the final render looks under ~22 years old
- The scene setting is adult-coded (workplace, home, driveway, café, street, gym) rather than school-coded

A prompt is unsafe when:

- Generic error returns (not a specific prompt-rejection message)
- Several regenerations fail with no obvious issue
- Same prompt with the age reference removed succeeds

## Example

**Failing prompt (Grok Imagine, 2026-04-17):**

> "A suburban driveway in soft morning light. A teenage son stands centre-frame facing camera... A father's hand rests warmly on his shoulder... A mustard-yellow school bus waits out of focus in the background."

Result: "Something went wrong, we couldn't generate it."

**Fixed prompt (same scene, adult-coded):**

> "A suburban driveway in soft morning light. A young adult man in his mid-twenties stands centre-frame facing camera... An older man, his father, rests a warm hand on his shoulder from behind... A parked car waits out of focus in the background."

Result: generates successfully. Emotional beat identical.

## Notes

- This is an accept/reject binary at the prompt-classification stage, before any pixels are rendered. Fast feedback loop: if it fails, it fails instantly. Use that to iterate vocabulary quickly.
- The filter runs on the raw prompt text. Image-to-video conditioning sometimes bypasses the text classifier but the filter may re-scan the output — not reliable as a workaround.
- Legitimate education or documentary content needing minors is out of scope for these consumer tools. Use licensed stock footage instead.
- Policies tighten over time. If a vocabulary that worked last month is now rejected, don't debug it — just age up further.
- This is separate from the public-figure filter (which blocks real people) and the brand-logo filter (which blocks trademarks). All three filters run independently; a prompt can pass two and fail one.

## References

- Grok Imagine policies: xAI enforces strict minors-in-scene filtering; no published keyword list, behaviour is observational.
- OpenAI Sora safety documentation: https://openai.com/sora
- Google Veo acceptable use: https://deepmind.google/technologies/veo
- Related skill: `text-to-video-prop-text-rendering` (for legible text on props in generated video).
