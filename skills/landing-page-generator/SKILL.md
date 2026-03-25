---
name: landing-page-generator
description: Generate complete, production-quality animated landing pages using one-shot prompts. Use this skill whenever the user asks to create a landing page, build a hero section, design a SaaS page, create a website homepage, scaffold a marketing site, or build any kind of animated web page. Also trigger when the user mentions "landing page prompt", "hero section", "glassmorphism site", "animated website", "liquid glass design", or wants to build a dark/light themed promotional page with React, Tailwind, and Framer Motion. Even if the user just says "make me a website" or "build a page for my product", this skill is likely relevant.
metadata:
  author: michaldobiezynski
  version: "1.0.0"
---

# Landing Page Generator

Generate complete, animated landing pages from a single prompt using a battle-tested structure that produces consistent, high-quality results with AI coding tools.

## Why This Structure Works

AI coding tools produce far better landing pages when given a systematic, section-by-section specification rather than a vague description. The pattern below front-loads the design system (fonts, colours, utilities) so every component inherits consistent styling, then specifies each section with exact Tailwind classes and layout details. This eliminates the guesswork that causes AI tools to produce inconsistent, generic output.

## Prompt Construction Workflow

When the user asks for a landing page, follow these steps:

### Step 1: Gather Requirements

Ask the user for:
- **Company/product name** and what it does (one sentence)
- **Theme preference**: dark, light, or specific mood (cinematic, editorial, clean, etc.)
- **Accent colour**: or let the user pick from the presets below
- **Sections needed**: hero only, or full page (features, testimonials, pricing, CTA, footer)
- **Background style**: solid colour, gradient, or video background
- **Animation level**: minimal (fade-ins only), moderate (staggered entrances), or rich (scroll-triggered, parallax, marquee)

### Step 2: Assemble the Design System

Every prompt begins with the global design system. This is the foundation — get this right and the sections almost write themselves.

#### Font Pairing (pick one)

| Heading Font | Body Font | Vibe | Google Fonts Import |
|---|---|---|---|
| Instrument Serif (italic) | Inter (400, 500, 600) | Editorial luxury | `family=Instrument+Serif:ital@0;1&family=Inter:wght@400;500;600` |
| Akshar (400–700) | Inter (400–700) | Corporate tech | `family=Akshar:wght@400;500;600;700&family=Inter:wght@400;500;600;700` |
| Geist Sans (400–700) | Geist Sans | Clean SaaS | Install `@fontsource/geist-sans` |
| Space Grotesk (400–700) | Inter (400–600) | Modern startup | `family=Space+Grotesk:wght@400;500;600;700&family=Inter:wght@400;500;600` |
| Playfair Display (400–700) | Barlow (300–600) | Premium agency | `family=Playfair+Display:wght@400;500;600;700&family=Barlow:wght@300;400;500;600` |

Configure in Tailwind as `font-heading` and `font-body`. Apply `font-body` to `<body>` and `font-heading` to h1, h2, h3 in the base layer.

#### Colour Palette Presets

**Dark Premium**
```css
:root {
  --background: 260 87% 3%;
  --foreground: 40 6% 95%;
  --primary: 121 95% 76%;
  --primary-foreground: 0 0% 5%;
  --secondary: 240 4% 16%;
  --border: 240 4% 20%;
  --card: 240 6% 9%;
  --muted: 240 4% 16%;
  --muted-foreground: 240 5% 65%;
  --radius: 0.75rem;
}
```

**Dark Cinematic**
```css
:root {
  --background: 213 45% 67%;
  --foreground: 0 0% 100%;
  --primary: 0 0% 100%;
  --primary-foreground: 213 45% 67%;
  --border: 0 0% 100% / 0.2;
  --ring: 0 0% 100% / 0.3;
  --radius: 9999px;
}
```

**Light Clean**
```css
:root {
  --background: 0 0% 100%;
  --foreground: 210 14% 17%;
  --primary: 210 14% 17%;
  --primary-foreground: 0 0% 100%;
  --accent: 239 84% 67%;
  --accent-foreground: 0 0% 100%;
  --border: 0 0% 90%;
  --muted-foreground: 184 5% 55%;
  --radius: 0.5rem;
}
```

**Light Corporate**
```css
:root {
  --background: 0 0% 100%;
  --foreground: 220 20% 20%;
  --primary: 212 72% 18%;
  --primary-foreground: 0 0% 100%;
  --muted-foreground: 220 10% 50%;
  --radius: 0.5rem;
}
```

All colours use HSL format. Map all in `tailwind.config.ts` as `hsl(var(--token))`.

#### Liquid Glass Utility (for dark/glassmorphism themes)

When the user wants a glassmorphism aesthetic, include this CSS utility class in the prompt:

```css
@layer utilities {
  .liquid-glass {
    background: rgba(255, 255, 255, 0.01);
    background-blend-mode: luminosity;
    backdrop-filter: blur(4px);
    -webkit-backdrop-filter: blur(4px);
    border: none;
    box-shadow: inset 0 1px 1px rgba(255, 255, 255, 0.1);
    position: relative;
    overflow: hidden;
  }
  .liquid-glass::before {
    content: '';
    position: absolute;
    inset: 0;
    border-radius: inherit;
    padding: 1.4px;
    background: linear-gradient(180deg,
      rgba(255,255,255,0.45) 0%,
      rgba(255,255,255,0.15) 20%,
      transparent 40%,
      transparent 60%,
      rgba(255,255,255,0.15) 80%,
      rgba(255,255,255,0.45) 100%
    );
    -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
    -webkit-mask-composite: xor;
    mask-composite: exclude;
    pointer-events: none;
  }
  .liquid-glass-strong {
    backdrop-filter: blur(50px);
    box-shadow: 4px 4px 4px rgba(0,0,0,0.05), inset 0 1px 1px rgba(255,255,255,0.15);
  }
}
```

