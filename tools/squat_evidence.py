"""Backward-compatible shim: squat evidence is now config-driven.

The implementation moved to tools/action_evidence.py with per-action
ActionConfig; build_evidence defaults to the squat config so existing callers
keep working unchanged.
"""
from tools.action_config import ACTIONS
from tools.action_evidence import (  # noqa: F401
    build_evidence, evidence_images, extract_clip, sample, side_samples, usable,
)

__all__ = ["ACTIONS", "build_evidence", "evidence_images", "extract_clip", "sample", "side_samples", "usable"]
