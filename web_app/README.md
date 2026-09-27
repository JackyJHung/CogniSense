# CogniSense web client

React 19 + TypeScript + Vite + Tailwind CSS v4. Installable as a web app
(`public/manifest.webmanifest`), with a service worker (`public/sw.js`) that
exists only to show push notifications. The project's documentation is the
[top-level README](../README.md).

```bash
npm ci
npm run dev      # http://localhost:5173, with the backend on 127.0.0.1:8000
npm run lint
npm run build    # type-checks, then writes dist/ -- which the backend serves
```

The API is reached at `/api` on the page's own origin: Vite proxies it in
development (`vite.config.ts`), and in production the backend serves `dist/`
and answers `/api` itself. Keep it that way. The session cookie is `SameSite=Strict`, so an
API on another origin never receives it and sign-in silently fails.

The interface follows Apple's Human Interface Guidelines. Colours, the type
ramp and backgrounds are design tokens in `src/index.css`, each with its dark
pair, so components write `text-label` or `bg-surface` rather than a light and
a dark class. The building blocks are in `src/components/ui/` (grouped lists,
segmented control, buttons, fields), and `src/components/Shell.tsx` is the
frame: large titles, the navigation bar, the tab bar and the sidebar.
