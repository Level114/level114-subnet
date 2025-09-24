"""
Level114 Subnet - Validator Storage

SQLite-based persistence for server reports, scoring history, and miner data.
Provides efficient storage and retrieval for the validator scoring system.
"""

import sqlite3
import json
import time
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from collections import deque
from contextlib import contextmanager

from .scoring.report_schema import ServerReport
from .scoring.constants import MAX_REPORT_HISTORY, DEBUG_SCORING


class ValidatorStorage:
    """
    SQLite-based storage for validator data
    """
    
    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize validator storage
        
        Args:
            db_path: Path to SQLite database file
        """
        if db_path is None:
            # Default to ~/.level114/validator.db
            home_dir = Path.home() / ".level114"
            home_dir.mkdir(exist_ok=True)
            db_path = str(home_dir / "validator.db")
        
        self.db_path = db_path
        self._init_database()
    
    def _init_database(self):
        """Initialize database schema"""
        with self._get_connection() as conn:
            # Table for historical reports by server
            conn.execute("""
                CREATE TABLE IF NOT EXISTS reports_by_server (
                    server_id TEXT NOT NULL,
                    ts INTEGER NOT NULL,
                    tps REAL NOT NULL,
                    uptime_ms INTEGER NOT NULL,
                    players INTEGER NOT NULL,
                    latency REAL NOT NULL,
                    comp INTEGER NOT NULL,
                    report_json TEXT NOT NULL,
                    PRIMARY KEY (server_id, ts)
                )
            """)
            
            # Table for miner scores  
            conn.execute("""
                CREATE TABLE IF NOT EXISTS miner_scores (
                    server_id TEXT PRIMARY KEY,
                    score INTEGER NOT NULL,
                    infra REAL NOT NULL,
                    part REAL NOT NULL,
                    rely REAL NOT NULL,
                    updated_at INTEGER NOT NULL
                )
            """)
            
            # Table for server registration mapping
            conn.execute("""
                CREATE TABLE IF NOT EXISTS server_registry (
                    server_id TEXT PRIMARY KEY,
                    hotkey TEXT NOT NULL,
                    registered_at INTEGER NOT NULL,
                    last_seen INTEGER NOT NULL,
                    status TEXT DEFAULT 'active'
                )
            """)
            
            # Indexes for performance
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_reports_server_ts 
                ON reports_by_server(server_id, ts DESC)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_reports_ts 
                ON reports_by_server(ts DESC)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_registry_hotkey
                ON server_registry(hotkey)
            """)
            
            conn.commit()
    
    @contextmanager
    def _get_connection(self):
        """Get database connection with proper cleanup"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Enable column access by name
        try:
            yield conn
        finally:
            conn.close()
    
    def append_report(
        self,
        server_id: str,
        report: ServerReport,
        latency: float = 0.0,
        compliance: bool = True
    ):
        """
        Store a new server report
        
        Args:
            server_id: Server identifier
            report: Server report to store
            latency: HTTP latency for this report
            compliance: Whether report passed integrity checks
        """
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO reports_by_server
                    (server_id, ts, tps, uptime_ms, players, latency, comp, report_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    server_id,
                    report.client_timestamp_ms,
                    report.payload.tps_actual,
                    report.payload.system_info.uptime_ms,
                    report.payload.player_count,
                    latency,
                    1 if compliance else 0,
                    report.model_dump_json()
                ))
                
                # Update last seen for this server
                conn.execute("""
                    UPDATE server_registry 
                    SET last_seen = ?
                    WHERE server_id = ?
                """, (report.client_timestamp_ms, server_id))
                
                conn.commit()
                
                if DEBUG_SCORING:
                    print(f"Stored report for server {server_id}")
                    
        except Exception as e:
            if DEBUG_SCORING:
                print(f"Error storing report: {e}")
    
    def load_history(
        self,
        server_id: str,
        max_rows: int = MAX_REPORT_HISTORY
    ) -> deque:
        """
        Load recent report history for a server
        
        Args:
            server_id: Server to load history for
            max_rows: Maximum number of reports to load
            
        Returns:
            Deque of ServerReport objects
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.execute("""
                    SELECT report_json FROM reports_by_server
                    WHERE server_id = ?
                    ORDER BY ts DESC
                    LIMIT ?
                """, (server_id, max_rows))
                
                # Load reports and reverse to chronological order
                reports = []
                for row in cursor.fetchall():
                    try:
                        report_data = json.loads(row['report_json'])
                        report = ServerReport.from_dict(report_data)
                        reports.append(report)
                    except Exception as e:
                        if DEBUG_SCORING:
                            print(f"Error parsing stored report: {e}")
                        continue
                
                # Reverse to get chronological order (oldest first)
                reports.reverse()
                
                return deque(reports, maxlen=MAX_REPORT_HISTORY)
                
        except Exception as e:
            if DEBUG_SCORING:
                print(f"Error loading history: {e}")
            return deque(maxlen=MAX_REPORT_HISTORY)
    
    def upsert_score(
        self,
        server_id: str,
        score: int,
        infra: float,
        part: float,
        rely: float
    ):
        """
        Store or update miner score
        
        Args:
            server_id: Server identifier
            score: Final normalized score
            infra: Infrastructure component score
            part: Participation component score
            rely: Reliability component score
        """
        try:
            current_time = int(time.time() * 1000)
            
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO miner_scores
                    (server_id, score, infra, part, rely, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (server_id, score, infra, part, rely, current_time))
                
                conn.commit()
                
                if DEBUG_SCORING:
                    print(f"Updated score for server {server_id}: {score}")
                    
        except Exception as e:
            if DEBUG_SCORING:
                print(f"Error storing score: {e}")
    
    def get_score(self, server_id: str) -> Optional[Dict[str, Any]]:
        """
        Get stored score for a server
        
        Args:
            server_id: Server to get score for
            
        Returns:
            Dictionary with score data or None
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.execute("""
                    SELECT * FROM miner_scores
                    WHERE server_id = ?
                """, (server_id,))
                
                row = cursor.fetchone()
                if row:
                    return {
                        'server_id': row['server_id'],
                        'score': row['score'],
                        'infra': row['infra'],
                        'part': row['part'],
                        'rely': row['rely'],
                        'updated_at': row['updated_at']
                    }
                
                return None
                
        except Exception as e:
            if DEBUG_SCORING:
                print(f"Error getting score: {e}")
            return None
    
    def get_all_scores(self) -> List[Dict[str, Any]]:
        """
        Get all stored server scores
        
        Returns:
            List of score dictionaries
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.execute("""
                    SELECT * FROM miner_scores
                    ORDER BY score DESC
                """)
                
                scores = []
                for row in cursor.fetchall():
                    scores.append({
                        'server_id': row['server_id'],
                        'score': row['score'],
                        'infra': row['infra'],
                        'part': row['part'],
                        'rely': row['rely'],
                        'updated_at': row['updated_at']
                    })
                
                return scores
                
        except Exception as e:
            if DEBUG_SCORING:
                print(f"Error getting all scores: {e}")
            return []
    
    def register_server(
        self,
        server_id: str,
        hotkey: str,
        registered_at: Optional[int] = None
    ):
        """
        Register a server with its hotkey mapping
        
        Args:
            server_id: Server identifier
            hotkey: Associated Bittensor hotkey
            registered_at: Registration timestamp (defaults to now)
        """
        try:
            if registered_at is None:
                registered_at = int(time.time() * 1000)
            
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO server_registry
                    (server_id, hotkey, registered_at, last_seen, status)
                    VALUES (?, ?, ?, ?, 'active')
                """, (server_id, hotkey, registered_at, registered_at))
                
                conn.commit()
                
                if DEBUG_SCORING:
                    print(f"Registered server {server_id} with hotkey {hotkey}")
                    
        except Exception as e:
            if DEBUG_SCORING:
                print(f"Error registering server: {e}")
    
    def get_server_hotkey(self, server_id: str) -> Optional[str]:
        """
        Get hotkey for a server
        
        Args:
            server_id: Server to look up
            
        Returns:
            Hotkey string or None
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.execute("""
                    SELECT hotkey FROM server_registry
                    WHERE server_id = ?
                """, (server_id,))
                
                row = cursor.fetchone()
                return row['hotkey'] if row else None
                
        except Exception as e:
            if DEBUG_SCORING:
                print(f"Error getting hotkey: {e}")
            return None
    
    def get_hotkey_server(self, hotkey: str, active_only: bool = True) -> Optional[str]:
        """
        Get server ID for a hotkey
        
        Args:
            hotkey: Hotkey to look up
            
        Returns:
            Server ID string or None
        """
        try:
            query = """
                SELECT server_id FROM server_registry
                WHERE hotkey = ?
            """
            params = [hotkey]

            if active_only:
                query += " AND status = 'active'"

            with self._get_connection() as conn:
                cursor = conn.execute(query, params)

                row = cursor.fetchone()
                return row['server_id'] if row else None

        except Exception as e:
            if DEBUG_SCORING:
                print(f"Error getting server ID: {e}")
            return None

    def deactivate_server(self, server_id: str, status: str = 'inactive') -> None:
        """Mark a server as inactive/missing in the registry"""
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    UPDATE server_registry
                    SET status = ?, last_seen = last_seen
                    WHERE server_id = ?
                """, (status, server_id))

                conn.commit()

                if DEBUG_SCORING:
                    print(f"Deactivated server {server_id} with status {status}")

        except Exception as e:
            if DEBUG_SCORING:
                print(f"Error deactivating server: {e}")
    
    def is_server_registered(self, server_id: str) -> bool:
        """
        Check if server is registered
        
        Args:
            server_id: Server to check
            
        Returns:
            True if registered
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.execute("""
                    SELECT 1 FROM server_registry
                    WHERE server_id = ? AND status = 'active'
                """, (server_id,))
                
                return cursor.fetchone() is not None
                
        except Exception as e:
            if DEBUG_SCORING:
                print(f"Error checking registration: {e}")
            return False
    
    def get_server_stats(self, server_id: str) -> Dict[str, Any]:
        """
        Get comprehensive stats for a server
        
        Args:
            server_id: Server to analyze
            
        Returns:
            Dictionary with server statistics
        """
        try:
            with self._get_connection() as conn:
                # Report statistics
                cursor = conn.execute("""
                    SELECT 
                        COUNT(*) as total_reports,
                        MIN(ts) as first_report,
                        MAX(ts) as last_report,
                        AVG(tps) as avg_tps,
                        AVG(players) as avg_players,
                        AVG(latency) as avg_latency,
                        SUM(comp) as compliance_count
                    FROM reports_by_server
                    WHERE server_id = ?
                """, (server_id,))
                
                report_stats = cursor.fetchone()
                
                # Registration info
                cursor = conn.execute("""
                    SELECT hotkey, registered_at, last_seen, status
                    FROM server_registry
                    WHERE server_id = ?
                """, (server_id,))
                
                reg_info = cursor.fetchone()
                
                # Score info
                cursor = conn.execute("""
                    SELECT score, infra, part, rely, updated_at
                    FROM miner_scores
                    WHERE server_id = ?
                """, (server_id,))
                
                score_info = cursor.fetchone()
                
                # Combine all stats
                stats = {
                    'server_id': server_id,
                    'total_reports': report_stats['total_reports'] if report_stats else 0,
                    'first_report': report_stats['first_report'] if report_stats else None,
                    'last_report': report_stats['last_report'] if report_stats else None,
                    'avg_tps': report_stats['avg_tps'] if report_stats else 0.0,
                    'avg_players': report_stats['avg_players'] if report_stats else 0.0,
                    'avg_latency': report_stats['avg_latency'] if report_stats else 0.0,
                    'compliance_rate': (
                        report_stats['compliance_count'] / report_stats['total_reports']
                        if report_stats and report_stats['total_reports'] > 0
                        else 0.0
                    ),
                    'hotkey': reg_info['hotkey'] if reg_info else None,
                    'registered_at': reg_info['registered_at'] if reg_info else None,
                    'last_seen': reg_info['last_seen'] if reg_info else None,
                    'status': reg_info['status'] if reg_info else 'unregistered',
                    'current_score': score_info['score'] if score_info else None,
                    'score_components': {
                        'infra': score_info['infra'] if score_info else 0.0,
                        'part': score_info['part'] if score_info else 0.0,
                        'rely': score_info['rely'] if score_info else 0.0
                    } if score_info else None,
                    'score_updated': score_info['updated_at'] if score_info else None
                }
                
                return stats
                
        except Exception as e:
            if DEBUG_SCORING:
                print(f"Error getting server stats: {e}")
            return {'server_id': server_id, 'error': str(e)}
    
    def cleanup_old_data(self, max_age_days: int = 30):
        """
        Clean up old data to prevent database bloat
        
        Args:
            max_age_days: Maximum age of data to keep
        """
        try:
            cutoff_ms = int((time.time() - max_age_days * 24 * 3600) * 1000)
            
            with self._get_connection() as conn:
                # Clean up old reports
                cursor = conn.execute("""
                    DELETE FROM reports_by_server
                    WHERE ts < ?
                """, (cutoff_ms,))
                
                reports_deleted = cursor.rowcount
                
                # Clean up inactive servers (no reports in cleanup period)
                conn.execute("""
                    UPDATE server_registry 
                    SET status = 'inactive'
                    WHERE last_seen < ? AND status = 'active'
                """, (cutoff_ms,))
                
                conn.commit()
                
                if DEBUG_SCORING and reports_deleted > 0:
                    print(f"Cleaned up {reports_deleted} old reports")
                    
        except Exception as e:
            if DEBUG_SCORING:
                print(f"Error during cleanup: {e}")
    
    def export_data(self, output_path: str):
        """
        Export all data to JSON file for backup
        
        Args:
            output_path: Path to write JSON export
        """
        try:
            with self._get_connection() as conn:
                # Export all tables
                data = {
                    'exported_at': int(time.time() * 1000),
                    'scores': [],
                    'registry': [],
                    'recent_reports': []
                }
                
                # Export scores
                for row in conn.execute("SELECT * FROM miner_scores"):
                    data['scores'].append(dict(row))
                
                # Export registry
                for row in conn.execute("SELECT * FROM server_registry"):
                    data['registry'].append(dict(row))
                
                # Export recent reports (last 24 hours)
                cutoff = int((time.time() - 24 * 3600) * 1000)
                for row in conn.execute("""
                    SELECT * FROM reports_by_server 
                    WHERE ts > ? 
                    ORDER BY ts DESC
                """, (cutoff,)):
                    data['recent_reports'].append(dict(row))
                
                # Write to file
                with open(output_path, 'w') as f:
                    json.dump(data, f, indent=2)
                
                if DEBUG_SCORING:
                    print(f"Exported data to {output_path}")
                    
        except Exception as e:
            if DEBUG_SCORING:
                print(f"Error exporting data: {e}")


# Global storage instance
_global_storage: Optional[ValidatorStorage] = None

def get_storage(db_path: Optional[str] = None) -> ValidatorStorage:
    """Get the global storage instance"""
    global _global_storage
    if _global_storage is None:
        _global_storage = ValidatorStorage(db_path)
    return _global_storage