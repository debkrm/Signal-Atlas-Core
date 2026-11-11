# Signal Atlas Core

`signal-core` is the clean, minimal, offline-first quantitative research and market-data foundation for Signal Atlas.

## Core Design Principles

1. **Deterministic & Offline-First:**
   - Core research contracts and simulators operate 100% offline from immutable, in-memory dataset contracts.
   - Zero coupling to live SQL databases or network APIs during simulation.

2. **Rigorous Numeric & Accounting Integrity:**
   - Financial values are modeled strictly with unrounded, exact `Decimal` types.
   - Binary floating-point arithmetic is strictly forbidden for financial calculations.
   - Gross P&L, statutory fees, execution slippage, and net P&L are maintained as separate, auditable components.

3. **Cryptographic Content Provenance:**
   - Every dataset and point-in-time universe schedule is content-fingerprinted with deterministic canonicalization.
   - Content identification proves dataset immutability against known digests, but is never confused with external exchange source authenticity.

4. **Zero Duplicate Simulation Engines:**
   - A single authoritative simulation loop guarantees that all research signals, risk gates, position sizing, and cost models run through identical execution paths.