### Step 3: Build the Section Specs

For each section, specify: layout, positioning, exact Tailwind classes, content, and any animations. The key principle is to be explicit about classes and structure — ambiguity produces generic results.

#### Section Templates

**Navbar**
```
Fixed at top, z-50, [px and py values]
Left: [Logo — image or text + icon]
Centre/Right: Nav links in a [pill/bar/plain] container: [list items]
  Link styles: text-sm font-medium text-foreground/90
CTA: [Button text] — [style: rounded-full, primary colour, etc.]
Nav links hidden on mobile (hidden md:flex)
```

**Hero (full-screen with video background)**
```
min-h-screen, centred flex column, overflow-hidden
Background: <video> element with autoPlay muted loop playsInline
  src="[VIDEO_URL]"
  Classes: absolute inset-0 w-full h-full object-cover z-0
Gradient overlay (absolute, pointer-events-none):
  linear-gradient(to bottom, transparent 0%, transparent 30%, hsl(var(--background) / 0.4) 60%, hsl(var(--background)) 95%)

Content (relative z-10, flex column, centred):
- [Optional] Announcement badge: [pill style] with text
- Heading: "[TEXT]"
  Classes: text-4xl sm:text-6xl lg:text-7xl font-semibold leading-[1.05] tracking-tight max-w-5xl
- Subheading: "[TEXT]"
  Classes: text-lg max-w-md mt-4 opacity-80
- CTA Buttons: "[PRIMARY]" (primary) + "[SECONDARY]" (ghost/secondary)
- [Optional] Social proof: logo marquee or "Trusted by" bar
```

**Features (card grid)**
```
Background: [solid / video with gradient overlays top and bottom]
Header: badge pill + heading + subtext
Grid: grid md:grid-cols-3 gap-6
Each card: [liquid-glass / bordered] rounded-3xl p-8
  - Icon or emoji
  - Title (text-lg font-semibold)
  - Description (text-muted-foreground)
  - [Optional] Stat highlight (e.g. "3.2x faster")
```

**Content Section (alternating chess layout)**
```
Grid: lg:grid-cols-2 gap-20 items-centre
Side A — Video/Image: liquid-glass rounded-3xl aspect-[4/3] overflow-hidden
Side B — Content:
  - Badge pill
  - Heading
  - Body paragraph
  - Bullet list (3-4 items with coloured dots)
  - CTA buttons
[Reverse on alternate sections using order- classes]
```

**Testimonials**
```
3-column card grid
Each card: [glass/bordered] rounded-3xl p-8
  - Quoted text
  - Divider
  - Avatar circle with initials + name + role
[Optional: offset middle card with md:-translate-y-6]
```

**CTA Section**
```
Centred card: [glass/bordered] rounded-[2rem] p-12 sm:p-20
  - Heading
  - Subtext
  - Two CTA buttons
```

**Footer**
```
[N]-column grid: Brand column (2-col span) + link columns
Bottom bar: copyright + legal links
Border: border-t border-border/30
```

### Step 4: Add Animations

**Framer Motion fade-up (staggered)**
```tsx
initial={{ opacity: 0, y: 16 }}
animate={{ opacity: 1, y: 0 }}
transition={{ duration: 0.6, delay: 0.1 * index }}
```

**Blur-in text (word by word)**
Uses IntersectionObserver. Each word animates from `filter: blur(10px)` to `blur(0px)` with y-axis movement, staggered 100ms per word.

**Infinite marquee**
```js
marquee: {
  "0%": { transform: "translateX(0%)" },
  "100%": { transform: "translateX(-50%)" }
}
```

### Step 5: List Dependencies

Always end the prompt with a clear dependency list:
```
KEY DEPENDENCIES
- react, react-dom
- tailwindcss, tailwindcss-animate
- framer-motion (motion/react)
- lucide-react (icons)
- shadcn/ui (Button, Badge components)
- [hls.js — only if using HLS video streams]
- [font package if using @fontsource]
```

And a page structure summary:
```
PAGE STRUCTURE (Index.tsx)
<NavBar />
<HeroSection />
<FeaturesSection />
...
```

## Tech Stack

The default stack for these prompts is:
- **React + Vite + TypeScript** — fast scaffolding, type safety
- **Tailwind CSS** — utility-first styling with design tokens
- **shadcn/ui** — accessible component primitives
- **Framer Motion** — entrance and scroll animations
- **Lucide React** — consistent icon set
- **hls.js** — only when streaming video backgrounds (use plain `<video>` for MP4s)

## Tips for Best Results

- Always specify the font import URL explicitly — AI tools often hallucinate font names
- Include exact Tailwind class strings for critical elements (headings, buttons, cards)
- For video backgrounds, always specify: `autoPlay muted loop playsInline` and `object-cover`
- Add gradient overlays on video backgrounds to ensure text readability
- Specify mobile breakpoints explicitly (`hidden md:flex`, responsive text sizes)
- The more specific the colour tokens, the more consistent the output
