# Issue contract — Wafer Batch Admission Gate

## Problem
Integrating extreme-speed inference into reliable, broadly available production systems.

## Desired outcome
A bounded, open, testable implementation of **Wafer Batch Admission Gate** that demonstrates Admit batches only under a declared latency/quality envelope; emit rejection receipts with exact violated bounds.

## Non-goals
- Cerebras affiliation or proprietary integration
- Portfolio-wide scale/performance claims
- UI marketing site

## Acceptance
1. Mechanism module implements allow + refuse with structured receipts
2. pytest behavioral suite green
3. operate.py cold-start produces JSON receipt
4. Non-affiliation disclaimer preserved
