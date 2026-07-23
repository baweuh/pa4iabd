'use client'

import { useState, useRef, useCallback, useEffect } from 'react'
import { DEFAULT_CONFIG, validateConfig } from '@/lib/alife/config'
import type { SimState } from '@/lib/alife/simulation'
import { Simulation } from '@/lib/alife/simulation'
import { TRACKER } from '@/lib/alife/genome'
import { rayAngles } from '@/lib/alife/environment'

// ── Validate default config on module load ────────────────
validateConfig(DEFAULT_CONFIG)

// ── Canvas constants ───────────────────────────────────────
const WORLD_W = DEFAULT_CONFIG.world.width
const WORLD_H = DEFAULT_CONFIG.world.height

// ── Throttle interval for React state updates (ms) ─────────
const HUD_UPDATE_INTERVAL = 50 // ~20fps for React state, canvas always 60fps

export default function Home() {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const simRef = useRef<Simulation | null>(null)
  const rafRef = useRef<number>(0)
  const wallZoneRef = useRef<HTMLCanvasElement | null>(null)

  // All mutable loop state as refs — NEVER as useEffect deps
  const speedRef = useRef(1)
  const pausedRef = useRef(false)
  const selectedIdxRef = useRef(-1)
  const showRaysRef = useRef(true)
  const lastHudUpdateRef = useRef(0)

  // React state — only for UI chrome (updated at throttled rate)
  const [state, setState] = useState<SimState | null>(null)
  const [started, setStarted] = useState(false)
  const [extinct, setExtinct] = useState(false)
  const [speed, setSpeed] = useState(1)
  const [selectedIdx, setSelectedIdx] = useState(-1)
  const [showRays, setShowRays] = useState(true)
  const [paused, setPaused] = useState(false)
  const [selectedInfo, setSelectedInfo] = useState<Record<string, string | number> | null>(null)

  // Keep refs in sync with state (no re-renders for loop vars)
  const speedDisplay = useRef(speed)
  speedDisplay.current = speed

  // ── Build wall zone offscreen canvas ──────────────────────
  const buildWallZone = useCallback(() => {
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
    wallZoneRef.current = offscreen
  }, [])

  // ── Render one frame (pure function of sim + UI state) ───
  const renderFrame = useCallback((sim: Simulation, currentState: SimState | null, currentPaused: boolean, currentSpeed: number, currentSelectedIdx: number, currentShowRays: boolean) => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    // Background
    ctx.fillStyle = '#12121a'
    ctx.fillRect(0, 0, WORLD_W, WORLD_H)

    // Wall zone gradient
    if (wallZoneRef.current) ctx.drawImage(wallZoneRef.current, 0, 0)

    // Grid
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.04)'
    ctx.lineWidth = 0.5
    for (let x = 50; x < WORLD_W; x += 50) {
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, WORLD_H); ctx.stroke()
    }
    for (let y = 50; y < WORLD_H; y += 50) {
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
      ctx.beginPath()
      ctx.arc(apple.x - appleR * 0.2, apple.y - appleR * 0.2, appleR * 0.4, 0, Math.PI * 2)
      ctx.fillStyle = 'rgba(255, 150, 150, 0.5)'
      ctx.fill()
    }

    // Find best agent (highest energy)
    let bestIdx = -1
    let bestEnergy = -1
    for (let i = 0; i < sim.population.length; i++) {
      if (sim.population[i].energy > bestEnergy) {
        bestEnergy = sim.population[i].energy
        bestIdx = i
      }
    }

    const agentR = DEFAULT_CONFIG.agent.radius
    const selIdx = currentSelectedIdx >= 0 && currentSelectedIdx < sim.population.length ? currentSelectedIdx : -1

    // Draw agents
    for (let i = 0; i < sim.population.length; i++) {
      const agent = sim.population[i]
      const isBest = i === bestIdx
      const isSelected = i === selIdx
      const isDying = agent.isDying()

      if (isSelected || isBest) {
        const energyNorm = agent.energy / DEFAULT_CONFIG.agent.max_energy
        const cr = Math.round(255 * (1 - energyNorm))
        const cg = Math.round(255 * energyNorm)

        // Raycasts
        if (currentShowRays && agent.lastSenses) {
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

        // Body
        ctx.beginPath()
        ctx.arc(agent.x, agent.y, agentR, 0, Math.PI * 2)
        ctx.fillStyle = isDying ? 'rgba(200, 80, 50, 0.9)' : `rgb(${cr}, ${cg}, 50)`
        ctx.fill()
        ctx.strokeStyle = isSelected ? '#ffffff' : '#4ade80'
        ctx.lineWidth = 2
        ctx.stroke()

        // Heading arrow
        const hLen = agentR * 2
        ctx.beginPath()
        ctx.moveTo(agent.x, agent.y)
        ctx.lineTo(agent.x + Math.cos(agent.heading) * hLen, agent.y + Math.sin(agent.heading) * hLen)
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.7)'
        ctx.lineWidth = 1.5
        ctx.stroke()
      } else {
        const alpha = isDying ? 0.25 : 0.35
        const energyNorm = agent.energy / DEFAULT_CONFIG.agent.max_energy
        const cr = Math.round(255 * (1 - energyNorm))
        const cg = Math.round(255 * energyNorm)
        ctx.beginPath()
        ctx.arc(agent.x, agent.y, agentR, 0, Math.PI * 2)
        ctx.fillStyle = `rgba(${cr}, ${cg}, 50, ${alpha})`
        ctx.fill()
      }
    }

    // HUD top bar
    const s = currentState
    if (!s) return
    ctx.fillStyle = 'rgba(0, 0, 0, 0.6)'
    ctx.fillRect(0, 0, WORLD_W, 36)
    ctx.font = '13px "Geist Mono", monospace'
    ctx.textBaseline = 'middle'
    const speedText = currentPaused ? 'PAUSED' : `${currentSpeed}x`
    ctx.fillStyle = '#e2e8f0'
    ctx.fillText(`Speed: ${speedText}`, 12, 18)
    ctx.fillStyle = '#94a3b8'
    const sx = 160
    ctx.fillText(`Tick: ${s.tick}`, sx, 18)
    ctx.fillText(`Pop: ${s.population}/${DEFAULT_CONFIG.population.max_size}`, sx + 120, 18)
    ctx.fillText(`Food: ${s.foodAvailable}`, sx + 260, 18)
    ctx.fillText(`Record: ${s.recordApples}`, sx + 360, 18)
    ctx.fillText(`Gen: ${s.meanGeneration.toFixed(1)}`, sx + 470, 18)
    ctx.fillText(`Species: ${s.speciesCount}`, sx + 580, 18)
    ctx.fillText(`Forage: ${s.meanForageRate.toFixed(3)}`, sx + 680, 18)
    ctx.fillText(`Repro: ${s.totalReproductions}`, sx + 820, 18)
    ctx.fillStyle = DEFAULT_CONFIG.agent.apples_per_offspring > 0 ? '#4ade80' : '#facc15'
    ctx.fillText(`Repro: ${DEFAULT_CONFIG.agent.apples_per_offspring > 0 ? 'STRUCTURAL' : 'LEGACY'}`, sx + 950, 18)
  }, [])

  // ── Game loop — refs-only deps, never restarts on state change ──
  useEffect(() => {
    if (!started) return

    let running = true

    const loop = () => {
      if (!running) return
      const sim = simRef.current
      if (!sim) return

      // Read all mutable state from refs (zero deps = zero restarts)
      const spd = speedRef.current
      const isPaused = pausedRef.current

      if (!isPaused) {
        for (let i = 0; i < spd; i++) {
          sim.tick()
          if (sim.isExtinct) {
            setExtinct(true)
            break
          }
        }
      }

      // Canvas rendering: always 60fps, reads from refs
      renderFrame(sim, state, isPaused, spd, selectedIdxRef.current, showRaysRef.current)

      // Throttled React state update (~20fps) — avoids GC + re-render overhead
      const now = performance.now()
      if (now - lastHudUpdateRef.current >= HUD_UPDATE_INTERVAL) {
        lastHudUpdateRef.current = now
        const s = sim.getState()
        setState(s)

        // Update selected agent info
        const si = selectedIdxRef.current
        if (si >= 0 && si < sim.population.length) {
          const a = sim.population[si]
          setSelectedInfo({
            age: a.age,
            energy: a.energy.toFixed(3),
            gen: a.generation,
            ray: a.effectiveRayRange.toFixed(0),
            nodes: a.genome.nodes.length,
            conns: a.genome.enabledConnections.length,
          })
        } else {
          setSelectedInfo(null)
        }
      }

      rafRef.current = requestAnimationFrame(loop)
    }

    rafRef.current = requestAnimationFrame(loop)
    return () => {
      running = false
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
    }
  }, [started, renderFrame, state]) // state dep for HUD render only (throttled via timestamp)

  // ── Start / Reset ────────────────────────────────────────
  const handleStart = useCallback(() => {
    TRACKER.reset()
    const sim = new Simulation(DEFAULT_CONFIG)
    simRef.current = sim
    setExtinct(false)
    setSelectedIdx(-1)
    selectedIdxRef.current = -1
    setSelectedInfo(null)
    setStarted(true)
    setPaused(false)
    pausedRef.current = false
    speedRef.current = 1
    setSpeed(1)
    buildWallZone()
    const s = sim.getState()
    setState(s)
    renderFrame(sim, s, false, 1, -1, showRaysRef.current)
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
    selectedIdxRef.current = closestIdx
  }, [])

  // ── Keyboard controls ────────────────────────────────────
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === ' ' || e.code === 'Space') {
        e.preventDefault()
        setPaused(p => {
          pausedRef.current = !p
          return !p
        })
      } else if (e.key === '+' || e.key === '=') {
        setSpeed(s => {
          const next = Math.min(s * 2, 64)
          speedRef.current = next
          return next
        })
      } else if (e.key === '-' || e.key === '_') {
        setSpeed(s => {
          const next = Math.max(Math.floor(s / 2), 1)
          speedRef.current = next
          return next
        })
      } else if (e.key === 'r' || e.key === 'R') {
        handleStart()
      }
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [handleStart])

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

  return (
    <div className="min-h-screen bg-[#0a0a12] text-white flex flex-col">
      {/* Canvas */}
      <div className="flex-1 flex items-center justify-center p-2 sm:p-4">
        <div className="relative w-full max-w-[1200px]">
          <canvas
            ref={canvasRef}
            width={WORLD_W}
            height={WORLD_H}
            onClick={handleCanvasClick}
            className="w-full h-auto rounded-lg border border-white/10 cursor-crosshair"
            style={{ aspectRatio: `${WORLD_W}/${WORLD_H}` }}
          />

          {/* Start overlay */}
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
                <p className="text-white/20 text-xs">
                  Seed: {DEFAULT_CONFIG.simulation.seed} · Pop: {DEFAULT_CONFIG.population.initial_size} · World: {WORLD_W}×{WORLD_H}
                </p>
              </div>
            </div>
          )}

          {/* Extinct overlay */}
          {extinct && (
            <div className="absolute inset-0 flex items-center justify-center bg-black/70 rounded-lg">
              <div className="text-center space-y-4">
                <h2 className="text-2xl font-bold text-red-400">Extinction</h2>
                <p className="text-white/50">
                  Population died out at tick {state?.tick ?? '?'}. Record: {state?.recordApples ?? 0} apples.
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
            <div className="flex items-center gap-1">
              <button
                onClick={() => setPaused(p => { pausedRef.current = !p; return !p })}
                className="px-3 py-1.5 bg-white/10 hover:bg-white/20 rounded text-sm font-mono transition-colors"
              >
                {paused ? '\u25B6' : '\u23F8'}
              </button>
              <button
                onClick={() => {
                  const next = Math.max(Math.floor(speedRef.current / 2), 1)
                  speedRef.current = next
                  setSpeed(next)
                }}
                className="px-2 py-1.5 bg-white/10 hover:bg-white/20 rounded text-sm font-mono transition-colors"
              >
                -
              </button>
              <span className="px-2 py-1.5 text-sm font-mono text-white/60 min-w-[40px] text-center">
                {speed}x
              </span>
              <button
                onClick={() => {
                  const next = Math.min(speedRef.current * 2, 64)
                  speedRef.current = next
                  setSpeed(next)
                }}
                className="px-2 py-1.5 bg-white/10 hover:bg-white/20 rounded text-sm font-mono transition-colors"
              >
                +
              </button>
            </div>

            <div className="h-5 w-px bg-white/10" />

            <button
              onClick={() => {
                const next = !showRaysRef.current
                showRaysRef.current = next
                setShowRays(next)
              }}
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

            {selectedInfo && (
              <div className="text-xs font-mono text-white/50 flex flex-wrap gap-x-4 gap-y-1">
                <span>Age: <span className="text-white/80">{selectedInfo.age}</span></span>
                <span>Energy: <span className="text-white/80">{selectedInfo.energy}</span></span>
                <span>Gen: <span className="text-white/80">{selectedInfo.gen}</span></span>
                <span>Ray: <span className="text-white/80">{selectedInfo.ray}</span></span>
                <span>Nodes: <span className="text-white/80">{selectedInfo.nodes}</span></span>
                <span>Conns: <span className="text-white/80">{selectedInfo.conns}</span></span>
              </div>
            )}

            <div className="ml-auto text-xs text-white/20 hidden sm:block">
              Space: pause · +/-: speed · Click: select agent · R: reset
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
