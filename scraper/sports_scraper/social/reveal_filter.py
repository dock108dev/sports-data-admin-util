"""
Reveal filter for social post classification.

Re-exports the classify_reveal_risk function from the shared API module.
The scraper container has the API code in its PYTHONPATH.
"""

from app.utils.reveal_utils import RevealClassification, classify_reveal_risk

__all__ = ["RevealClassification", "classify_reveal_risk"]
