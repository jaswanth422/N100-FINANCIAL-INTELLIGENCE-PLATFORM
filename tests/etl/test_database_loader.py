from pathlib import Path

import pandas as pd

from etl.loader import AuditRow, _reject_orphans, connect_database, create_schema, insert_frame


def test_schema_has_eleven_tables(tmp_path: Path):
    connection = connect_database(tmp_path / "test.db")
    create_schema(connection, Path("db/schema.sql"))
    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    }
    connection.close()
    assert len(tables) == 11
    assert "peer_percentiles" in tables


def test_foreign_keys_are_enabled(tmp_path: Path):
    connection = connect_database(tmp_path / "test.db")
    assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    connection.close()


def test_reject_orphans():
    frame = pd.DataFrame({"company_id": ["AAA", "BBB", None], "value": [1, 2, 3]})
    clean, rejected = _reject_orphans(frame, {"AAA"})
    assert clean["company_id"].tolist() == ["AAA"]
    assert rejected == 2


def test_insert_frame_uses_schema_columns(tmp_path: Path):
    connection = connect_database(tmp_path / "test.db")
    create_schema(connection, Path("db/schema.sql"))
    frame = pd.DataFrame({"id": ["AAA"], "company_name": ["Alpha"], "ignored": [1]})
    assert insert_frame(connection, "companies", frame) == 1
    assert connection.execute("SELECT company_name FROM companies").fetchone()[0] == "Alpha"
    connection.close()


def test_audit_row_fields():
    row = AuditRow("a.xlsx", "companies", 10, 9, 1, "invalid")
    assert row.source_rows == row.loaded_rows + row.rejected_rows
