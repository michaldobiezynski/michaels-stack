---
name: video-background-generator
description: Generate prompts for creating looping video backgrounds for websites using Grok, Kling, Runway, or other AI video tools. Use this skill whenever the user asks to create a video background, generate a background video, make a looping video for a website, create an atmospheric video, generate a video prompt for Grok, or needs ambient/abstract video content for a landing page or hero section. Also trigger when the user mentions "video background", "looping video", "ambient video", "Grok video", "Kling video", "website video", or wants to create motion content for behind text on a web page.
metadata:
  author: michaldobiezynski
  version: "1.0.0"
---

# Video Background Generator

Generate optimised prompts for AI video tools (Grok, Kling, Runway, Nano Banana) that produce seamlessly looping, atmospheric video backgrounds for websites and landing pages.

## Why Video Backgrounds Need Special Prompts

Generic video generation prompts produce content that's too busy, too short, or too distracting to work behind text on a landing page. The prompts below are designed to produce slow, abstract, atmospheric loops that serve as a visual layer without competing with foreground content. The key constraints are: slow movement, abstract/out-of-focus visuals, and seamless loopability.

## Prompt Construction

When the user asks for a video background, follow this process:

### Step 1: Match the Video to the Page Theme

Ask what the landing page looks like (or check if the landing-page-generator skill has already been used). The video must complement the page's colour palette and mood.

| Page Theme | Video Style | Colour Guidance |
|---|---|---|
| Dark SaaS / Tech | Abstract fluid, particles, neural networks | Deep purples, blacks, green/cyan accents |
| Dark Cinematic | Smoke, ink, liquid, volumetric fog | Navy, charcoal, occasional gold |
| Light Clean | Soft gradients, light refractions, bokeh | Whites, pastels, subtle blues |
| Light Corporate | Aerial cityscapes, nature macro, water | Warm tones, golden hour, soft focus |
| Futuristic / AI | Data visualisation, glowing nodes, grids | Electric blue, cyan, white on dark |
| Organic / Natural | Ink in water, plant macro, clouds | Earth tones, deep greens, amber |

### Step 2: Build the Prompt

Every video background prompt follows this structure:

```
Create a [DURATION]-second seamlessly looping video.

[VISUAL DESCRIPTION — 2-3 sentences describing the scene. Keep it abstract and slow-moving.]

Colour palette: [SPECIFIC COLOURS that match the landing page theme]
Movement: Slow, smooth, continuous. Must loop seamlessly.
Style: [Cinematic / abstract / organic / technological / editorial]
Camera: [Static / very slow dolly / slow orbit / fixed macro]
No text, no people, no UI elements. Pure atmospheric background.
[RESOLUTION — 4K / 1080p]
```

The critical constraints that make these work as backgrounds:
- **"Seamlessly looping"** — without this, there's a visible jump when the video restarts
- **"Slow, smooth, continuous"** — fast movement distracts from foreground content
- **"No text, no people, no UI"** — prevents visual competition with page content
- **Abstract/out-of-focus** — keeps the video as atmosphere, not a focal point

### Step 3: Duration and Format Guidance

- **Duration**: 5-10 seconds is the sweet spot. Shorter loops are smaller files and loop more seamlessly. Longer loops risk visible seam points.
- **Resolution**: Request 4K if the tool supports it — you can always downscale but can't upscale
- **Output format**: MP4 with H.264 codec is the web standard
- **File size target**: Under 5MB for hero backgrounds, under 10MB for full-page backgrounds

## Ready-to-Use Prompt Library

### Dark SaaS / Tech
```
Create a 5-second seamlessly looping video. Slow-moving dark abstract fluid simulation with deep purples, blacks, and occasional green luminescent particles floating through the frame. Cinematic lighting with volumetric fog. Very slow movement — this is a website background. No text, no people. 4K quality, photorealistic.
```

### Liquid Glass / Glassmorphism
```
Create a 5-second seamlessly looping video. Abstract translucent glass spheres and planes slowly rotating and refracting light against a deep black background. Subtle caustic light patterns. Colours: cool whites, soft blues, hints of violet. Ultra-slow motion. Cinematic depth of field. No text, no UI. 4K.
```

### Corporate / Professional
```
Create a 5-second seamlessly looping video. Aerial view of a modern city skyline at golden hour, extremely slow camera drift. Warm tones, soft focus, cinematic colour grading. Tilt-shift effect to give miniature feel. No text overlays. 4K quality.
```

### Abstract Organic
```
Create a 5-second seamlessly looping video. Macro shot of ink slowly diffusing in water. Deep navy and black tones with occasional gold shimmer. Extremely slow motion, almost meditative. Shot from above, soft lighting. No text, no objects. 4K.
```

### Futuristic / AI / Neural
```
Create a 5-second seamlessly looping video. Neural network visualisation — glowing nodes and connections pulsing with soft light against a dark background. Colours: electric blue, white, subtle cyan. Slow rotation through the network. Volumetric, 3D depth. No text. 4K.
```

### Smoke / Cinematic Dark
```
Create a 5-second seamlessly looping video. Wisps of smoke slowly curling and drifting against a pure black background. Side-lit with a single warm amber light source. Extremely slow motion. Volumetric and atmospheric. No text, no objects. 4K.
```

### Light / Ethereal
```
Create a 5-second seamlessly looping video. Soft light caustics rippling across a white surface, as if sunlight is refracting through gently moving water above. Pastel blue and gold tints. Dreamy, ethereal mood. Very slow movement. No text, no people. 4K.
```

### Geometric / Minimal
```
Create a 5-second seamlessly looping video. Minimal geometric shapes — thin white lines and circles — slowly rotating and intersecting against a deep navy background. Clean, mathematical precision. Bauhaus-inspired. Very slow movement. No text. 4K.
```

## Tool-Specific Notes

### Grok (on X/Twitter)
- Access via the Grok interface on X or grok.com
- Supports video generation directly from text prompts
- Good at abstract and artistic styles
- Specify "seamlessly looping" explicitly — it doesn't loop by default

### Kling
- Strong at cinematic quality and realistic motion
- Supports longer generations (up to 10s)
- Pair with Nano Banana for even better results (generate the initial frame in Nano Banana, then animate in Kling)
- Best for: smoke, fluid, nature macro shots

### Runway Gen-3
- Excellent motion control and consistency
- Supports image-to-video (generate a still frame first, then animate)
- Good for: abstract, geometric, and light-based backgrounds

### Nano Banana
- Primarily an image generator, but useful for creating the initial keyframe
- Generate a high-quality still → feed into Kling or Runway for animation
- Best for: establishing the exact aesthetic before animation

## Implementation in HTML/React

Once the video is generated, here's how to use it on the page:

```html
<video
  className="absolute inset-0 w-full h-full object-cover z-0"
  src="[VIDEO_URL]"
  autoPlay
  muted
  loop
  playsInline
/>
```

Always add a gradient overlay on top for text readability:

```html
<div
  className="absolute inset-0 z-[1] pointer-events-none"
  style={{
    background: 'linear-gradient(to bottom, transparent 0%, transparent 30%, hsl(var(--background) / 0.4) 60%, hsl(var(--background)) 95%)'
  }}
/>
```

## Hosting

After generating, convert to MP4 (H.264) and host on a CDN:
- **CloudFront** (AWS) — good for global distribution
- **Cloudinary** — auto-optimises video format and quality
- **Vercel Blob** — simple if already using Vercel
- **Bunny.net** — cost-effective CDN with video optimisation

For HLS streaming (larger videos), use **Mux** — it handles adaptive bitrate streaming automatically. Use `hls.js` on the frontend to play HLS streams.
