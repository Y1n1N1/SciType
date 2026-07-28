"""Single-command parsing engine for SciType V0.1."""

from collections.abc import Mapping
from functools import lru_cache

from .dictionary import load_dictionary


@lru_cache(maxsize=1)
def _default_dictionary() -> dict[str, str]:
    """Load the packaged dictionary once for normal API use."""
    return load_dictionary()


def parse_text(
    text: str,
    dictionary: Mapping[str, str] | None = None,
) -> str:
    """Parse one complete command, returning unknown input unchanged."""
    symbols = _default_dictionary() if dictionary is None else dictionary
    return symbols.get(text, text)

