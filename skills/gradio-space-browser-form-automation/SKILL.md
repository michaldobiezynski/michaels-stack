---
name: gradio-space-browser-form-automation
description: |
  Drive a Gradio app (HF Space) UI with agent-browser when there is no usable API path:
  switching gr.Tab tabs and uploading files into gr.File inputs. Use when: (1) clicking a
  Gradio tab via a11y refs, semantic locators, or naive querySelector does nothing and the
  old tab stays [selected], (2) `agent-browser upload @ref` fails with "CDP error
  (DOM.describeNode): Object id doesn't reference a Node" on a "Click to upload or drop
  files" button, (3) automating submission forms on *.hf.space apps behind HF OAuth.
author: Claude Code
version: 1.0.0
date: 2026-08-26
---

# Gradio Space form automation gotchas (agent-browser)

## Tab switching

Gradio renders TWO copies of every tab button: a `visually-hidden` measurement container
(`div.tab-container.visually-hidden`, aria-hidden) AND the real
`div[role="tablist"]`. The hidden copies pass `offsetParent` checks (hidden by clipping,
not display:none), so text-based queries and even `find role tab click` can hit the inert
copy: the click "succeeds" but the tab never switches. Target the real one explicitly:

```js
Array.from(document.querySelectorAll('[role="tablist"] button[role="tab"]'))
  .find(b => b.textContent.trim() === 'My Tab').click()
```

Verify the switch by re-snapshotting for `[selected]` on the target tab, never by the
click's exit status.

## File uploads

`agent-browser upload @eNN file` fails when the ref points at the styled
"Click to upload or drop files" button. Target the native hidden input by CSS attribute
selector instead; Gradio sets each input's `accept` from the component's `file_types`, so
multiple upload fields are distinguishable:

```sh
agent-browser upload 'input[type="file"][accept=".csv"]' ./predictions.csv
agent-browser upload 'input[type="file"][accept=".pdf, .md"]' ./report.md
```

Verify by snapshotting for the uploaded filename appearing in the component.

## HF OAuth sign-in

The "Sign in with Hugging Face" flow works headed with a live huggingface.co login:
navigate to `<space-url>/login/huggingface`, which chains
login -> oauth/authorize -> Space callback. Caveat: agent-browser `--session-name`
state save does NOT reliably restore huggingface.co session cookies across `close`
(secure-cookie constraints); plan for the user to re-login per browser lifetime and keep
the browser open until the whole flow is done.

## Also

- Page may load scrolled or with floating header pills intercepting clicks; screenshot
  (`--annotate`) when clicks mysteriously no-op.
- Gradio result panels (scores, confirmations) read cleanly from `snapshot` StaticText
  lines; grep for the confirmation heading first.
