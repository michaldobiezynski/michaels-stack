---
name: hidden-panels-still-preload-media
description: |
  Hidden tabs and panels still download their media. Use when: (1) a React/Vue/Svelte tabbed
  UI mounts every panel and hides inactive ones with `display: none`, the `hidden` attribute,
  `visibility: hidden` or zero opacity, (2) the network panel shows video, audio or image
  requests for a tab the user never opened, (3) first paint pulls megabytes you cannot
  account for, (4) a page embeds `<video>` or `<audio>` whose src is user-supplied or
  third-party and you do not want to hit those hosts unbidden, (5) you are auditing what a
  static site actually requests on load. Root cause: CSS visibility does not gate the media
  resource-loading algorithm, so `preload="metadata"` fetches regardless. Fix is to make
  preload conditional on the panel being active.
author: Claude Code
version: 1.0.0
date: 2026-08-03
---

# Hidden panels still download their media

## Problem

A tabbed UI that mounts all panels and hides the inactive ones is a completely standard
pattern:

```css
.panel { display: none }
.panel.on { display: block }
```

If any hidden panel contains `<video>` or `<audio>` with a `src` and a `preload` of
`metadata` or `auto`, **the browser fetches every one of them at first paint**, for tabs the
user may never open. `display: none`, the `hidden` attribute and `visibility: hidden` do not
gate media loading. The element is in the document, so the resource-loading algorithm runs.

Measured on one real page with 30 accepted clips, sitting on a different tab the whole time:

| Variant | Requests | Bytes |
| --- | --- | --- |
| `preload="metadata"`, panel hidden | 30 | 17.15 MiB |
| Same, throttled to 5 Mbps | 30 | 2.84 MiB in the first 8s |
| `preload="none"` | 0 | 0 |

That is roughly 4.5 seconds of a 5 Mbps connection consumed before the user has touched
anything, and it scales with the number of items.

## Context / Trigger Conditions

- A tab, accordion, carousel, modal or drawer that renders all children and hides the
  inactive ones with CSS rather than unmounting them.
- Media elements with a `src` and default or explicit `preload="metadata"` / `"auto"`.
- Symptoms: unexplained requests at load; a slow first paint that scales with list length;
  requests to third-party hosts before any user action; a privacy or CORS complaint about
  hosts you did not intend to contact yet.
- Especially sharp when the `src` values are **user-supplied or third-party**, because the
  page silently announces itself to every one of those hosts on load.

## Solution

Make `preload` conditional on whether the panel is actually showing.

```tsx
function CutPanel({ active, clips }: { active: boolean; clips: Clip[] }) {
  return (
    <div className={`panel${active ? ' on' : ''}`} hidden={!active}>
      {clips.map((clip) => (
        <video
          key={clip.id}
          src={clip.url}
          controls
          // A hidden panel still loads its media, so an unopened tab would fetch every
          // clip at first paint. Raising preload later starts the fetch, so nothing is lost.
          preload={active ? 'metadata' : 'none'}
        />
      ))}
    </div>
  )
}
```

This keeps the DOM shape identical, so existing tests that query the elements while the tab
is hidden keep working.

Alternatives, in rough order of preference:

1. **Conditional `preload`** as above. Smallest change, keeps the DOM stable.
2. **Do not mount inactive panels at all.** Fixes this and the render cost of hidden
   subtrees, but changes behaviour: component state in those panels resets on every tab
   switch, and any test querying hidden panels breaks.
3. **`loading="lazy"` on the video**, which per MDN applies preload behaviour only once the
   element is near or in the viewport. Less battle-tested across browsers than the preload
   toggle, so verify before relying on it.

## Verification

Assert it at the network level, not by reading the markup:

```ts
test('does not fetch clips for a tab that has not been opened', async ({ page }) => {
  const clipRequests: string[] = []
  await page.route('**/*.mp4', async (route) => {
    clipRequests.push(route.request().url())
    await route.fulfill({ status: 200, contentType: 'video/mp4', body: '' })
  })

  await page.goto('/')
  await page.waitForTimeout(1000)
  expect(clipRequests).toEqual([])          // nothing fetched while the tab is closed

  await page.getByTestId('tab-cut').click()
  await expect.poll(() => clipRequests.length).toBe(2)   // and it does fetch once opened
})
```

Then **mutate the fix away and confirm the test fails**, or you have not proven anything.
Reverting `preload={active ? 'metadata' : 'none'}` back to `preload="metadata"` should turn
the first assertion red. In one run it went from 0 requests to 4.

The second half of the test matters as much as the first: it proves that raising `preload`
after load actually starts the fetch, so the optimisation has not broken playback.

## Notes

- Verified in Chromium. Raising `preload` from `none` to `metadata` after load starting the
  fetch is a "may" in the spec, so confirm in Safari and Firefox if you support them. The
  user-visible fallback is mild: metadata such as duration appears slightly later.
- The same reasoning applies to `<img>` in hidden panels, though images are usually far
  cheaper. `loading="lazy"` is the well-supported answer there.
- `autoplay` takes precedence over `preload`, so a hidden autoplaying video downloads
  regardless.
- Do not reach for this before measuring. Check the network panel, filter by media, and
  confirm the requests actually fire on load with the tab closed.
- When auditing what a page requests, prefer an **allowlist** assertion over a denylist. A
  test that greps for a couple of known-bad hostnames cannot fail for the host nobody thought
  of, and reads as a guarantee it does not provide.

## References

- [MDN: `<video>` preload attribute](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/video) — documents `none`, `metadata`, `auto`, that the value is a hint the browser may ignore, that `autoplay` takes precedence, and the `loading="lazy"` interaction. It does not address hidden elements, which is why this trap is easy to miss.
- [HTML spec: media element load algorithm](https://html.spec.whatwg.org/multipage/media.html#loading-the-media-resource)
