"""Version-bound, evidence-first Unreal Engine information pool."""

from .builder import build_information_pool
from .query import query_information_pool

__all__ = ["build_information_pool", "query_information_pool"]
