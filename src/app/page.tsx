'use client'

import { useState, useRef, useCallback, useEffect } from 'react'
import { DEFAULT_CONFIG, validateConfig, type SimConfig, type SimState } from '@/lib/alife/config'
import { Simulation } from '@/lib/alife/simulation'
import { Agent } from '@/lib/alife/agent'
import { rayAngles } from '@/lib/alife/environment'

// ── Validate default config on module load ────────────────
validateConfig(DEFAULT_CONFIG)

// ── Canvas constants ───────────────────────────────────────
const WORLD_W = DEFAULT_CONFIG.world.width
const WORLD_H = DEFAULT_CONFIG.world.height

export default function Home() {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const simRef = useRef<Simulation | null>(null)
  const rafRef = useRef<number>(0)
  const wallZoneCanvasRef = useRef<HTMLCanvasElement | null>(null)

  const [state, setState] = useState<SimState | null>(null)
  const [started, setStarted] = useState(false)
  const [extinct, setExtinct] = useState(false)
  const [speed, setSpeed] = useState(1)
  const [selectedIdx, setSelectedIdx] = useState(-1)
  const [showRays, setShowRays] = useState(true)
  const [paused, setPaused] = useState(false)

  // ── Pre-render wall zone gradient (once) ─────────────────
  const buildWallZone = useCallback((ctx: CanvasRenderingContext2D) => {
    const offscreen = document.createElement('canvas')
    offscreen.width = WORLD_W
    offscreen.height = WORLD_H
    const oc = offscreen.getContext('2d')!
    const zw = DEFAULT_CONFIG.penalty_zone.width

    for (let i = 0; i < zw; i++) {
      const alpha = 0.15 * (1 - i / zw)
      oc.strokeStyle = `rgba(220, 50, 50, ${alpha})`
      oc.lineWidth = 1
      oc.strokeRect(i, i, WORLD_W - 2 * i, WORLD_H - 2 * i)
    }
    wallZoneCanvasRef.current = offscreen
  }, [])

  // ── Render one frame ─────────────────────────────────────
  const renderFrame = useCallback((sim: Simulation) => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    // Background
    ctx.fillStyle = '#12121a'
    ctx.fillRect(0, 0, WORLD_W, WORLD_H)

    // Wall zone gradient
    if (wallZoneCanvasRef.current) {
      ctx.drawImage(wallZoneCanvasRef.current, 0, 0)
    }

    // Grid
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.04)'
    ctx.lineWidth = 0.5
    const gridStep = 50
    for (let x = gridStep; x < WORLD_W; x += gridStep) {
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, WORLD_H); ctx.stroke()
    }
    for (let y = gridStep; y < WORLD_H; y += gridStep) {
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(WORLD_W, y); ctx.stroke()
    }

    // Penalty zone border
    const zw = DEFAULT_CONFIG.penalty_zone.width
    ctx.strokeStyle = 'rgba(220, 50, 50, 0.3)'
    ctx.lineWidth = 1
    ctx.setLineDash([4, 4])
    ctx.strokeRect(zw, zw, WORLD_W - 2 * zw, WORLD_H - 2 * zw)
    ctx.setLineDash([])

    // Apples
    const appleR = DEFAULT_CONFIG.apple.radius
    for (const apple of sim.env.apples) {
      ctx.beginPath()
      ctx.arc(apple.x, apple.y, appleR, 0, Math.PI * 2)
      ctx.fillStyle = '#e53e3e'
      ctx.fill()
      // Inner highlight
      ctx.beginPath()
      ctx.arc(apple.x - appleR * 0.2, apple.y - appleR * 0.2, appleR * 0.4, 0, Math.PI * 2)
      ctx.fillStyle = 'rgba(255, 150, 150, 0.5)'
      ctx.fill()
    }

    // Find best agent (most apples eaten via record tracking)
    let bestIdx = -1
    let bestEnergy = -1
    for (let i = 0; i < sim.population.length; i++) {
      if (sim.population[i].energy > bestEnergy) {
        bestEnergy = sim.population[i].energy
        bestIdx = i
      }
    }

    // Agents
    const agentR = DEFAULT_CONFIG.agent.radius
    const selIdx = selectedIdx >= 0 && selectedIdx < sim.population.length ? selectedIdx : -1

    for (let i = 0; i < sim.population.length; i++) {
      const agent = sim.population[i]
      const isBest = i === bestIdx
      const isSelected = i === selIdx
      const isDying = agent.isDying()

      if (isSelected || isBest) {
        // Full opacity, rays, outline
        const energyNorm = agent.energy / DEFAULT_CONFIG.agent.max_energy
        const r = Math.round(255 * (1 - energyNorm))
        const g = Math.round(255 * energyNorm)
        const b = 50

        // Raycasts
        if (showRays && agent.lastSenses) {
          const numRays = DEFAULT_CONFIG.sensors.num_rays
          const rayRange = agent.effectiveRayRange
          const angles = rayAngles(numRays, DEFAULT_CONFIG.sensors.fov, agent.heading)

          for (let ri = 0; ri < numRays; ri++) {
            const angle = angles[ri]
            const dist = agent.lastSenses[ri] * rayRange
            const isApple = agent.lastSenses[numRays + ri] > 0.5
            const isWall = agent.lastSenses[numRays * 2 + ri] > 0.5

            ctx.beginPath()
            ctx.moveTo(agent.x, agent.y)
            ctx.lineTo(agent.x + Math.cos(angle) * dist, agent.y + Math.sin(angle) * dist)

            if (isApple) ctx.strokeStyle = 'rgba(255, 160, 50, 0.6)'
            else if (isWall) ctx.strokeStyle = 'rgba(100, 200, 255, 0.5)'
            else ctx.strokeStyle = 'rgba(100, 255, 100, 0.15)'

            ctx.lineWidth = isSelected ? 1 : 0.8
            ctx.stroke()
          }
        }

        // Agent body
        ctx.beginPath()
        ctx.arc(agent.x, agent.y, agentR, 0, Math.PI * 2)
        ctx.fillStyle = isDying ? `rgba(200, 80, 50, 0.9)` : `rgb(${r}, ${g}, ${b})`
        ctx.fill()

        // Outline
        ctx.strokeStyle = isSelected ? '#ffffff' : '#4ade80'
        ctx.lineWidth = 2
        ctx.stroke()

        // Heading indicator
        const hLen = agentR * 2
        ctx.beginPath()
        ctx.moveTo(agent.x, agent.y)
        ctx.lineTo(
          agent.x + Math.cos(agent.heading) * hLen,
          agent.y + Math.sin(agent.heading) * hLen,
        )
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.7)'
        ctx.lineWidth = 1.5
        ctx.stroke()

      } else {
        // Other agents: semi-transparent
        const alpha = isDying ? 0.25 : 0.35
        const energyNorm = agent.energy / DEFAULT_CONFIG.agent.max_energy
        const r = Math.round(255 * (1 - energyNorm))
        const g = Math.round(255 * energyNorm)

        ctx.beginPath()
        ctx.arc(agent.x, agent.y, agentR, 0, Math.PI * 2)
        ctx.fillStyle = `rgba(${r}, ${g}, 50, ${alpha})`
        ctx.fill()
      }
    }

    // HUD
    const s = state
    if (!s) return

    // Top bar background
    ctx.fillStyle = 'rgba(0, 0, 0, 0.6)'
    ctx.fillRect(0, 0, WORLD_W, 36)

    ctx.font = '13px "Geist Mono", monospace'
    ctx.textBaseline = 'middle'

    // Speed controls info
    const speedText = paused ? '⏸ PAUSED' : `${speed}x`
    ctx.fillStyle = '#e2e8f0'
    ctx.fillText(`Speed: ${speedText}`, 12, 18)

    // Stats
    ctx.fillStyle = '#94a3b8'
    const statsX = 160
    ctx.fillText(`Tick: ${s.tick}`, statsX, 18)
    ctx.fillText(`Pop: ${s.population}/${DEFAULT_CONFIG.population.max_size}`, statsX + 120, 18)
    ctx.fillText(`Food: ${s.foodAvailable}`, statsX + 260, 18)
    ctx.fillText(`Record: ${s.recordApples}`, statsX + 360, 18)
    ctx.fillText(`Gen: ${s.meanGeneration.toFixed(1)}`, statsX + 470, 18)
    ctx.fillText(`Species: ${s.speciesCount}`, statsX + 580, 18)
    ctx.fillText(`Forage: ${s.meanForageRate.toFixed(3)}`, statsX + 680, 18)
    ctx.fillText(`Repro: ${s.totalReproductions}`, statsX + 820, 18)

    // Reproduction mode indicator
    ctx.fillStyle = DEFAULT_CONFIG.agent.apples_per_offspring > 0 ? '#4ade80' : '#facc15'
    const mode = DEFAULT_CONFIG.agent.apples_per_offspring > 0 ? 'STRUCTURAL' : 'LEGACY'
    ctx.fillText(`Repro: ${mode}`, statsX + 950, 18)

  }, [selectedIdx, showRays, state])

  // ── Game loop (ref-based to avoid self-reference in useCallback) ──
  const gameLoopRef = useRef<() => void>(() => {})
  gameLoopRef.current = () => {
    const sim = simRef.current
    if (!sim || paused) {
      rafRef.current = requestAnimationFrame(gameLoopRef.current)
      return
    }

    for (let i = 0; i < speed; i++) {
      sim.tick()
      if (sim.isExtinct) {
        setExtinct(true)
        break
      }
    }

    const s = sim.getState()
    setState(s)
    renderFrame(sim)

    rafRef.current = requestAnimationFrame(gameLoopRef.current)
  }

  // ── Start / Reset ────────────────────────────────────────
  const handleStart = useCallback(() => {
    TRACKER_RESET()
    const sim = new Simulation(DEFAULT_CONFIG)
    simRef.current = sim
    setExtinct(false)
    setSelectedIdx(-1)
    setStarted(true)
    setPaused(false)

    // Build wall zone on first start
    const canvas = canvasRef.current
    if (canvas) {
      const ctx = canvas.getContext('2d')
      if (ctx) buildWallZone(ctx)
    }

    // Initial render
    setState(sim.getState())
    renderFrame(sim)

    // Start loop
    if (rafRef.current) cancelAnimationFrame(rafRef.current)
    rafRef.current = requestAnimationFrame(gameLoopRef.current)
  }, [buildWallZone, renderFrame])

  // ── Canvas click: select agent ──────────────────────────
  const handleCanvasClick = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const sim = simRef.current
    if (!sim) return
    const canvas = canvasRef.current
    if (!canvas) return

    const rect = canvas.getBoundingClientRect()
    const scaleX = WORLD_W / rect.width
    const scaleY = WORLD_H / rect.height
    const mx = (e.clientX - rect.left) * scaleX
    const my = (e.clientY - rect.top) * scaleY

    let closestIdx = -1
    let closestDist = DEFAULT_CONFIG.agent.radius * 3
    for (let i = 0; i < sim.population.length; i++) {
      const a = sim.population[i]
      const d = Math.sqrt((a.x - mx) ** 2 + (a.y - my) ** 2)
      if (d < closestDist) {
        closestDist = d
        closestIdx = i
      }
    }
    setSelectedIdx(closestIdx)
  }, [])

  // ── Keyboard controls ────────────────────────────────────
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === ' ' || e.code === 'Space') {
        e.preventDefault()
        setPaused(p => !p)
      } else if (e.key === '+' || e.key === '=') {
        setSpeed(s => Math.min(s * 2, 64))
      } else if (e.key === '-' || e.key === '_') {
        setSpeed(s => Math.max(s / 2, 1))
      } else if (e.key === 'r' || e.key === 'R') {
        handleStart()
      }
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [handleStart])

  // ── Cleanup ──────────────────────────────────────────────
  useEffect(() => {
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
    }
  }, [])

  // ── Download CSV ─────────────────────────────────────────
  const handleDownloadCSV = useCallback(() => {
    const sim = simRef.current
    if (!sim) return
    const blob = new Blob([sim.getCsvContent()], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `alife_metrics_${Date.now()}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }, [])

  // ── Selected agent details ───────────────────────────────
  const selectedAgent = selectedIdx >= 0 && simRef.current
    ? simRef.current.population[selectedIdx] ?? null
    : null

  return (
    <div className="min-h-screen bg-[#0a0a12] text-white flex flex-col">
      {/* Canvas area */}
      <div className="flex-1 flex items-center justify-center p-2 sm:p-4">
        <div className="relative w-full max-w-[1200px]">
          {/* Canvas */}
          <canvas
            ref={canvasRef}
            width={WORLD_W}
            height={WORLD_H}
            onClick={handleCanvasClick}
            className="w-full h-auto rounded-lg border border-white/10 cursor-crosshair"
            style={{ aspectRatio: `${WORLD_W}/${WORLD_H}` }}
          />

          {/* Overlay: not started */}
          {!started && (
            <div className="absolute inset-0 flex items-center justify-center bg-black/70 rounded-lg">
              <div className="text-center space-y-6">
                <h1 className="text-3xl sm:text-4xl font-bold tracking-tight">
                  <span className="text-emerald-400">ALife</span>{' '}
                  <span className="text-white/60">Neuroevolution</span>
                </h1>
                <p className="text-white/40 max-w-md mx-auto text-sm sm:text-base">
                  Agents with evolvable neural networks forage for food to survive and reproduce.
                  Vision range is an evolvable trait with phenotypic plasticity.
                </p>
                <div className="flex flex-wrap items-center justify-center gap-3 text-xs text-white/30">
                  <span className="px-2 py-1 rounded bg-white/5">Structural Reproduction</span>
                  <span className="px-2 py-1 rounded bg-white/5">Evolvable Vision</span>
                  <span className="px-2 py-1 rounded bg-white/5">Anti-Spinning Noise</span>
                  <span className="px-2 py-1 rounded bg-white/5">Connection Toggle</span>
                </div>
                <button
                  onClick={handleStart}
                  className="px-8 py-3 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg font-medium transition-colors text-lg"
                >
                  Start Simulation
                </button>
                <p className="text-white/20 text-xs">Seed: {DEFAULT_CONFIG.simulation.seed} · Pop: {DEFAULT_CONFIG.population.initial_size} · World: {WORLD_W}×{WORLD_H}</p>
              </div>
            </div>
          )}

          {/* Overlay: extinct */}
          {extinct && (
            <div className="absolute inset-0 flex items-center justify-center bg-black/70 rounded-lg">
              <div className="text-center space-y-4">
                <h2 className="text-2xl font-bold text-red-400">Extinction</h2>
                <p className="text-white/50">
                  Population died out at tick {state?.tick ?? '?'}.
                  Record: {state?.recordApples ?? 0} apples.
                </p>
                <button
                  onClick={handleStart}
                  className="px-6 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg font-medium transition-colors"
                >
                  Restart
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Controls bar */}
      {started && (
        <div className="border-t border-white/10 bg-black/40 px-4 py-2">
          <div className="max-w-[1200px] mx-auto flex flex-wrap items-center gap-2 sm:gap-3">
            {/* Speed controls */}
            <div className="flex items-center gap-1">
              <button
                onClick={() => setPaused(p => !p)}
                className="px-3 py-1.5 bg-white/10 hover:bg-white/20 rounded text-sm font-mono transition-colors"
              >
                {paused ? '▶' : '⏸'}
              </button>
              <button
                onClick={() => setSpeed(s => Math.max(s / 2, 1))}
                className="px-2 py-1.5 bg-white/10 hover:bg-white/20 rounded text-sm font-mono transition-colors"
                disabled={speed <= 1}
              >
                -
              </button>
              <span className="px-2 py-1.5 text-sm font-mono text-white/60 min-w-[40px] text-center">
                {speed}x
              </span>
              <button
                onClick={() => setSpeed(s => Math.min(s * 2, 64))}
                className="px-2 py-1.5 bg-white/10 hover:bg-white/20 rounded text-sm font-mono transition-colors"
                disabled={speed >= 64}
              >
                +
              </button>
            </div>

            <div className="h-5 w-px bg-white/10" />

            {/* Toggles */}
            <button
              onClick={() => setShowRays(r => !r)}
              className={`px-3 py-1.5 rounded text-sm transition-colors ${showRays ? 'bg-emerald-600/30 text-emerald-400' : 'bg-white/10 text-white/40'}`}
            >
              Rays
            </button>

            <button
              onClick={handleDownloadCSV}
              className="px-3 py-1.5 bg-white/10 hover:bg-white/20 rounded text-sm transition-colors"
            >
              CSV
            </button>

            <button
              onClick={handleStart}
              className="px-3 py-1.5 bg-white/10 hover:bg-white/20 rounded text-sm transition-colors"
            >
              Reset
            </button>

            <div className="h-5 w-px bg-white/10" />

            {/* Selected agent info */}
            {selectedAgent && (
              <div className="text-xs font-mono text-white/50 flex flex-wrap gap-x-4 gap-y-1">
                <span>Age: <span className="text-white/80">{selectedAgent.age}</span></span>
                <span>Energy: <span className="text-white/80">{selectedAgent.energy.toFixed(3)}</span></span>
                <span>Gen: <span className="text-white/80">{selectedAgent.generation}</span></span>
                <span>Ray: <span className="text-white/80">{selectedAgent.effectiveRayRange.toFixed(0)}</span></span>
                <span>Nodes: <span className="text-white/80">{selectedAgent.genome.nodes.length}</span></span>
                <span>Conns: <span className="text-white/80">{selectedAgent.genome.enabledConnections.length}</span></span>
              </div>
            )}

            {/* Help hint */}
            <div className="ml-auto text-xs text-white/20 hidden sm:block">
              Space: pause · +/-: speed · Click: select agent · R: reset
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// Need to import TRACKER for reset on restart
import { TRACKER as _TRACKER } from '@/lib/alife/genome'

function TRACKER_RESET() {
  _TRACKER.reset()
}