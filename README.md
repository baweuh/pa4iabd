# Artificial Life Simulation (Next.js + HyperNEAT)

## Overview

This project is a web-based **Artificial Life (ALife) Simulation** built with **Next.js**, **React**, and **Tailwind CSS**. At its core, it implements an advanced evolutionary engine utilizing **HyperNEAT** (NeuroEvolution of Augmenting Topologies), speciation, and novelty search to evolve complex agent behaviors within a simulated 2D environment.

## Features

* **Advanced Evolutionary Engine**: A custom-built ALife system featuring:
  * **HyperNEAT**: Evolves neural networks using Compositional Pattern Producing Networks (CPPNs) to capture spatial geometry.
  * **Speciation**: Protects structural innovation by clustering similar genomes during reproduction.
  * **Novelty Search**: Drives evolution by rewarding unique and novel behaviors rather than relying strictly on objective fitness functions.
* **Modern Tech Stack**: 
  * **Next.js (App Router)** for the application framework.
  * **TypeScript** for strict type safety and robust architecture.
  * **Tailwind CSS** & **shadcn/ui** for a sleek, responsive, and accessible user interface.
  * **Bun** as the fast, all-in-one JavaScript runtime and package manager.
* **Production Ready**: Includes a `Caddyfile` for easy, secure production deployment and reverse proxying.

## Project Structure

* `/src/lib/alife/`: The core simulation and evolutionary engine.
  * `agent.ts`, `environment.ts`, `simulation.ts`: Entities, physics, and world state management.
  * `genome.ts`, `network.ts`: Neural network representation and feed-forward execution.
  * `hyperneat.ts`: Logic for mapping CPPNs to the agent's neural substrate.
  * `speciation.ts`, `novelty.ts`: Advanced evolutionary dynamics.
  * `geometry.ts`: Spatial math and hit detection.
* `/src/app/`: Next.js routing, frontend pages, and global styles.
* `/src/components/ui/`: Reusable, customizable UI components generated via shadcn/ui.
* `/scripts/`: Automation, utility scripts, and smoke tests (e.g., `test-poc26-smoke.ts`).

## Getting Started

### Prerequisites

Ensure you have [Bun](https://bun.sh/) installed on your machine.

### Installation

1. Clone the repository and navigate to the project directory.
2. Install the dependencies using Bun:
   ```bash
   bun install
   ```

### Running the Development Server

Start the Next.js development server:
```bash
bun run dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the simulation dashboard.

## Deployment

The repository is equipped with a `Caddyfile`, making it straightforward to host using [Caddy Web Server](https://caddyserver.com/). It handles automatic HTTPS and routing for your production environment.
