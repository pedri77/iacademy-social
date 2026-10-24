#!/usr/bin/env python3
"""Retención de backups iacademy-social-ops.

Invariantes:
- Solo se consideran conjuntos COMPLETOS de este directorio (subdir con COMPLETE).
- Diarios: conjuntos completos de los últimos N días se conservan.
- Mensuales: el primer conjunto completo de cada mes se conserva M meses.
- Nunca se tocan: conjuntos sin COMPLETE (INCOMPLETE), symlinks, ficheros sueltos
  ni directorios que no siguen el patrón de nombres de este sistema.
"""
import argparse
import datetime as dt
import re
import sys
from pathlib import Path

SET_RE = re.compile(r"^iacademy-social-(\d{8})T\d{6}Z$")


def parse_set_date(name: str) -> dt.date | None:
    m = SET_RE.match(name)
    if not m:
        return None
    try:
        return dt.datetime.strptime(m.group(1), "%Y%m%d").date()
    except ValueError:
        return None


def is_complete_set(path: Path) -> bool:
    marker = path / "COMPLETE"
    return path.is_dir() and not path.is_symlink() and marker.is_file() and not marker.is_symlink()


def select_expired(
    names_with_dates: list[tuple[str, dt.date]],
    now: dt.datetime,
    daily_days: int = 30,
    monthly_months: int = 12,
) -> list[str]:
    """Nombres de conjuntos completos que caducan según la política.

    Conserva: todo conjunto con fecha >= now-daily_days; el primero (más antiguo)
    de cada mes dentro de los últimos monthly_months; nunca el más reciente global.
    """
    if not names_with_dates:
        return []
    keep: set[str] = set()
    daily_cutoff = (now - dt.timedelta(days=daily_days)).date()
    first_month = now.year * 12 + now.month - monthly_months
    monthly_cutoff = dt.date(first_month // 12, first_month % 12 + 1, 1)

    ordered = sorted(names_with_dates, key=lambda nd: nd[1])
    keep.add(ordered[-1][0])  # el más reciente nunca se borra
    for name, date in ordered:
        if date >= daily_cutoff:
            keep.add(name)
    first_of_month: dict[dt.date, str] = {}
    for name, date in ordered:
        key = date.replace(day=1)
        if key not in first_of_month:
            first_of_month[key] = name
    for month, name in first_of_month.items():
        if month >= monthly_cutoff:
            keep.add(name)
    return [name for name, _ in names_with_dates if name not in keep]


def prune(root: Path, daily_days: int, monthly_months: int, dry_run: bool = False) -> int:
    now = dt.datetime.now(dt.UTC)
    sets: list[tuple[str, dt.date]] = []
    for child in sorted(root.iterdir()):
        if not is_complete_set(child):
            continue
        date = parse_set_date(child.name)
        if date is None:
            continue  # patrón ajeno: no tocar
        sets.append((child.name, date))
    expired = select_expired(sets, now, daily_days, monthly_months)
    for name in expired:
        target = root / name
        print(f"iacademy-social-ops: retención elimina {name}")
        if not dry_run:
            import shutil

            shutil.rmtree(target)
    print(f"iacademy-social-ops: retención: {len(sets)} completos, {len(expired)} expirados")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["prune"])
    ap.add_argument("--root", required=True)
    ap.add_argument("--daily-days", type=int, default=30)
    ap.add_argument("--monthly-months", type=int, default=12)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    return prune(Path(a.root), a.daily_days, a.monthly_months, a.dry_run)


if __name__ == "__main__":
    sys.exit(main())
