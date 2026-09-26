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
development (`vite.config.ts`) and the backend serves `dist/` itself in
production. Keep it that way. The session cookie is `SameSite=Strict`, so an
API on another origin never receives it and sign-in silently fails.
