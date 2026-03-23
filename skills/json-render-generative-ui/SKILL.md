---
name: json-render-generative-ui
description: |
  Build Generative UI with @json-render — the Vercel Labs framework that lets AI generate
  dynamic interfaces constrained to a predefined component catalog. Use when:
  (1) the user wants to create AI-generated UIs with json-render,
  (2) the user asks about building generative UI, AI-driven interfaces, or dynamic rendering,
  (3) the user needs to define a json-render catalog, registry, or spec,
  (4) the user is working with @json-render/core, @json-render/react, @json-render/react-native,
      or @json-render/remotion,
  (5) the user wants to stream AI-generated UI specs to React components.
  Covers catalog definition, component registries, spec rendering, streaming, dynamic props,
  actions, state management, and the React Native / Remotion integrations.
author: Claude Code
version: 1.0.0
date: 2026-02-15
---

# json-render — Generative UI Framework

## Problem

AI-generated UIs are unpredictable and unsafe if the model can output arbitrary markup.
json-render solves this by constraining AI output to a typed component catalog you define,
producing a flat JSON spec that maps to real React (or React Native / Remotion) components.
The result is guardrailed, predictable, and supports progressive streaming.

## Context / Trigger Conditions

- User asks about building generative UI or AI-driven interfaces
- User wants to define or modify a json-render catalog
- User is working with `@json-render/core`, `@json-render/react`, `@json-render/react-native`, or `@json-render/remotion`
- User needs to create a component registry or render a spec
- User asks about streaming AI-generated UI specs
- User wants dynamic props, conditional visibility, or action handling in json-render

## Solution

### Installation

```bash
# React (web)
npm install @json-render/core @json-render/react

# React Native (mobile)
npm install @json-render/core @json-render/react-native

# Remotion (video)
npm install @json-render/core @json-render/remotion
```

### Package Ecosystem

| Package | Purpose |
| --- | --- |
| `@json-render/core` | Schemas, catalogs, prompts, dynamic props, streaming utilities |
| `@json-render/react` | React renderer, contexts, hooks |
| `@json-render/react-native` | Mobile renderer with 25+ standard components |
| `@json-render/remotion` | Video rendering with timeline-based specs |

### Step 1: Define a Catalog

A catalog declares which components and actions the AI is allowed to use, with Zod schemas for type safety.

```typescript
import { defineCatalog } from '@json-render/core';
import { schema } from '@json-render/react';
import { z } from 'zod';

const catalog = defineCatalog(schema, {
  components: {
    Card: {
      props: z.object({ title: z.string() }),
      description: 'A card container',
    },
    Metric: {
      props: z.object({
        label: z.string(),
        value: z.string(),
        format: z.enum(['currency', 'percent', 'number']).nullable(),
      }),
      description: 'Display a metric value',
    },
    Button: {
      props: z.object({
        label: z.string(),
        action: z.string(),
      }),
      description: 'Clickable button',
    },
  },
  actions: {
    export_report: { description: 'Export dashboard to PDF' },
    refresh_data: { description: 'Refresh all metrics' },
  },
});
```

### Step 2: Define a React Registry

Map catalog component names to actual React implementations.

```typescript
import { defineRegistry, Renderer } from '@json-render/react';

const { registry } = defineRegistry(catalog, {
  components: {
    Card: ({ props, children }) => (
      <div className="card">
        <h3>{props.title}</h3>
        {children}
      </div>
    ),
    Metric: ({ props }) => (
      <div className="metric">
        <span>{props.label}</span>
        <span>{props.value}</span>
      </div>
    ),
    Button: ({ props, emit }) => (
      <button onClick={() => emit('press')}>
        {props.label}
      </button>
    ),
  },
});
```

### Step 3: Render a Spec

A spec is a flat JSON structure the AI generates. Pass it to `<Renderer />`.

```typescript
function Dashboard({ spec }) {
  return <Renderer spec={spec} registry={registry} />;
}
```

### Spec Format

Specs use a flat element map with a root pointer:

