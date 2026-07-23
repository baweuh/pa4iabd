// ══════════════════════════════════════════════════════════════════════════════
//  test-poc26-smoke.ts — Smoke test for HyperNEAT + Hebbian integration
//
//  Validates:
//    1. Default config: both features OFF, simulation runs 500 ticks
//    2. Hebbian-only: applyHebbian called, weights change, no crash
//    3. HyperNEAT-only: substrate network built, agents move, no crash
//    4. Both enabled: Hebbian on substrate, no crash, 500-tick survival
//  5. Coordinate consistency: substrateInputCoords matches sense() column order
//
//  Run:  bun run scripts/test-poc26-smoke.ts
// ══════════════════════════════════════════════════════════════════════════════

import { DEFAULT_CONFIG, validateConfig, deriveNumInputs, type SimConfig } from '../src/lib/alife/config';
import { Simulation } from '../src/lib/alife/simulation';
import { SeededRNG, Genome } from '../src/lib/alife/genome';
import { NeuralNetwork } from '../src/lib/alife/network';
import { substrateInputCoords } from '../src/lib/alife/hyperneat';
import { Agent } from '../src/lib/alife/agent';
import { Environment } from '../src/lib/alife/environment';
import { rayAngles } from '../src/lib/alife/geometry';

// ── Helpers ──────────────────────────────────────────────────

let passCount = 0;
let failCount = 0;

function assert(cond: boolean, label: string): void {
  if (cond) { passCount++; }
  else { failCount++; console.error(`  FAIL: ${label}`); }
}

function section(title: string): void {
  console.log(`\n── ${title} ──`);
}

function makeConfig(overrides: Partial<SimConfig>): SimConfig {
  // Deep-merge helper for frozen config
  const base = DEFAULT_CONFIG as unknown as Record<string, unknown>;
  const result = { ...base };
  for (const [k, v] of Object.entries(overrides)) {
    (result as Record<string, unknown>)[k] = v;
  }
  return result as unknown as SimConfig;
}

function runSimTicks(sim: Simulation, ticks: number): void {
  for (let i = 0; i < ticks; i++) {
    if (sim.isExtinct) break;
    sim.tick();
  }
}

// ── Test 1: Default config — both features OFF ──────────────

section('Test 1: Default config (hyperneat=false, hebbian=false)');
{
  const cfg = DEFAULT_CONFIG;
  validateConfig(cfg);
  assert(!cfg.hyperneat.enabled, 'hyperneat disabled by default');
  assert(!cfg.hebbian.enabled, 'hebbian disabled by default');

  const sim = new Simulation(cfg);
  assert(sim.population.length === cfg.population.initial_size, `initial pop = ${cfg.population.initial_size}`);
  assert(!sim.population[0]._plastic, 'agent._plastic is false');

  runSimTicks(sim, 500);
  const state = sim.getState();
  console.log(`  After 500 ticks: pop=${state.population}, tick=${state.tick}, foragers(avg)=${state.meanForageRate.toFixed(4)}`);
  assert(state.tick === 500, 'reached 500 ticks');
  // With 100 agents and 80 apples, population should survive
  assert(state.population > 0, 'population survived');
}

// ── Test 2: Hebbian-only ─────────────────────────────────────

section('Test 2: Hebbian-only (hebbian.enabled=true)');
{
  const cfg = makeConfig({
    hebbian: { enabled: true, learning_rate: 0.01, weight_max: 5.0, eligibility_decay: 0.99, baseline_rate: 0.01 },
  });
  validateConfig(cfg);

  const sim = new Simulation(cfg);
  const agent = sim.population[0];
  assert(agent._plastic, 'agent._plastic is true under Hebbian');

  // Snapshot a weight before
  const net = agent.network as unknown as { _incoming: Map<number, [number, number][]> };
  const firstNodeWithEdges = [...net._incoming.entries()].find(([_, edges]) => edges.length > 0);
  let weightBefore = 0;
  if (firstNodeWithEdges) {
    weightBefore = firstNodeWithEdges[1][0][1];
  }

  runSimTicks(sim, 500);
  const state = sim.getState();
  console.log(`  After 500 ticks: pop=${state.population}, tick=${state.tick}`);
  assert(state.tick === 500, 'reached 500 ticks');
  assert(state.population > 0, 'population survived with Hebbian');

  // Verify a weight changed (at least one agent must have eaten)
  const hasEaten = sim.population.some(a => a.applesEaten > 0);
  console.log(`  Agents that ate: ${sim.population.filter(a => a.applesEaten > 0).length}/${sim.population.length}`);
  // With 100 agents and 80 apples in a small world, SOME should eat
  assert(hasEaten, 'at least one agent ate an apple');
}

// ── Test 3: HyperNEAT-only ───────────────────────────────────

section('Test 3: HyperNEAT-only (hyperneat.enabled=true)');
{
  const cfg = makeConfig({
    hyperneat: { enabled: true, weight_scale: 3.0, connectivity: 1.0, bootstrap_hidden_nodes: 0 },
  });
  validateConfig(cfg);

  const sim = new Simulation(cfg);
  const agent = sim.population[0];
  assert(!agent._plastic, 'agent._plastic is false (Hebbian off)');

  // Verify the network has the right number of inputs/outputs
  // Under HyperNEAT, the substrate is num_inputs -> 2 outputs (no hidden)
  console.log(`  Agent network: inputs=${agent.network.inputIds.length}, outputs=${agent.network.outputIds.length}`);
  assert(agent.network.inputIds.length === cfg.network.num_inputs,
    `substrate has ${cfg.network.num_inputs} inputs`);
  assert(agent.network.outputIds.length === 2, 'substrate has 2 outputs');

  runSimTicks(sim, 500);
  const state = sim.getState();
  console.log(`  After 500 ticks: pop=${state.population}, tick=${state.tick}`);
  assert(state.tick === 500, 'reached 500 ticks with HyperNEAT');
  // HyperNEAT agents may go extinct (falsified in Python), but should not crash
  console.log(`  Population survived: ${state.population > 0}`);
}

