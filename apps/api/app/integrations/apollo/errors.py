"""Apollo-specific provider errors whose semantics exceed generic HTTP classification."""

from __future__ import annotations


class ApolloAmbiguousEnrichmentError(Exception):
    """Raised when Apollo may have started credit-consuming work but recovery identity is absent."""

    def __init__(self, *, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
