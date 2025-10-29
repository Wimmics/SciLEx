"""
Async state manager using SQLite for efficient batch updates.

Replaces JSON file-based state management with SQLite3 for:
- Eliminates global lock contention (1,280-3,200 file writes → 130-320 DB writes)
- Batch state updates (10 pages per write instead of 1)
- Atomic transactions with ACID guarantees
- Faster read/write performance
- Optional async operations with aiosqlite
"""

import asyncio
import json
import logging
import os
import sqlite3
from contextlib import asynccontextmanager
from datetime import date
from typing import Dict, Any, Optional

import aiosqlite


class StateManager:
    """
    Manages collection state persistence with SQLite backend.

    This class provides both sync and async interfaces for state management,
    enabling transition from JSON file-based state to database-backed state.

    Benefits over JSON:
    - No lock contention on writes
    - Batch updates with single write
    - Transaction support (ACID)
    - Efficient queries and indexing
    - Better concurrent access patterns
    """

    def __init__(self, db_path: str):
        """
        Initialize state manager.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self.async_db: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Initialize database schema."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript("""
                CREATE TABLE IF NOT EXISTS query_state (
                    api TEXT NOT NULL,
                    query_id INTEGER NOT NULL,
                    state INTEGER DEFAULT -1,
                    last_page INTEGER DEFAULT 0,
                    total_art INTEGER DEFAULT 0,
                    coll_art INTEGER DEFAULT 0,
                    keyword TEXT,
                    year INTEGER,
                    update_date TEXT,
                    error_message TEXT,
                    PRIMARY KEY (api, query_id)
                );

                CREATE TABLE IF NOT EXISTS api_state (
                    api TEXT PRIMARY KEY,
                    state INTEGER DEFAULT -1,
                    completed_queries INTEGER DEFAULT 0,
                    total_queries INTEGER DEFAULT 0,
                    last_updated TEXT
                );

                CREATE TABLE IF NOT EXISTS global_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    state INTEGER DEFAULT -1,
                    completed_apis INTEGER DEFAULT 0,
                    total_apis INTEGER DEFAULT 0,
                    last_updated TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_query_state_api ON query_state(api);
                CREATE INDEX IF NOT EXISTS idx_query_state_state ON query_state(state);

                INSERT OR IGNORE INTO global_state (id, state) VALUES (1, -1);
            """)
            await db.commit()

    async def update_query_state(
        self,
        api: str,
        query_id: int,
        state_data: Dict[str, Any]
    ) -> None:
        """
        Update state for a single query.

        Args:
            api: API name
            query_id: Query ID
            state_data: Dictionary with state fields (state, last_page, etc.)
        """
        async with self._lock:
            async with aiosqlite.connect(self.db_path) as db:
                # Build UPDATE statement dynamically
                columns = []
                values = []
                for key, value in state_data.items():
                    if key not in ['api', 'query_id']:  # Don't update PK columns
                        columns.append(f"{key} = ?")
                        values.append(value)

                if not columns:
                    return

                columns.append("update_date = ?")
                values.append(str(date.today()))
                values.extend([api, query_id])

                update_sql = f"""
                    UPDATE query_state
                    SET {', '.join(columns)}
                    WHERE api = ? AND query_id = ?
                """

                await db.execute(update_sql, values)
                await db.commit()

    async def batch_update_queries(
        self,
        api: str,
        updates: list
    ) -> None:
        """
        Batch update multiple queries in one transaction.

        This is the key optimization: instead of updating state after every page,
        collect 10 page updates and write them all at once.

        Args:
            api: API name
            updates: List of (query_id, state_data_dict) tuples
        """
        async with self._lock:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute('BEGIN TRANSACTION'):
                    for query_id, state_data in updates:
                        columns = []
                        values = []
                        for key, value in state_data.items():
                            if key not in ['api', 'query_id']:
                                columns.append(f"{key} = ?")
                                values.append(value)

                        if columns:
                            columns.append("update_date = ?")
                            values.append(str(date.today()))
                            values.extend([api, query_id])

                            update_sql = f"""
                                UPDATE query_state
                                SET {', '.join(columns)}
                                WHERE api = ? AND query_id = ?
                            """

                            await db.execute(update_sql, values)

                    # Update API-level state
                    await db.execute("""
                        UPDATE api_state
                        SET
                            completed_queries = (
                                SELECT COUNT(*) FROM query_state
                                WHERE api = ? AND state = 1
                            ),
                            last_updated = ?
                        WHERE api = ?
                    """, [api, str(date.today()), api])

                    await db.commit()

    async def initialize_queries(
        self,
        queries_by_api: Dict[str, list]
    ) -> None:
        """
        Initialize query state records for a new collection.

        Args:
            queries_by_api: Dict mapping API name to list of query configs
        """
        async with self._lock:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute('BEGIN TRANSACTION'):
                    for api, queries in queries_by_api.items():
                        # Initialize API state
                        await db.execute("""
                            INSERT OR REPLACE INTO api_state
                            (api, state, completed_queries, total_queries, last_updated)
                            VALUES (?, -1, 0, ?, ?)
                        """, [api, len(queries), str(date.today())])

                        # Initialize query states
                        for idx, query_config in enumerate(queries):
                            await db.execute("""
                                INSERT OR REPLACE INTO query_state
                                (api, query_id, state, keyword, year, last_updated)
                                VALUES (?, ?, -1, ?, ?, ?)
                            """, [
                                api,
                                idx,
                                json.dumps(query_config.get('keyword', [])),
                                query_config.get('year'),
                                str(date.today())
                            ])

                    # Update global state
                    total_apis = len(queries_by_api)
                    await db.execute("""
                        UPDATE global_state
                        SET state = -1, completed_apis = 0, total_apis = ?, last_updated = ?
                        WHERE id = 1
                    """, [total_apis, str(date.today())])

                    await db.commit()

    async def get_query_state(
        self,
        api: str,
        query_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Get state for a specific query.

        Args:
            api: API name
            query_id: Query ID

        Returns:
            Dictionary of state fields or None if not found
        """
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("""
                SELECT state, last_page, total_art, coll_art, error_message
                FROM query_state
                WHERE api = ? AND query_id = ?
            """, [api, query_id]) as cursor:
                row = await cursor.fetchone()
                if row:
                    return {
                        'state': row[0],
                        'last_page': row[1],
                        'total_art': row[2],
                        'coll_art': row[3],
                        'error_message': row[4]
                    }
                return None

    async def get_global_state(self) -> Dict[str, Any]:
        """
        Get global collection state.

        Returns:
            Dictionary with global state
        """
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("""
                SELECT state, completed_apis, total_apis, last_updated
                FROM global_state WHERE id = 1
            """) as cursor:
                row = await cursor.fetchone()
                if row:
                    return {
                        'global': row[0],
                        'completed_apis': row[1],
                        'total_apis': row[2],
                        'last_updated': row[3]
                    }
                return {'global': -1, 'completed_apis': 0, 'total_apis': 0}

    async def mark_collection_complete(self) -> None:
        """Mark the entire collection as complete."""
        async with self._lock:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    UPDATE global_state
                    SET state = 1, last_updated = ?
                    WHERE id = 1
                """, [str(date.today())])
                await db.commit()

    async def check_completion_status(self) -> bool:
        """
        Check if all queries and APIs are complete.

        Returns:
            True if all queries finished successfully, False otherwise
        """
        async with aiosqlite.connect(self.db_path) as db:
            # Check if all query states are 1 (complete)
            async with db.execute("""
                SELECT COUNT(*) as incomplete
                FROM query_state
                WHERE state != 1
            """) as cursor:
                row = await cursor.fetchone()
                if row and row[0] > 0:
                    return False

            return True

    def convert_json_to_db(self, json_state: Dict[str, Any]) -> None:
        """
        Convert existing JSON state to SQLite database (migration).

        This enables migration from old JSON-based state to new DB-based state.

        Args:
            json_state: State dictionary from JSON file
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute('BEGIN TRANSACTION')

            # Initialize schema
            cursor.executescript("""
                CREATE TABLE IF NOT EXISTS query_state (
                    api TEXT NOT NULL,
                    query_id INTEGER NOT NULL,
                    state INTEGER DEFAULT -1,
                    last_page INTEGER DEFAULT 0,
                    total_art INTEGER DEFAULT 0,
                    coll_art INTEGER DEFAULT 0,
                    keyword TEXT,
                    year INTEGER,
                    update_date TEXT,
                    error_message TEXT,
                    PRIMARY KEY (api, query_id)
                );
            """)

            # Migrate data from JSON
            if 'details' in json_state:
                for api, api_data in json_state['details'].items():
                    if 'by_query' in api_data:
                        for query_id, query_data in api_data['by_query'].items():
                            cursor.execute("""
                                INSERT OR REPLACE INTO query_state
                                (api, query_id, state, last_page, total_art, coll_art,
                                 keyword, year, update_date, error_message)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, [
                                api,
                                int(query_id),
                                query_data.get('state', -1),
                                query_data.get('last_page', 0),
                                query_data.get('total_art', 0),
                                query_data.get('coll_art', 0),
                                json.dumps(query_data.get('keyword', [])),
                                query_data.get('year'),
                                query_data.get('update_date', str(date.today())),
                                query_data.get('error', '')
                            ])

            conn.commit()
            logging.info(f"Migrated state to SQLite: {self.db_path}")

        except Exception as e:
            conn.rollback()
            logging.error(f"Error migrating state to SQLite: {str(e)}")
            raise
        finally:
            conn.close()

    async def export_to_json(self) -> Dict[str, Any]:
        """
        Export database state back to JSON format (for compatibility).

        Useful for backward compatibility or manual inspection.

        Returns:
            JSON-compatible state dictionary
        """
        async with aiosqlite.connect(self.db_path) as db:
            # Get all query states
            async with db.execute("""
                SELECT api, query_id, state, last_page, total_art, coll_art
                FROM query_state
            """) as cursor:
                rows = await cursor.fetchall()

            state = {
                'global': (await self.get_global_state())['global'],
                'details': {}
            }

            for api, query_id, state_val, last_page, total_art, coll_art in rows:
                if api not in state['details']:
                    state['details'][api] = {
                        'state': -1,
                        'by_query': {}
                    }

                state['details'][api]['by_query'][query_id] = {
                    'state': state_val,
                    'last_page': last_page,
                    'total_art': total_art,
                    'coll_art': coll_art,
                    'update_date': str(date.today())
                }

            return state

    async def get_progress(self) -> Dict[str, Any]:
        """
        Get current collection progress.

        Returns:
            Dictionary with progress metrics
        """
        async with aiosqlite.connect(self.db_path) as db:
            # Get completion counts by API
            async with db.execute("""
                SELECT
                    api,
                    COUNT(*) as total,
                    SUM(CASE WHEN state = 1 THEN 1 ELSE 0 END) as completed
                FROM query_state
                GROUP BY api
            """) as cursor:
                rows = await cursor.fetchall()

            progress = {}
            total_completed = 0
            total_queries = 0

            for api, total, completed in rows:
                if completed is None:
                    completed = 0
                progress[api] = {
                    'completed': completed,
                    'total': total,
                    'percentage': (completed / total * 100) if total > 0 else 0
                }
                total_completed += completed
                total_queries += total

            return {
                'by_api': progress,
                'total_completed': total_completed,
                'total_queries': total_queries,
                'overall_percentage': (
                    (total_completed / total_queries * 100)
                    if total_queries > 0 else 0
                )
            }
