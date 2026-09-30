"""
Flere biler på én vagt (bekræftet af bruger 2026-09-30).

En .ddd-vagt kan være kørt i flere biler efter hinanden (Activity.vehicle_uses,
[[start_iso, slut_iso, reg], ...]). Lønafregning viser én linje pr. bil pr.
dag; selve loft-/overtidsberegningen forbliver ét sammenhængende skift, og
timerne fordeles blot bagefter efter hvilken bil de er arbejdet i.

Arbejdstid hvor kortet ikke står i nogen bil tilfalder nærmeste bil:
før første bil -> første bil, mellem to biler -> den forrige bil (indtil den
næste starter), efter sidste bil -> sidste bil.
"""
from datetime import datetime


def clipped_vehicle_uses(act) -> list[tuple[datetime, datetime, str]]:
    """Aktivitetens bilposter klippet til dens egne start/slut (en split-del
    eller en manuelt forkortet vagt har kun de biler, der ligger i dens tidsrum)."""
    uses = []
    for raw in getattr(act, "vehicle_uses", None) or []:
        try:
            s, e, reg = datetime.fromisoformat(raw[0]), datetime.fromisoformat(raw[1]), raw[2]
        except (ValueError, IndexError, TypeError):
            continue
        s, e = max(s, act.start_time), min(e, act.end_time)
        if e > s and reg:
            uses.append((s, e, reg))
    return sorted(uses)


def has_multiple_vehicles(uses: list[tuple[datetime, datetime, str]]) -> bool:
    return len({reg for _, _, reg in uses}) > 1


def vehicle_assignment_intervals(
    start: datetime, end: datetime, uses: list[tuple[datetime, datetime, str]],
) -> list[tuple[datetime, datetime, str]] | None:
    """Sammenhængende intervaller der dækker HELE [start, end], hvert tildelt
    én bil efter nærmeste-bil-reglen. None når vagten kun har én (eller ingen)
    bil – så beregnes den præcis som hidtil."""
    if not has_multiple_vehicles(uses):
        return None
    intervals = []
    for i, (use_start, _, reg) in enumerate(uses):
        interval_start = start if i == 0 else use_start
        interval_end = uses[i + 1][0] if i + 1 < len(uses) else end
        if interval_end > interval_start:
            intervals.append((interval_start, interval_end, reg))
    return intervals


def split_by_vehicle(segments, intervals):
    """Deler (start, slut)-segmenter yderligere ved bilskift og yielder
    (start, slut, reg). Uden intervaller: segmenterne uændret med reg=None."""
    for seg_start, seg_end in segments:
        if not intervals:
            yield seg_start, seg_end, None
            continue
        for i_start, i_end, reg in intervals:
            s, e = max(seg_start, i_start), min(seg_end, i_end)
            if e > s:
                yield s, e, reg
