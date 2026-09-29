"""Naturlig sortering af navne med tal: 0, 00, 000, 1, 2 … 10 (ikke 1, 10, 2)."""
import re

_PARTS = re.compile(r"(\d+)")


def natural_key(name: str | None) -> tuple:
    """Sorteringsnøgle: talblokke sammenlignes som tal; ved samme talværdi kommer det korteste først."""
    s = (name or "").strip()
    key = []
    for part in _PARTS.split(s.casefold()):
        if part.isdigit():
            key.append((1, int(part), len(part)))
        elif part:
            key.append((2, part, 0))
    return tuple(key)
