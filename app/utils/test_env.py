"""
Testmiljø (2026-10-07): sættes med LONSYSTEM_ENV=test i testmiljøets .env.
I produktion er variablen ikke sat, og intet ændrer sig.

- Rød TESTMILJØ-bjælke øverst på siden (viser hvilken backup testdata kommer fra).
- E-mail kan aldrig sendes fra testmiljøet.
"""
import os
from pathlib import Path
from typing import Optional

TESTDATA_SOURCE_FILE = Path(__file__).resolve().parent.parent / "database" / "TESTDATA_SOURCE.txt"


def is_test_env() -> bool:
    return os.getenv("LONSYSTEM_ENV", "").strip().lower() == "test"


def test_data_source() -> Optional[str]:
    """Hvilken backup testdata er gendannet fra (skrives af opdater_testdata.ps1)."""
    try:
        return TESTDATA_SOURCE_FILE.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None
