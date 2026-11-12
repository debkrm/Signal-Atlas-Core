"""
Disposable DuckDB Query View Layer over Immutable Silver Parquet Partitions.

Implements query view invariants per AGENTS.md Rule 10.2:
- Parquet files plus SHA-256 hashes constitute the system of record.
- DuckDB is a rebuildable, disposable analytical view engine over the Parquet partitions.
- Core package stays stdlib-pure; DuckDB is isolated in optional extra.
- Disposable verification: deleting or unlinking the .duckdb file changes zero fingerprints (Gate G2B.5-6).
"""

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union

try:
    import duckdb
    _DUCKDB_AVAILABLE = True
except ImportError:
    _DUCKDB_AVAILABLE = False

from signal_core.storage.silver import SilverStorage


class DuckDBViewError(ValueError):
    """Base exception for DuckDB view layer errors."""
    pass


class DuckDBDependencyMissingError(DuckDBViewError):
    """Raised when duckdb package is not installed."""
    pass


def _require_duckdb() -> None:
    if not _DUCKDB_AVAILABLE:
        raise DuckDBDependencyMissingError(
            "duckdb is required for DuckDBViewLayer. Install via 'pip install duckdb' or '.[storage]'."
        )


class DuckDBViewLayer:
    """
    Manages disposable, rebuildable DuckDB SQL views over Silver Parquet partitions.
    """
    def __init__(
        self,
        silver_storage: SilverStorage,
        db_path: Optional[Union[str, Path]] = None,
    ) -> None:
        _require_duckdb()
        self._silver = silver_storage
        self._db_path = Path(db_path).resolve() if db_path is not None else None
        self._conn: Optional[duckdb.DuckDBPyConnection] = None

    @property
    def db_path(self) -> Optional[Path]:
        return self._db_path

    @property
    def silver_storage(self) -> SilverStorage:
        return self._silver

    def connect(self) -> "DuckDBViewLayer":
        """Establishes DuckDB connection and registers Silver views."""
        _require_duckdb()
        if self._conn is None:
            db_target = str(self._db_path) if self._db_path is not None else ":memory:"
            if self._db_path is not None:
                self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = duckdb.connect(db_target)
            self.register_views()
        return self

    def register_views(self) -> None:
        """Registers SQL views pointing to Silver Parquet files."""
        if self._conn is None:
            raise DuckDBViewError("Cannot register views: connection is closed. Call connect() first.")

        bhavcopy_pattern = (self._silver.bhavcopy_dir / "*" / "*.parquet").as_posix()
        # Create view over bhavcopy partitions
        sql = f"""
        CREATE OR REPLACE VIEW silver_bhavcopy AS
        SELECT
            isin,
            symbol,
            series,
            trade_date,
            open,
            high,
            low,
            close,
            volume,
            traded_value
        FROM read_parquet('{bhavcopy_pattern}')
        """
        try:
            self._conn.execute(sql)
        except Exception as exc:
            # If no parquet files exist yet, register an empty typed view
            empty_sql = """
            CREATE OR REPLACE VIEW silver_bhavcopy AS
            SELECT
                CAST(NULL AS VARCHAR) AS isin,
                CAST(NULL AS VARCHAR) AS symbol,
                CAST(NULL AS VARCHAR) AS series,
                CAST(NULL AS VARCHAR) AS trade_date,
                CAST(NULL AS VARCHAR) AS open,
                CAST(NULL AS VARCHAR) AS high,
                CAST(NULL AS VARCHAR) AS low,
                CAST(NULL AS VARCHAR) AS close,
                CAST(NULL AS BIGINT) AS volume,
                CAST(NULL AS VARCHAR) AS traded_value
            WHERE 1=0
            """
            self._conn.execute(empty_sql)

    def query(self, sql: str, params: Optional[Sequence[Any]] = None) -> List[Tuple[Any, ...]]:
        """Executes a SQL query and returns rows as tuples."""
        if self._conn is None:
            self.connect()
        if self._conn is None:
            raise DuckDBViewError("Failed to establish DuckDB connection.")
        if params is not None:
            return self._conn.execute(sql, params).fetchall()
        return self._conn.execute(sql).fetchall()

    def close(self) -> None:
        """Closes active DuckDB connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def unlink_database_file(self) -> bool:
        """
        Closes connection and deletes the .duckdb database file from disk.
        Returns True if a file was deleted.
        """
        self.close()
        if self._db_path is not None and self._db_path.exists():
            self._db_path.unlink()
            # Also clean up WAL file if present
            wal_file = self._db_path.with_name(self._db_path.name + ".wal")
            if wal_file.exists():
                wal_file.unlink()
            return True
        return False
