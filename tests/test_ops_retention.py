"""Invariantes de retención de deploy/iacademy/ops/retention.py.

No se ejecutan contra producción: solo la lógica pura de selección.
"""
import datetime as dt
import importlib.util
import sys
from pathlib import Path

OPS = Path(__file__).resolve().parents[1] / "deploy" / "iacademy" / "ops"
spec = importlib.util.spec_from_file_location("retention", OPS / "retention.py")
retention = importlib.util.module_from_spec(spec)
sys.modules["retention"] = retention
spec.loader.exec_module(retention)

NOW = dt.datetime(2026, 10, 24, 12, tzinfo=dt.UTC)


def names(*days_oct):
    return [(f"iacademy-social-2026{m:02d}{d:02d}T023000Z", dt.date(2026, m, d)) for m, d in days_oct]


def test_keeps_recent_daily_window():
    sets = names((10, 1), (10, 20), (10, 23))
    assert retention.select_expired(sets, NOW, daily_days=30, monthly_months=12) == []


def test_expires_old_non_first_of_month():
    sets = names((1, 5), (1, 6), (2, 3), (10, 23))  # 6-ene caduca; 5-ene (primer completo ene) y 3-feb (primer completo feb) se quedan
    assert retention.select_expired(sets, NOW, daily_days=30, monthly_months=12) == [
        "iacademy-social-20260106T023000Z"
    ]


def test_never_expires_newest_even_outside_window():
    sets = [
        ("iacademy-social-20240101T023000Z", dt.date(2024, 1, 1)),
        ("iacademy-social-20240102T023000Z", dt.date(2024, 1, 2)),
    ]
    assert retention.select_expired(sets, NOW, daily_days=30, monthly_months=12) == [
        "iacademy-social-20240101T023000Z"
    ]


def test_keeps_first_complete_of_each_month_within_12m():
    sets = [("iacademy-social-20251201T023000Z", dt.date(2025, 12, 1))]
    assert retention.select_expired(sets, NOW, daily_days=30, monthly_months=12) == []


def test_expires_monthly_beyond_12m():
    sets = [
        ("iacademy-social-20240901T023000Z", dt.date(2024, 9, 1)),
        ("iacademy-social-20261023T023000Z", dt.date(2026, 10, 23)),
    ]
    assert retention.select_expired(sets, NOW, daily_days=30, monthly_months=12) == [
        "iacademy-social-20240901T023000Z"
    ]


def test_empty_is_noop():
    assert retention.select_expired([], NOW) == []


def test_twelve_calendar_months_do_not_shrink_at_month_end():
    now = dt.datetime(2026, 10, 31, 12, tzinfo=dt.UTC)
    sets = [
        ("iacademy-social-20251101T023000Z", dt.date(2025, 11, 1)),
        ("iacademy-social-20261030T023000Z", dt.date(2026, 10, 30)),
    ]
    assert retention.select_expired(sets, now, daily_days=30, monthly_months=12) == []


def test_prune_never_touches_foreign_sets_incomplete_sets_or_symlinks(tmp_path, monkeypatch):
    class FixedDatetime(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW

    monkeypatch.setattr(retention.dt, "datetime", FixedDatetime)
    expired = tmp_path / "iacademy-social-20240101T023000Z"
    newest = tmp_path / "iacademy-social-20261023T023000Z"
    foreign = tmp_path / "another-system-20240101T023000Z"
    incomplete = tmp_path / "iacademy-social-20240102T023000Z"
    linked = tmp_path / "iacademy-social-20240103T023000Z"
    linked_marker = tmp_path / "iacademy-social-20240104T023000Z"
    for directory in (expired, newest, foreign, incomplete, linked_marker):
        directory.mkdir()
    for directory in (expired, newest, foreign):
        (directory / "COMPLETE").write_text("verified")
    linked.symlink_to(foreign, target_is_directory=True)
    (linked_marker / "COMPLETE").symlink_to(foreign / "COMPLETE")

    retention.prune(tmp_path, daily_days=30, monthly_months=12)

    assert not expired.exists()
    assert newest.is_dir()
    assert foreign.is_dir()
    assert incomplete.is_dir()
    assert linked.is_symlink()
    assert linked_marker.is_dir()
