"""CallTone model server — Tier 3 of the demo deployment.

This package runs on the on-demand GPU VM (Vast.ai RTX 4090). It exposes a
small FastAPI surface that the backend (Tier 2, Hetzner CPX31) calls to run
the LAYER 1 → LAYER 2 → LAYER 3 pipeline on uploaded audio.

The package is intentionally separate from ``backend/app/`` because the deploy
target, dependency set, and security surface are all different. See
``docs/DEMO_DEPLOYMENT_PLAN.md`` for the full rationale.
"""

__version__ = "0.1.0"
