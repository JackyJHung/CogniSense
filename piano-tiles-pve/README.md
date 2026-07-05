# Piano Tiles PvE

A competitive Piano Tiles game you can play in your phone's browser. Tap the falling tiles
in time to build a melody, race a live AI opponent's score, and climb the on-device leaderboard.
Pure HTML/CSS/JS — no build step, no dependencies, works offline once loaded.

## Features

- **4-lane falling tiles** rendered on canvas, tap the colored tile before it passes the hit zone
- **Music**: every correct tap plays a pentatonic note (they always sound musical together) over a
  procedurally generated background bassline, all synthesized live with the Web Audio API
- **PvE**: an AI opponent "watches" the same tile stream and racks up its own score in real time —
  beat its final score to win
- **3 difficulty levels** (Easy / Medium / Hard) — each changes fall speed, tile frequency, hit-zone
  size, and AI accuracy; speed also ramps up the longer a run lasts
- **Local scoreboard**: top 10 scores per difficulty saved with `localStorage`, tagged win/draw/loss
  vs the AI
- Installable as a home-screen app (PWA manifest + offline service worker)

## Run it on your phone

Any of these work — pick whichever is easiest:

### Option A: GitHub Pages (best for a real "app" experience)
Enable GitHub Pages for this repo (Settings → Pages → serve from this branch), then open
`https://<your-username>.github.io/<repo>/piano-tiles-pve/` on your phone and use
"Add to Home Screen" for a full-screen installed app.

### Option B: Local server on your computer, open from your phone
```bash
cd piano-tiles-pve
python3 -m http.server 8000
```
Then, with your phone on the same Wi-Fi, open `http://<your-computer's-LAN-IP>:8000` in the
phone's browser.

### Option C: Just open the file
Copy the `piano-tiles-pve` folder to your phone and open `index.html` directly in the browser.
The game works fully this way; only the installable-offline (service worker) part needs a real
`http(s)://` origin.

## How to play

1. Enter your name, pick a difficulty, tap **Start Game**.
2. Tap the lane with the colored tile as it reaches the glowing zone near the bottom.
3. Missing a tile, or tapping a lane with nothing there, ends the run.
4. Your final score is compared to the AI's — win, lose, or draw — and saved to that
   difficulty's leaderboard.

## Files

- `index.html` — markup for menu, game, pause, game-over, and leaderboard screens
- `style.css` — mobile-first dark theme, HUD, overlays
- `game.js` — game loop, canvas rendering, Web Audio music/SFX, AI opponent, localStorage
  scoreboard, and UI wiring
- `manifest.json` / `sw.js` / `icon-*.png` — PWA install + offline support
