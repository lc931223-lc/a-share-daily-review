from datetime import date

from src.services.raw_archive_service import archive_raw


def test_archive_is_content_addressed(tmp_path):
    result = archive_raw(b'{"ok":true}', "tushare", "daily", date(2026, 9, 1), tmp_path)

    assert result.path.read_bytes() == b'{"ok":true}'
    assert result.sha256 in result.path.name
    assert result.path.parts[-5:] == (
        "data",
        "raw",
        "tushare",
        "2026-09-01",
        "daily",
        f"{result.sha256}.json",
    )[-5:]


def test_archive_returns_existing_path_for_same_content(tmp_path):
    first = archive_raw(b'{"ok":true}', "tushare", "daily", date(2026, 9, 1), tmp_path)
    second = archive_raw(b'{"ok":true}', "tushare", "daily", date(2026, 9, 1), tmp_path)

    assert second.path == first.path
    assert second.existed is True
