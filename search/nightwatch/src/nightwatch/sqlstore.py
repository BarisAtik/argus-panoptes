"""An in-process log store on SQLite: the engine-free path, and a second opinion.

SQLite's LIKE ignores case for ASCII and sees the whole value, which is close to what a Sigma rule
means. It is slow and not a SIEM, so it serves tests, laptops and as a reference for the Lucene
results. Column names come from data, so they are always quoted.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterable


def _regexp(pattern: str, value: str | None) -> bool:
    return value is not None and re.search(pattern, value) is not None


class SqlStore:
    def __init__(self, events: Iterable[dict[str, str]]) -> None:
        rows = list(events)
        # SQLite column names ignore case, and logs hold both `ProcessId` and `processId`.
        spelling: dict[str, str] = {}
        for row in rows:
            for key in row:
                spelling.setdefault(key.lower(), key)
        self.columns = sorted(spelling.values())
        self.db = sqlite3.connect(":memory:")
        self.db.create_function("regexp", 2, _regexp)
        columns = ", ".join(f'"{name}" TEXT' for name in self.columns)
        self.db.execute(f"CREATE TABLE logs ({columns})")
        marks = ", ".join("?" for _ in self.columns)
        names = ", ".join(f'"{name}"' for name in self.columns)
        self.db.executemany(
            f"INSERT INTO logs ({names}) VALUES ({marks})",
            (
                [{key.lower(): value for key, value in row.items()}.get(name.lower())
                 for name in self.columns]
                for row in rows
            ),
        )

    def counts_by(self, where: str, field: str) -> dict[str, int]:
        sql = f'SELECT "{field}", COUNT(*) FROM logs WHERE ({where}) GROUP BY 1'
        return {key: count for key, count in self.db.execute(sql).fetchall() if key is not None}

    def count(self, where: str) -> int:
        return self.db.execute(f"SELECT COUNT(*) FROM logs WHERE ({where})").fetchone()[0]

    def rows(self, where: str, limit: int = 10) -> list[dict[str, str]]:
        cursor = self.db.execute(f"SELECT * FROM logs WHERE ({where}) LIMIT ?", (limit,))
        names = [column[0] for column in cursor.description]
        return [
            {name: value for name, value in zip(names, row, strict=True) if value is not None}
            for row in cursor.fetchall()
        ]
