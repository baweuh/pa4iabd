'use client';

import { useRef, useEffect, useState, useCallback } from 'react';
import { Simulation } from '@/lib/alife/simulation';
import { DEFAULT_CONFIG } from '@/lib/alife/config';
import type { SimState } from '@/lib/alife/simulation';

// ── Color palette (matching Pygame renderer) ──
const C = {
  bg: '#0f0f14',
  grid: '#191920',
  agent: '#ffdc32',
  agentDying: '#ff6432',
  agentBest: '#64ff64',
  agentBestDying: '#64b43c',
  food: '#dc3232',
  foodInner: '#ff7878',
  rayFood: 'rgba(255,100,100,0.6)',
  rayWall: 'rgba(100,130,255,0.5)',
  rayNone: 'rgba(40,55,40,0.3)',
  hudBg: '#14141c',
  hudFg: '#c8c8c8',
  hudHl: '#ffdc32',
  hudGreen: '#64ff64',
  hudMuted: '#8c8ca0',
};

export default function ALifePage() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const simRef = useRef<Simulation | null>(null);
  const rafRef = useRef<number>(0);
  const [state, setState] = useState<SimState | null>(null);
  const [started, setStarted] = useState(false);
  const [extinct, setExtinct] = useState(false);

  // Pre-rendered wall zone gradient
  const wallZoneCanvas = useRef<HTMLCanvasElement | null>(null);

  const buildWallZone = useCallback((w: number, h: number, zoneW: number) => {
    const offscreen = document.createElement('canvas');
    offscreen.width = w;
    offscreen.height = h;
    const ctx = offscreen.getContext('2d')!;
    const zw = Math.floor(zoneW);

    // Top & Bottom
    for (let i = 0; i < zw; i++) {
      const alpha = 0.15 * (1.0 - i / zw);
      ctx.fillStyle = `rgba(200,40,40,${alpha})`;
      ctx.fillRect(0, i, w, 1);
      ctx.fillRect(0, h - 1 - i, w, 1);
    }
    // Left & Right
    for (let i = 0; i < zw; i++) {
      const alpha = 0.15 * (1.0 - i / zw);
      ctx.fillStyle = `rgba(200,40,40,${alpha})`;
      ctx.fillRect(i, 0, 1, h);
      ctx.fillRect(w - 1 - i, 0, 1, h);
    }

    wallZoneCanvas.current = offscreen;
  }, []);

  const startSim = useCallback((seed?: number) => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    const sim = new Simulation(DEFAULT_CONFIG, seed);
    simRef.current = sim;
    setExtinct(false);
    setStarted(true);

    buildWallZone(DEFAULT_CONFIG.environment.env_width, DEFAULT_CONFIG.environment.env_height, DEFAULT_CONFIG.environment.zone_width);

    let lastTime = 0;
    const targetFPS = DEFAULT_CONFIG.simulation.render_fps;
    const frameInterval = 1000 / targetFPS;

    const loop = (time: number) => {
      if (!sim.running) {
        setExtinct(true);
        setState(sim.getState());
        return;
      }

      if (time - lastTime >= frameInterval) {
        if (!sim.paused) {
          for (let i = 0; i < sim.ticksPerFrame; i++) {
            if (!sim.step()) break;
          }
        }
        setState(sim.getState());
        renderFrame(sim);
        lastTime = time;
      }

      rafRef.current = requestAnimationFrame(loop);
    };

    rafRef.current = requestAnimationFrame(loop);
  }, [buildWallZone]);

  const renderFrame = useCallback((sim: Simulation) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const envW = sim.cfg.environment.env_width;
    const envH = sim.cfg.environment.env_height;
    const agentRadius = sim.cfg.agents.agent_radius;
    const foodRadius = sim.cfg.agents.food_radius;

    // Clear
    ctx.fillStyle = C.bg;
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    // Wall zone gradient
    if (wallZoneCanvas.current) {
      ctx.drawImage(wallZoneCanvas.current, 0, 0);
    }

    // Grid
    ctx.strokeStyle = C.grid;
    ctx.lineWidth = 0.5;
    for (let x = 0; x < envW; x += 50) {
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, envH); ctx.stroke();
    }
    for (let y = 0; y < envH; y += 50) {
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(envW, y); ctx.stroke();
    }

    // Apples
    for (const apple of sim.env.apples) {
      if (apple.respawn_at_tick >= 0) continue;
      ctx.fillStyle = C.food;
      ctx.beginPath();
      ctx.arc(apple.x, apple.y, foodRadius, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = C.foodInner;
      ctx.beginPath();
      ctx.arc(apple.x, apple.y, Math.max(2, foodRadius - 3), 0, Math.PI * 2);
      ctx.fill();
    }

    // Best agent (full opacity + rays)
    const best = sim.bestAgent;
    if (best && best.alive) {
      // Rays
      for (const ray of best.rays) {
        ctx.strokeStyle = ray.kind === 0.5 ? C.rayFood : ray.kind === 1.0 ? C.rayWall : C.rayNone;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(best.x, best.y);
        ctx.lineTo(ray.x, ray.y);
        ctx.stroke();
      }

      // Body
      const isDying = best.isDying();
      ctx.fillStyle = isDying ? C.agentBestDying : C.agentBest;
      ctx.beginPath();
      ctx.arc(best.x, best.y, agentRadius, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 2;
      ctx.stroke();

      // Direction indicator
      const speed = Math.sqrt(best.vx ** 2 + best.vy ** 2);
      if (speed > 0.1) {
        const dx = best.vx / speed;
        const dy = best.vy / speed;
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(best.x, best.y);
        ctx.lineTo(best.x + dx * (agentRadius + 7), best.y + dy * (agentRadius + 7));
        ctx.stroke();
      }
    }

    // Other agents (semi-transparent, no rays)
    ctx.globalAlpha = 0.35;
    for (const agent of sim.agents) {
      if (!agent.alive || agent === best) continue;
      ctx.fillStyle = agent.isDying() ? C.agentDying : C.agent;
      ctx.beginPath();
      ctx.arc(agent.x, agent.y, agentRadius, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  }, []);

  // Keyboard controls
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      const sim = simRef.current;
      if (!sim) return;
      if (e.code === 'Space') {
        e.preventDefault();
        sim.paused = !sim.paused;
        setState(sim.getState());
      } else if (e.code === 'ArrowUp') {
        e.preventDefault();
        sim.ticksPerFrame = Math.min(sim.ticksPerFrame * 2, 64);
        setState(sim.getState());
      } else if (e.code === 'ArrowDown') {
        e.preventDefault();
        sim.ticksPerFrame = Math.max(sim.ticksPerFrame / 2, 1);
        setState(sim.getState());
      }
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, []);

  // Cleanup
  useEffect(() => {
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, []);

  const envW = DEFAULT_CONFIG.environment.env_width;
  const envH = DEFAULT_CONFIG.environment.env_height;

  if (!started) {
    return (
      <div className="min-h-screen bg-[#0f0f14] flex flex-col items-center justify-center text-white">
        <div className="text-center max-w-md px-6">
          <div className="text-5xl mb-4">🧬</div>
          <h1 className="text-2xl font-bold mb-2">ALife</h1>
          <p className="text-sm text-[#888] mb-8">Neuroévolution Continue — Simulation de vie artificielle avec algorithme NEAT</p>
          <button
            onClick={() => startSim()}
            className="px-8 py-3 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg font-semibold transition-colors text-sm cursor-pointer"
          >
            Lancer une nouvelle expérience
          </button>
          <p className="text-xs text-[#555] mt-6">
            40 agents · 16 raycasts 360° · Réseaux neuronaux évolutifs · Sélection naturelle
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#0f0f14] flex flex-col items-center justify-center text-white select-none">
      {/* Header */}
      <header className="w-full border-b border-white/[0.06] px-4 py-3 flex items-center gap-3 bg-[#0f0f14]/90 backdrop-blur-sm">
        <div className="w-8 h-8 rounded-lg bg-emerald-500/10 flex items-center justify-center text-lg">🧬</div>
        <div>
          <h1 className="text-sm font-bold leading-tight">ALife</h1>
          <p className="text-[10px] text-[#666]">Neuroévolution Continue</p>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full ${extinct ? 'bg-red-500' : state?.paused ? 'bg-yellow-500 animate-pulse' : 'bg-emerald-500'}`} />
          <span className="text-xs text-[#888]">
            {extinct ? 'Extinction' : state?.paused ? 'En pause' : 'Active'}
          </span>
          {state && (
            <span className="ml-2 px-2 py-0.5 bg-emerald-500/10 border border-emerald-500/25 rounded text-[10px] text-emerald-400 font-mono">
              seed: {state.seed}
            </span>
          )}
        </div>
      </header>

      {/* Main content */}
      <main className="flex flex-col lg:flex-row gap-4 p-4 items-start justify-center">
        {/* Canvas */}
        <div className="relative">
          <canvas
            ref={canvasRef}
            width={envW}
            height={envH}
            className="rounded-lg border border-white/[0.08] max-w-[95vw] max-h-[75vh]"
            style={{ width: envW, height: envH, maxWidth: '95vw', maxHeight: '75vh', objectFit: 'contain' }}
          />

          {extinct && (
            <div className="absolute inset-0 flex items-center justify-center rounded-lg bg-black/70">
              <div className="text-center">
                <p className="text-red-400 text-lg font-bold mb-2">Extinction</p>
                <p className="text-sm text-[#999] mb-4">
                  Population éteinte au tick {state?.currentTick?.toLocaleString()}
                </p>
                <button
                  onClick={() => startSim()}
                  className="px-6 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg font-semibold transition-colors text-sm cursor-pointer"
                >
                  Nouvelle expérience
                </button>
              </div>
            </div>
          )}
        </div>

        {/* HUD Panel */}
        <div className="w-full lg:w-60 bg-[#14141c] rounded-lg border border-white/[0.08] p-4 text-xs space-y-3">
          <h2 className="text-sm font-bold text-[#ffdc32]">Simulation</h2>

          <div className="space-y-1.5 text-[#c8c8c8]">
            <div className="flex justify-between">
              <span>Tick</span>
              <span className="font-mono">{state?.currentTick?.toLocaleString()}</span>
            </div>
            <div className="flex justify-between">
              <span>Population</span>
              <span className="font-mono">{state?.population}</span>
            </div>
            <div className="flex justify-between">
              <span>Food</span>
              <span className="font-mono">{state?.foodAvailable}/{DEFAULT_CONFIG.environment.food_count}</span>
            </div>
            <div className="flex justify-between">
              <span>Record pommes</span>
              <span className="font-mono text-[#ffdc32]">{state?.recordApples}</span>
            </div>
            <div className="flex justify-between">
              <span>Reproductions</span>
              <span className="font-mono">{state?.totalReproductions?.toLocaleString()}</span>
            </div>
            <div className="flex justify-between">
              <span>Générations</span>
              <span className="font-mono">{state?.generation?.toLocaleString()}</span>
            </div>
            <div className="flex justify-between">
              <span>Espèces</span>
              <span className="font-mono">{state?.numSpecies}</span>
            </div>
            <div className="flex justify-between">
              <span>Vitesse</span>
              <span className="font-mono">{state?.ticksPerFrame}x</span>
            </div>
            <div className="flex justify-between">
              <span>Avg énergie</span>
              <span className="font-mono">{state?.avgEnergy}</span>
            </div>
            <div className="flex justify-between">
              <span>Avg net size</span>
              <span className="font-mono">{state?.avgNetSize}</span>
            </div>
          </div>

          {state && state.bestAgentFood > 0 && (
            <>
              <div className="border-t border-white/[0.06] pt-3">
                <h2 className="text-sm font-bold text-[#64ff64] mb-2">Meilleur Agent</h2>
                <div className="space-y-1.5 text-[#64ff64]">
                  <div className="flex justify-between">
                    <span>Pommes</span>
                    <span className="font-mono">{state.bestAgentFood}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Énergie</span>
                    <span className="font-mono">{state.bestAgentEnergy}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Âge</span>
                    <span className="font-mono">{state.bestAgentAge}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Enfants</span>
                    <span className="font-mono">{state.bestAgentChildren}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Taille réseau</span>
                    <span className="font-mono">{state.bestAgentNetSize}</span>
                  </div>
                </div>
              </div>
            </>
          )}

          {/* Controls */}
          <div className="border-t border-white/[0.06] pt-3">
            <h2 className="text-sm font-bold text-[#ffdc32] mb-2">Contrôles</h2>
            <div className="grid grid-cols-2 gap-2">
              <button
                onClick={() => { if (simRef.current) { simRef.current.paused = !simRef.current.paused; setState(simRef.current.getState()); } }}
                className="px-2 py-1.5 bg-white/[0.06] border border-white/[0.1] rounded text-[10px] text-[#ccc] hover:bg-emerald-500/15 hover:border-emerald-500/30 hover:text-emerald-400 transition-colors cursor-pointer"
              >
                {state?.paused ? '▶ Reprendre' : '⏸ Pause'}
              </button>
              <button
                onClick={() => { if (simRef.current) { simRef.current.ticksPerFrame = Math.min(simRef.current.ticksPerFrame * 2, 64); setState(simRef.current.getState()); } }}
                className="px-2 py-1.5 bg-white/[0.06] border border-white/[0.1] rounded text-[10px] text-[#ccc] hover:bg-emerald-500/15 hover:border-emerald-500/30 hover:text-emerald-400 transition-colors cursor-pointer"
              >
                ↑ Accélérer
              </button>
              <button
                onClick={() => { if (simRef.current) { simRef.current.ticksPerFrame = Math.max(simRef.current.ticksPerFrame / 2, 1); setState(simRef.current.getState()); } }}
                className="px-2 py-1.5 bg-white/[0.06] border border-white/[0.1] rounded text-[10px] text-[#ccc] hover:bg-emerald-500/15 hover:border-emerald-500/30 hover:text-emerald-400 transition-colors cursor-pointer"
              >
                ↓ Ralentir
              </button>
              <button
                onClick={() => startSim()}
                className="px-2 py-1.5 bg-white/[0.06] border border-white/[0.1] rounded text-[10px] text-[#ccc] hover:bg-emerald-500/15 hover:border-emerald-500/30 hover:text-emerald-400 transition-colors cursor-pointer"
              >
                ↻ Nouveau run
              </button>
            </div>
            <p className="text-[9px] text-[#555] mt-2">
              Clavier : ESPACE (pause) · ↑↓ (vitesse)
            </p>
          </div>
        </div>
      </main>
    </div>
  );
}