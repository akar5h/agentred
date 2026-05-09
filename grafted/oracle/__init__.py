"""Oracle implementations."""

from grafted.oracle.judge import Judge
from grafted.oracle.llm_oracle import LlmOracle
from grafted.oracle.pattern_oracle import PatternOracle

__all__ = ["PatternOracle", "LlmOracle", "Judge"]
