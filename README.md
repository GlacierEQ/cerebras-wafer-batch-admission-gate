# Wafer Batch Admission

Independent GlacierEQ inference admission controller aligned to extreme-throughput serving problems.

> **Not affiliated.** This repository is not affiliated with, endorsed by, employed by, or deployed at Cerebras.

## Purpose

Admit inference batches only when the batch fits a declared latency, quality, throughput, queue, and size envelope.

## Runtime

The controller evaluates predicted batch behavior against explicit service bounds. Rejections contain every violated metric with observed value, operator, limit, and unit. Accepted batches contain quantitative headroom for each bound and deterministic envelope/headroom fingerprints.

It enforces:

- maximum batch size
- maximum predicted latency
- minimum predicted quality score
- required throughput not exceeding available throughput
- maximum queue depth
- request expiry and bounded evaluation work
- fail-closed schema validation

## Proof

```bash
python -m pytest -q
python scripts/operate.py
```

Install with `python -m pip install .`; the JSON CLI is `batch-admission`.

## Boundary

This is a portable admission-control kernel using caller-supplied predictions/capacity. It does not claim Cerebras infrastructure access or proprietary performance telemetry.
