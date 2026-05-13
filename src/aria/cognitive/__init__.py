"""ARIA Cognitive Engine — LLM-based reasoning loop with tool use.

execute → incorporate results → iterate until satisfied.
"""

from aria.cognitive.engine import CognitiveEngine, ReasoningContext

__all__ = ["CognitiveEngine", "ReasoningContext"]