```json
{
  "root": "card-1",
  "elements": {
    "card-1": {
      "type": "Card",
      "props": { "title": "Dashboard" },
      "children": ["metric-1", "button-1"]
    },
    "metric-1": {
      "type": "Metric",
      "props": { "label": "Revenue", "value": "$12,345", "format": "currency" },
      "children": []
    },
    "button-1": {
      "type": "Button",
      "props": { "label": "Export", "action": "export_report" },
      "children": []
    }
  }
}
```

### Streaming AI Responses

Use `createSpecStreamCompiler` to progressively render as the model responds:

```typescript
import { createSpecStreamCompiler } from '@json-render/core';

const compiler = createSpecStreamCompiler();

for await (const chunk of aiStream) {
  const { result, newPatches } = compiler.push(chunk);
  setSpec(result);
}

const finalSpec = compiler.getResult();
```

### Generating a System Prompt from the Catalog

Auto-generate an LLM system prompt that describes available components and actions:

```typescript
const systemPrompt = catalog.prompt();
```

### Dynamic Props with State Expressions

Reference internal state or use conditional expressions in props:

```json
{
  "type": "Icon",
  "props": {
    "name": {
      "$cond": { "$state": "/activeTab", "eq": "home" },
      "$then": "home",
      "$else": "home-outline"
    },
    "colour": { "$state": "/themeColour" }
  }
}
```

### Conditional Visibility

Control element visibility based on state:

```json
{
  "type": "Alert",
  "props": { "message": "Error occurred" },
  "visible": [
    { "$state": "/form/hasError" },
    { "$state": "/form/errorDismissed", "not": true }
  ]
}
```

### Actions and setState

Components trigger named actions. The built-in `setState` action updates internal state:

```json
{
  "type": "Pressable",
  "props": {
    "action": "setState",
    "actionParams": {
      "statePath": "/activeTab",
      "value": "home"
    }
  }
}
```

### React Native Usage

Use the 25+ standard mobile components:

```typescript
import { defineCatalog } from '@json-render/core';
import { schema } from '@json-render/react-native/schema';
import {
  standardComponentDefinitions,
  standardActionDefinitions,
} from '@json-render/react-native/catalog';

const catalog = defineCatalog(schema, {
  components: { ...standardComponentDefinitions },
  actions: standardActionDefinitions,
});
```

### Remotion (Video) Integration

Generate videos via timeline specs:

```typescript
const spec = {
  composition: {
    id: 'video',
    fps: 30,
    width: 1920,
    height: 1080,
    durationInFrames: 300,
  },
  tracks: [
    { id: 'main', name: 'Main', type: 'video', enabled: true },
  ],
  clips: [
    {
      id: 'clip-1',
      trackId: 'main',
      component: 'TitleCard',
      props: { title: 'Hello' },
      from: 0,
      durationInFrames: 90,
    },
  ],
  audio: { tracks: [] },
};
```

## Verification

1. Install packages: `npm install @json-render/core @json-render/react`
2. Define a catalog with at least one component
3. Create a registry mapping the component to a React implementation
4. Render a hardcoded spec with `<Renderer />` to confirm it works
5. Then integrate with an AI model to generate specs dynamically

## Example

**Scenario**: User wants to build an AI-powered dashboard that generates UI from a prompt.

1. Define catalog with Card, Metric, Chart, Button components
2. Create registry mapping each to styled React components
3. Generate system prompt with `catalog.prompt()`
4. Send user query + system prompt to LLM
5. Stream the response through `createSpecStreamCompiler`
6. Render the progressive spec with `<Renderer />`

## Notes

- Requires `zod` as a peer dependency for schema definitions
- The catalog constrains AI output — the model can only use components you define
- Specs are flat (not nested trees) for streaming compatibility
- `catalog.prompt()` auto-generates an LLM-ready system prompt from your component definitions
- The `$state`, `$cond`/`$then`/`$else` expression system enables reactive UIs without custom code
- React Native package includes 25+ pre-built standard components
- Remotion integration uses a timeline-based spec format (different from the element-based web/mobile format)
- Apache-2.0 licence
- Source: https://github.com/vercel-labs/json-render
