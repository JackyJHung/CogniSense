(() => {
  'use strict';

  const LANES = 4;
  const LANE_COLORS = ['#4ecdc4', '#7c4dff', '#ff6ec7', '#ffd166'];
  const TAP_NOTES = [261.63, 293.66, 329.63, 392.0]; // C4 D4 E4 G4 (major pentatonic subset)
  const BASS_PATTERN = [130.81, 164.81, 196.0, 164.81]; // C3 E3 G3 E3

  const DIFFICULTIES = {
    easy: { label: 'Easy', fallTime: 1500, minFallTime: 780, spawnInterval: 760, minSpawnInterval: 430,
      hitZoneRatio: 0.24, aiAccuracy: 0.7, tempo: 96, speedUpEvery: 15, speedUpFactor: 0.97 },
    medium: { label: 'Medium', fallTime: 1150, minFallTime: 580, spawnInterval: 600, minSpawnInterval: 330,
      hitZoneRatio: 0.17, aiAccuracy: 0.85, tempo: 126, speedUpEvery: 15, speedUpFactor: 0.965 },
    hard: { label: 'Hard', fallTime: 850, minFallTime: 440, spawnInterval: 450, minSpawnInterval: 250,
      hitZoneRatio: 0.13, aiAccuracy: 0.95, tempo: 156, speedUpEvery: 15, speedUpFactor: 0.96 },
  };

  // ---------------------------------------------------------------------
  // Storage
  // ---------------------------------------------------------------------
  const Storage = {
    SCORES_KEY: 'pianoTilesPve.scores.v1',
    NAME_KEY: 'pianoTilesPve.playerName',
    DIFF_KEY: 'pianoTilesPve.lastDifficulty',

    loadScores() {
      try {
        const raw = localStorage.getItem(this.SCORES_KEY);
        const parsed = raw ? JSON.parse(raw) : {};
        return { easy: [], medium: [], hard: [], ...parsed };
      } catch {
        return { easy: [], medium: [], hard: [] };
      }
    },

    saveEntry(difficulty, entry) {
      const scores = this.loadScores();
      scores[difficulty].push(entry);
      scores[difficulty].sort((a, b) => b.score - a.score || new Date(b.date) - new Date(a.date));
      scores[difficulty] = scores[difficulty].slice(0, 10);
      localStorage.setItem(this.SCORES_KEY, JSON.stringify(scores));
      return scores[difficulty];
    },

    getBest(difficulty) {
      const list = this.loadScores()[difficulty] || [];
      return list.length ? list[0].score : 0;
    },

    getName() {
      return localStorage.getItem(this.NAME_KEY) || '';
    },
    setName(name) {
      localStorage.setItem(this.NAME_KEY, name);
    },
    getLastDifficulty() {
      return localStorage.getItem(this.DIFF_KEY) || 'medium';
    },
    setLastDifficulty(d) {
      localStorage.setItem(this.DIFF_KEY, d);
    },
  };

  // ---------------------------------------------------------------------
  // Audio
  // ---------------------------------------------------------------------
  class AudioEngine {
    constructor() {
      this.ctx = null;
      this.master = null;
      this.muted = false;
      this.bgTimer = null;
      this.bgStep = 0;
    }

    ensureContext() {
      if (this.ctx) return;
      const Ctx = window.AudioContext || window.webkitAudioContext;
      this.ctx = new Ctx();
      this.master = this.ctx.createGain();
      this.master.gain.value = this.muted ? 0 : 0.9;
      this.master.connect(this.ctx.destination);
    }

    resume() {
      this.ensureContext();
      if (this.ctx.state === 'suspended') this.ctx.resume();
    }

    setMuted(muted) {
      this.muted = muted;
      if (this.master) this.master.gain.value = muted ? 0 : 0.9;
    }

    playTone(freq, { duration = 0.18, type = 'triangle', peak = 0.22, delay = 0 } = {}) {
      if (!this.ctx) return;
      const t0 = this.ctx.currentTime + delay;
      const osc = this.ctx.createOscillator();
      const gain = this.ctx.createGain();
      osc.type = type;
      osc.frequency.setValueAtTime(freq, t0);
      gain.gain.setValueAtTime(0, t0);
      gain.gain.linearRampToValueAtTime(peak, t0 + 0.012);
      gain.gain.exponentialRampToValueAtTime(0.0001, t0 + duration);
      osc.connect(gain).connect(this.master);
      osc.start(t0);
      osc.stop(t0 + duration + 0.02);
    }

    playTap(freq) {
      this.playTone(freq, { duration: 0.22, type: 'triangle', peak: 0.28 });
      this.playTone(freq * 2, { duration: 0.15, type: 'sine', peak: 0.06 });
    }

    playMiss() {
      if (!this.ctx) return;
      const t0 = this.ctx.currentTime;
      const osc = this.ctx.createOscillator();
      const gain = this.ctx.createGain();
      osc.type = 'sawtooth';
      osc.frequency.setValueAtTime(160, t0);
      osc.frequency.exponentialRampToValueAtTime(50, t0 + 0.35);
      gain.gain.setValueAtTime(0.3, t0);
      gain.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.4);
      osc.connect(gain).connect(this.master);
      osc.start(t0);
      osc.stop(t0 + 0.42);
    }

    startBackground(tempo) {
      this.stopBackground();
      this.bgStep = 0;
      const beatMs = 60000 / tempo;
      const playBeat = () => {
        const note = BASS_PATTERN[this.bgStep % BASS_PATTERN.length];
        this.playTone(note, { duration: beatMs / 1000 * 0.9, type: 'sine', peak: 0.07 });
        this.bgStep++;
      };
      playBeat();
      this.bgTimer = setInterval(playBeat, beatMs);
    }

    stopBackground() {
      if (this.bgTimer) {
        clearInterval(this.bgTimer);
        this.bgTimer = null;
      }
    }
  }

  // ---------------------------------------------------------------------
  // Game engine
  // ---------------------------------------------------------------------
  class Game {
    constructor(canvas, audio) {
      this.canvas = canvas;
      this.ctx = canvas.getContext('2d');
      this.audio = audio;
      this.width = 0;
      this.height = 0;
      this.tileHeight = 0;
      this.reset('medium');

      this.onScoreChange = null;
      this.onGameOver = null;

      canvas.addEventListener('pointerdown', (e) => {
        e.preventDefault();
        this.handlePointer(e.clientX);
      }, { passive: false });
    }

    reset(difficultyKey) {
      this.difficultyKey = difficultyKey;
      this.settings = { ...DIFFICULTIES[difficultyKey] };
      this.tiles = [];
      this.flashes = [];
      this.score = 0;
      this.aiScore = 0;
      this.combo = 0;
      this.clock = 0;
      this.spawnTimer = 0;
      this.state = 'idle';
      this.rafId = null;
      this.lastFrameTime = null;
    }

    resizeCanvas() {
      const dpr = window.devicePixelRatio || 1;
      const rect = this.canvas.getBoundingClientRect();
      this.width = rect.width;
      this.height = rect.height;
      this.canvas.width = Math.max(1, Math.round(rect.width * dpr));
      this.canvas.height = Math.max(1, Math.round(rect.height * dpr));
      this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      this.tileHeight = this.height * 0.16;
    }

    start() {
      this.state = 'playing';
      this.lastFrameTime = performance.now();
      this.loop();
    }

    pause() {
      if (this.state !== 'playing') return;
      this.state = 'paused';
      if (this.rafId) cancelAnimationFrame(this.rafId);
      this.audio.stopBackground();
    }

    resumeGame() {
      if (this.state !== 'paused') return;
      this.state = 'playing';
      this.lastFrameTime = performance.now();
      this.audio.startBackground(this.settings.tempo);
      this.loop();
    }

    loop() {
      if (this.state !== 'playing') return;
      const now = performance.now();
      let dt = now - this.lastFrameTime;
      this.lastFrameTime = now;
      dt = Math.min(dt, 48);
      this.update(dt);
      this.render();
      this.rafId = requestAnimationFrame(() => this.loop());
    }

    update(dt) {
      this.clock += dt;
      this.spawnTimer += dt;
      if (this.spawnTimer >= this.settings.spawnInterval) {
        this.spawnTimer = 0;
        this.spawnTile();
      }

      const zoneTop = this.height * (1 - this.settings.hitZoneRatio);

      for (const tile of this.tiles) {
        if (tile.hit) continue;
        const progress = (this.clock - tile.spawnedAt) / this.settings.fallTime;
        tile.y = progress * (this.height + this.tileHeight) - this.tileHeight;
        const bottom = tile.y + this.tileHeight;

        if (!tile.aiResolved && bottom >= zoneTop) {
          tile.aiResolved = true;
          if (tile.aiWillHit) {
            this.aiScore++;
            this.emitScoreChange();
          }
        }

        if (progress >= 1 && !tile.missed) {
          tile.missed = true;
          this.gameOver('missed');
          return;
        }
      }

      this.tiles = this.tiles.filter((t) => !t.hit && !t.missed);

      for (const f of this.flashes) f.life -= dt / 260;
      this.flashes = this.flashes.filter((f) => f.life > 0);
    }

    spawnTile() {
      const lane = Math.floor(Math.random() * LANES);
      this.tiles.push({
        lane,
        spawnedAt: this.clock,
        y: -this.tileHeight,
        hit: false,
        missed: false,
        aiResolved: false,
        aiWillHit: Math.random() < this.settings.aiAccuracy,
      });
    }

    laneWidth() {
      return this.width / LANES;
    }

    handlePointer(clientX) {
      if (this.state !== 'playing') return;
      const rect = this.canvas.getBoundingClientRect();
      const x = clientX - rect.left;
      const lane = Math.min(LANES - 1, Math.max(0, Math.floor((x / this.width) * LANES)));
      this.handleTap(lane);
    }

    handleTap(lane) {
      const zoneTop = this.height * (1 - this.settings.hitZoneRatio);
      let target = null;
      for (const tile of this.tiles) {
        if (tile.hit || tile.missed || tile.lane !== lane) continue;
        const bottom = tile.y + this.tileHeight;
        if (bottom >= zoneTop && tile.y <= this.height) {
          if (!target || tile.y > target.y) target = tile;
        }
      }

      if (target) {
        target.hit = true;
        this.score++;
        this.combo++;
        this.flashes.push({ lane, life: 1 });
        const octave = (this.combo % 16 >= 8) ? 2 : 1;
        this.audio.playTap(TAP_NOTES[lane] * octave);
        this.maybeSpeedUp();
        this.emitScoreChange();
      } else {
        this.audio.playMiss();
        this.gameOver('wrongTap');
      }
    }

    maybeSpeedUp() {
      const s = this.settings;
      if (this.score > 0 && this.score % s.speedUpEvery === 0) {
        s.fallTime = Math.max(s.minFallTime, s.fallTime * s.speedUpFactor);
        s.spawnInterval = Math.max(s.minSpawnInterval, s.spawnInterval * s.speedUpFactor);
      }
    }

    emitScoreChange() {
      if (this.onScoreChange) this.onScoreChange(this.score, this.aiScore, this.combo);
    }

    gameOver(reason) {
      if (this.state === 'gameover') return;
      this.state = 'gameover';
      this.combo = 0;
      if (this.rafId) cancelAnimationFrame(this.rafId);
      this.audio.stopBackground();
      this.canvas.classList.add('flash-miss');
      setTimeout(() => this.canvas.classList.remove('flash-miss'), 320);
      setTimeout(() => {
        if (this.onGameOver) this.onGameOver(this.score, this.aiScore, reason);
      }, 260);
    }

    render() {
      const ctx = this.ctx;
      ctx.clearRect(0, 0, this.width, this.height);

      const lw = this.laneWidth();

      // lane separators
      ctx.strokeStyle = 'rgba(255,255,255,0.06)';
      ctx.lineWidth = 1;
      for (let i = 1; i < LANES; i++) {
        ctx.beginPath();
        ctx.moveTo(i * lw, 0);
        ctx.lineTo(i * lw, this.height);
        ctx.stroke();
      }

      // hit zone
      const zoneTop = this.height * (1 - this.settings.hitZoneRatio);
      const zoneGrad = ctx.createLinearGradient(0, zoneTop, 0, this.height);
      zoneGrad.addColorStop(0, 'rgba(124,77,255,0.03)');
      zoneGrad.addColorStop(1, 'rgba(124,77,255,0.16)');
      ctx.fillStyle = zoneGrad;
      ctx.fillRect(0, zoneTop, this.width, this.height - zoneTop);
      ctx.strokeStyle = 'rgba(255,255,255,0.18)';
      ctx.beginPath();
      ctx.moveTo(0, zoneTop);
      ctx.lineTo(this.width, zoneTop);
      ctx.stroke();

      // tiles
      for (const tile of this.tiles) {
        const x = tile.lane * lw + lw * 0.08;
        const w = lw * 0.84;
        const color = LANE_COLORS[tile.lane];
        const r = 10;
        ctx.fillStyle = color;
        ctx.shadowColor = color;
        ctx.shadowBlur = 14;
        roundRect(ctx, x, tile.y, w, this.tileHeight, r);
        ctx.fill();
        ctx.shadowBlur = 0;
      }

      // hit flashes
      for (const f of this.flashes) {
        const cx = f.lane * lw + lw / 2;
        const cy = zoneTop + (this.height - zoneTop) / 2;
        const radius = lw * 0.55 * (1 - f.life) + lw * 0.15;
        ctx.beginPath();
        ctx.fillStyle = hexToRgba(LANE_COLORS[f.lane], f.life * 0.5);
        ctx.arc(cx, cy, radius, 0, Math.PI * 2);
        ctx.fill();
      }
    }
  }

  function roundRect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }

  function hexToRgba(hex, alpha) {
    const bigint = parseInt(hex.slice(1), 16);
    const r = (bigint >> 16) & 255, g = (bigint >> 8) & 255, b = bigint & 255;
    return `rgba(${r},${g},${b},${alpha})`;
  }

  // ---------------------------------------------------------------------
  // UI controller
  // ---------------------------------------------------------------------
  const $ = (id) => document.getElementById(id);

  const els = {
    rotateHint: $('rotate-hint'),
    menu: $('screen-menu'),
    nameInput: $('player-name'),
    diffSelect: $('difficulty-select'),
    bestScoreLine: $('best-score-line'),
    btnStart: $('btn-start'),
    btnLeaderboard: $('btn-leaderboard'),
    btnMute: $('btn-mute'),
    countdown: $('countdown'),
    countdownNumber: $('countdown-number'),
    gameScreen: $('screen-game'),
    canvas: $('game-canvas'),
    hudScore: $('hud-score'),
    hudAiScore: $('hud-ai-score'),
    hudCombo: $('hud-combo'),
    raceFillYou: $('race-fill-you'),
    raceFillAi: $('race-fill-ai'),
    btnPause: $('btn-pause'),
    pauseScreen: $('screen-pause'),
    btnResume: $('btn-resume'),
    btnQuit: $('btn-quit'),
    gameOverScreen: $('screen-gameover'),
    resultTitle: $('result-title'),
    finalScore: $('final-score'),
    finalAiScore: $('final-ai-score'),
    newBest: $('new-best'),
    btnRetry: $('btn-retry'),
    btnGameoverMenu: $('btn-gameover-menu'),
    leaderboardScreen: $('screen-leaderboard'),
    leaderboardTabs: $('leaderboard-tabs'),
    leaderboardList: $('leaderboard-list'),
    btnLeaderboardClose: $('btn-leaderboard-close'),
  };

  const audio = new AudioEngine();
  const game = new Game(els.canvas, audio);

  let selectedDifficulty = Storage.getLastDifficulty();
  let lbDifficulty = selectedDifficulty;
  let muted = false;

  function setSelectedDifficulty(key) {
    selectedDifficulty = key;
    Storage.setLastDifficulty(key);
    [...els.diffSelect.children].forEach((btn) => {
      btn.classList.toggle('selected', btn.dataset.difficulty === key);
    });
    els.bestScoreLine.textContent = `Best: ${Storage.getBest(key)}`;
  }

  function setLbDifficulty(key) {
    lbDifficulty = key;
    [...els.leaderboardTabs.children].forEach((btn) => {
      btn.classList.toggle('selected', btn.dataset.difficulty === key);
    });
    renderLeaderboard();
  }

  function renderLeaderboard() {
    const list = Storage.loadScores()[lbDifficulty] || [];
    els.leaderboardList.innerHTML = '';
    if (!list.length) {
      const li = document.createElement('li');
      li.className = 'leaderboard-empty';
      li.textContent = 'No scores yet. Be the first!';
      li.style.justifyContent = 'center';
      els.leaderboardList.appendChild(li);
      return;
    }
    list.forEach((entry, i) => {
      const li = document.createElement('li');
      const resultClass = entry.result === 'win' ? 'win' : '';
      li.innerHTML = `
        <span class="rank">${i + 1}</span>
        <span class="lb-name">${escapeHtml(entry.name)}</span>
        <span class="lb-result ${resultClass}">${entry.result === 'win' ? 'WIN' : entry.result === 'draw' ? 'DRAW' : 'LOSS'}</span>
        <span class="lb-score">${entry.score}</span>
      `;
      els.leaderboardList.appendChild(li);
    });
  }

  function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  function checkRotate() {
    const isLandscapeSmall = window.matchMedia('(orientation: landscape) and (max-height: 500px)').matches;
    els.rotateHint.classList.toggle('active', isLandscapeSmall);
    els.rotateHint.classList.toggle('hidden', !isLandscapeSmall);
  }

  function runCountdown(cb) {
    els.countdown.classList.remove('hidden');
    let n = 3;
    els.countdownNumber.textContent = n;
    const timer = setInterval(() => {
      n--;
      if (n === 0) {
        els.countdownNumber.textContent = 'GO!';
      } else if (n < 0) {
        clearInterval(timer);
        els.countdown.classList.add('hidden');
        cb();
      } else {
        els.countdownNumber.textContent = n;
      }
    }, 550);
  }

  function showScreen(name) {
    ['menu', 'gameScreen'].forEach((k) => els[k].classList.add('hidden'));
    if (name === 'menu') els.menu.classList.remove('hidden');
    if (name === 'game') els.gameScreen.classList.remove('hidden');
  }

  els.diffSelect.addEventListener('click', (e) => {
    const btn = e.target.closest('.seg-btn');
    if (btn) setSelectedDifficulty(btn.dataset.difficulty);
  });

  els.leaderboardTabs.addEventListener('click', (e) => {
    const btn = e.target.closest('.seg-btn');
    if (btn) setLbDifficulty(btn.dataset.difficulty);
  });

  els.nameInput.addEventListener('change', () => {
    Storage.setName(els.nameInput.value.trim());
  });

  els.btnMute.addEventListener('click', () => {
    muted = !muted;
    audio.setMuted(muted);
    els.btnMute.textContent = muted ? '🔇' : '🔊';
  });

  els.btnStart.addEventListener('click', () => {
    audio.resume();
    const name = els.nameInput.value.trim() || 'Player';
    Storage.setName(name);
    showScreen('game');
    game.reset(selectedDifficulty);
    game.resizeCanvas();
    game.onScoreChange = (score, aiScore, combo) => {
      els.hudScore.textContent = score;
      els.hudAiScore.textContent = aiScore;
      els.hudCombo.textContent = combo >= 5 ? `🔥 x${combo}` : '';
      const max = Math.max(score, aiScore, 5);
      els.raceFillYou.style.width = `${(score / max) * 100}%`;
      els.raceFillAi.style.width = `${(aiScore / max) * 100}%`;
    };
    game.onGameOver = (score, aiScore, reason) => {
      const prevBest = Storage.getBest(selectedDifficulty);
      const result = score > aiScore ? 'win' : score < aiScore ? 'lose' : 'draw';
      Storage.saveEntry(selectedDifficulty, {
        name, score, aiScore, result, date: new Date().toISOString(),
      });
      els.resultTitle.textContent = result === 'win' ? '🏆 You Win!' : result === 'draw' ? '🤝 Draw' : '🤖 AI Wins';
      els.finalScore.textContent = score;
      els.finalAiScore.textContent = aiScore;
      els.newBest.classList.toggle('hidden', score <= prevBest);
      els.gameOverScreen.classList.remove('hidden');
    };
    els.hudScore.textContent = '0';
    els.hudAiScore.textContent = '0';
    els.hudCombo.textContent = '';
    els.raceFillYou.style.width = '0%';
    els.raceFillAi.style.width = '0%';
    runCountdown(() => {
      audio.startBackground(game.settings.tempo);
      game.start();
    });
  });

  els.btnLeaderboard.addEventListener('click', () => {
    setLbDifficulty(selectedDifficulty);
    els.leaderboardScreen.classList.remove('hidden');
  });
  els.btnLeaderboardClose.addEventListener('click', () => {
    els.leaderboardScreen.classList.add('hidden');
  });

  els.btnPause.addEventListener('click', () => {
    game.pause();
    els.pauseScreen.classList.remove('hidden');
  });
  els.btnResume.addEventListener('click', () => {
    els.pauseScreen.classList.add('hidden');
    game.resumeGame();
  });
  els.btnQuit.addEventListener('click', () => {
    els.pauseScreen.classList.add('hidden');
    game.state = 'idle';
    audio.stopBackground();
    setSelectedDifficulty(selectedDifficulty);
    showScreen('menu');
  });

  els.btnRetry.addEventListener('click', () => {
    els.gameOverScreen.classList.add('hidden');
    game.reset(selectedDifficulty);
    game.resizeCanvas();
    els.hudScore.textContent = '0';
    els.hudAiScore.textContent = '0';
    els.raceFillYou.style.width = '0%';
    els.raceFillAi.style.width = '0%';
    runCountdown(() => {
      audio.startBackground(game.settings.tempo);
      game.start();
    });
  });
  els.btnGameoverMenu.addEventListener('click', () => {
    els.gameOverScreen.classList.add('hidden');
    setSelectedDifficulty(selectedDifficulty);
    showScreen('menu');
  });

  document.addEventListener('visibilitychange', () => {
    if (document.hidden && game.state === 'playing') {
      game.pause();
      els.pauseScreen.classList.remove('hidden');
    }
  });

  window.addEventListener('resize', () => {
    checkRotate();
    if (!els.gameScreen.classList.contains('hidden')) game.resizeCanvas();
  });
  window.addEventListener('orientationchange', checkRotate);

  // init
  els.nameInput.value = Storage.getName();
  setSelectedDifficulty(selectedDifficulty);
  checkRotate();

  if ('serviceWorker' in navigator && location.protocol !== 'file:') {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('sw.js').catch(() => {});
    });
  }
})();
