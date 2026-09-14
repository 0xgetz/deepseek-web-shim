"""deepseek-web-shim — an OpenAI-compatible local shim over DeepSeek's web chat.

Research / lab code. It speaks the same protocol the browser speaks: it solves
the site's proof-of-work locally and forwards your own authenticated session.
It bundles no credentials and creates no accounts — read the README's
"Intended use and caveats" before running it.
"""
from __future__ import annotations

__version__ = "0.1.2"

from .pow import PowSolver, deepseek_sha3, pow_prefix, solve_pure  # noqa: F401

__all__ = ["PowSolver", "deepseek_sha3", "pow_prefix", "solve_pure", "__version__"]