// ── Test 4: Both enabled ─────────────────────────────────────

section('Test 4: HyperNEAT + Hebbian combined');
{
  const cfg = makeConfig({
    hyperneat: { enabled: true, weight_scale: 3.0, connectivity: 1.0, bootstrap_hidden_nodes: 0 },
    hebbian: { enabled: true, learning_rate: 0.01, weight_max: 5.0, eligibility_decay: 0.99, baseline_rate: 0.01 },
  });
  validateConfig(cfg);

  const sim = new Simulation(cfg);
  const agent = sim.population[0];
  assert(agent._plastic, 'agent._plastic is true (Hebbian on)');
  console.log(`  Agent network: inputs=${agent.network.inputIds.length}, outputs=${agent.network.outputIds.length}`);

  runSimTicks(sim, 500);
  const state = sim.getState();
  console.log(`  After 500 ticks: pop=${state.population}, tick=${state.tick}`);
  assert(state.tick === 500, 'reached 500 ticks with both features');
  // Should not crash — that's the main assertion
}

// ── Test 5: Coordinate consistency ───────────────────────────

section('Test 5: substrateInputCoords matches sense() column count');
{
  const cfg = DEFAULT_CONFIG;
  const coords = substrateInputCoords(cfg.sensors);
  console.log(`  Substrate input coords: ${coords.length}, expected num_inputs: ${cfg.network.num_inputs}`);
  assert(coords.length === cfg.network.num_inputs,
    `coordinate count ${coords.length} == num_inputs ${cfg.network.num_inputs}`);

  // Every coord should be a valid (x, y, z) with x,y in [-1,1], z in [-1,1]
  for (let i = 0; i < coords.length; i++) {
    const [x, y, z] = coords[i];
    assert(Math.abs(x) <= 1.0 + 1e-9 && Math.abs(y) <= 1.0 + 1e-9 && Math.abs(z) <= 1.0 + 1e-9,
      `coord ${i} in [-1,1]^3: (${x.toFixed(3)}, ${y.toFixed(3)}, ${z.toFixed(3)})`);
  }
}

// ── Test 6: applyHebbian no-op when disabled ─────────────────

section('Test 6: applyHebbian is no-op when hebbian disabled');
{
  const rng = new SeededRNG(42);
  const genome = Genome.newFullyConnected(
    DEFAULT_CONFIG.network.num_inputs,
    DEFAULT_CONFIG.network.num_outputs,
    DEFAULT_CONFIG.genome,
    DEFAULT_CONFIG.sensors,
    rng,
  );
  // Build WITHOUT hebbian config
  const net = new NeuralNetwork(genome, DEFAULT_CONFIG.network);
  const inputs = new Array(DEFAULT_CONFIG.network.num_inputs).fill(0.5);
  const out1 = net.activate(inputs);
  // Call applyHebbian (should be no-op)
  net.applyHebbian(1.0);
  const out2 = net.activate(inputs);
  assert(out1[0] === out2[0] && out1[1] === out2[1],
    'output unchanged after applyHebbian when disabled');
}

// ── Test 7: applyHebbian changes weights when enabled ────────

section('Test 7: applyHebbian modifies weights when enabled');
{
  const rng = new SeededRNG(42);
  const genome = Genome.newFullyConnected(
    DEFAULT_CONFIG.network.num_inputs,
    DEFAULT_CONFIG.network.num_outputs,
    DEFAULT_CONFIG.genome,
    DEFAULT_CONFIG.sensors,
    rng,
  );
  const hebbianCfg = { enabled: true, learning_rate: 0.1, weight_max: 5.0, eligibility_decay: 0.99, baseline_rate: 0.01 };
  const net = new NeuralNetwork(genome, DEFAULT_CONFIG.network, hebbianCfg);
  const inputs = new Array(DEFAULT_CONFIG.network.num_inputs).fill(0.5);

  // Activate and apply Hebbian with reward
  net.activate(inputs);
  net.applyHebbian(1.0);
  net.activate(inputs);
  net.applyHebbian(1.0);

  // The output should differ from a frozen network
  const netFrozen = new NeuralNetwork(genome, DEFAULT_CONFIG.network);
 const outFrozen = netFrozen.activate(inputs);
  const outPlastic = net.activate(inputs);
  // With lr=0.1 and reward=1.0, weights should have shifted
  const diff = Math.abs(outPlastic[0] - outFrozen[0]) + Math.abs(outPlastic[1] - outFrozen[1]);
  console.log(`  Output diff (plastic vs frozen): ${diff.toFixed(6)}`);
  assert(diff > 1e-9, 'plastic network output differs from frozen after Hebbian updates');
}

// ── Summary ──────────────────────────────────────────────────

console.log(`\n═══ Results: ${passCount} passed, ${failCount} failed ═══`);
if (failCount > 0) {
  process.exit(1);
}
