"""M4 · Hallazgos.

Three decoupled, separately re-runnable stages:

1. ``select``  — deterministic prefilter + zero-shot classifier → extraction
   units (target sentence + context window with exact source references).
2. ``extract`` — an LLM (Kaggle vLLM or local Ollama) turns units into raw
   *candidates*. Extraction never sets any verification flag.
3. ``verify``  — deterministic, per-field checks against the source text →
   ``machine_verified`` / ``rejected``. Scientific review is a fourth, human-only
   step (``review``) and is never inferred from machine verification.
"""
