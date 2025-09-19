"""
Level114 Subnet - Report Integrity Verification

Implements hash verification, signature verification, and replay protection
for server reports from the collector system.
"""

import json
import hashlib
import base64
import os
import sqlite3
import time
from typing import Optional, Dict, Any, Callable
from pathlib import Path

try:
    import nacl.signing
    import nacl.encoding
    HAS_NACL = True
except ImportError:
    HAS_NACL = False

from .report_schema import ServerReport

# Feature flags
ALLOW_UNSIGNED = os.getenv("LEVEL114_ALLOW_UNSIGNED", "true").lower() == "true"
DEBUG_INTEGRITY = os.getenv("LEVEL114_DEBUG_INTEGRITY", "false").lower() == "true"


def recompute_payload_hash(payload: Dict[str, Any]) -> str:
    """
    Recompute payload hash using canonical JSON representation
    
    Args:
        payload: Payload dictionary
        
    Returns:
        Base64url encoded SHA256 hash
    """
    try:
        # Create canonical JSON representation
        canonical_json = json.dumps(
            payload,
            sort_keys=True,
            separators=(',', ':'),
            ensure_ascii=True
        )
        
        # Compute SHA256 hash
        hash_bytes = hashlib.sha256(canonical_json.encode('utf-8')).digest()
        
        # Encode as base64url (URL-safe base64 without padding)
        hash_b64 = base64.urlsafe_b64encode(hash_bytes).decode('ascii').rstrip('=')
        
        if DEBUG_INTEGRITY:
            print(f"Canonical JSON: {canonical_json[:200]}...")
            print(f"Computed hash: {hash_b64}")
        
        return hash_b64
        
    except Exception as e:
        if DEBUG_INTEGRITY:
            print(f"Hash computation error: {e}")
        return ""


def verify_payload_hash(report: ServerReport) -> bool:
    """
    Verify that the payload hash matches the recomputed hash
    
    Args:
        report: Server report to verify
        
    Returns:
        True if hash is valid, False otherwise
    """
    try:
        # Get canonical payload dictionary
        canonical_payload = report.to_canonical_dict()
        
        # Recompute hash
        computed_hash = recompute_payload_hash(canonical_payload)
        
        # Compare hashes
        is_valid = computed_hash == report.payload_hash.rstrip('=')
        
        if DEBUG_INTEGRITY:
            print(f"Expected hash: {report.payload_hash}")
            print(f"Computed hash: {computed_hash}")
            print(f"Hash valid: {is_valid}")
        
        return is_valid
        
    except Exception as e:
        if DEBUG_INTEGRITY:
            print(f"Hash verification error: {e}")
        return False


def verify_signature(
    report: ServerReport,
    pubkey_resolver: Optional[Callable[[str], Optional[bytes]]] = None
) -> bool:
    """
    Verify Ed25519 signature of the report
    
    Args:
        report: Server report to verify
        pubkey_resolver: Function to resolve server_id to public key bytes
        
    Returns:
        True if signature is valid or ALLOW_UNSIGNED=True, False otherwise
    """
    if ALLOW_UNSIGNED:
        if DEBUG_INTEGRITY:
            print("Signature verification skipped (ALLOW_UNSIGNED=True)")
        return True
    
    if not HAS_NACL:
        if DEBUG_INTEGRITY:
            print("PyNaCl not available, signature verification disabled")
        return ALLOW_UNSIGNED
    
    if not pubkey_resolver:
        if DEBUG_INTEGRITY:
            print("No pubkey resolver provided")
        return ALLOW_UNSIGNED
    
    try:
        # Get public key for server
        pubkey_bytes = pubkey_resolver(report.server_id)
        if not pubkey_bytes:
            if DEBUG_INTEGRITY:
                print(f"No public key found for server {report.server_id}")
            return False
        
        # Create signing key object
        verify_key = nacl.signing.VerifyKey(pubkey_bytes)
        
        # Create message to verify (server_id + payload_hash + nonce + counter)
        message = f"{report.server_id}:{report.payload_hash}:{report.nonce}:{report.counter}"
        message_bytes = message.encode('utf-8')
        
        # Decode signature from base64url
        signature_bytes = base64.urlsafe_b64decode(
            report.signature + '=' * (4 - len(report.signature) % 4)
        )
        
        # Verify signature
        verify_key.verify(message_bytes, signature_bytes)
        
        if DEBUG_INTEGRITY:
            print(f"Signature verification successful for server {report.server_id}")
        
        return True
        
    except Exception as e:
        if DEBUG_INTEGRITY:
            print(f"Signature verification failed: {e}")
        return False


class ReplayProtection:
    """
    Replay protection using nonce and counter tracking
    
    Maintains a database of seen nonces and counters per server to prevent
    replay attacks and ensure monotonic counter progression.
    """
    
    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize replay protection
        
        Args:
            db_path: Path to SQLite database, defaults to ~/.level114/replay.db
        """
        if db_path is None:
            home_dir = Path.home() / ".level114"
            home_dir.mkdir(exist_ok=True)
            db_path = str(home_dir / "replay.db")
        
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Initialize the replay protection database"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS replay_protection (
                    server_id TEXT NOT NULL,
                    nonce TEXT NOT NULL,
                    counter INTEGER NOT NULL,
                    timestamp_ms INTEGER NOT NULL,
                    PRIMARY KEY (server_id, nonce)
                )
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_server_counter 
                ON replay_protection(server_id, counter)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp 
                ON replay_protection(timestamp_ms)
            """)
            
            conn.commit()
    
    def check_and_record(self, report: ServerReport) -> bool:
        """
        Check if report is valid (no replay) and record it
        
        Args:
            report: Server report to check
            
        Returns:
            True if report is valid and recorded, False if replay detected
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Check if nonce already exists for this server
                nonce_exists = conn.execute("""
                    SELECT 1 FROM replay_protection 
                    WHERE server_id = ? AND nonce = ?
                """, (report.server_id, report.nonce)).fetchone()
                
                if nonce_exists:
                    if DEBUG_INTEGRITY:
                        print(f"Replay detected: nonce {report.nonce} already seen for server {report.server_id}")
                    return False
                
                # Check if counter is greater than last seen counter
                last_counter = conn.execute("""
                    SELECT MAX(counter) FROM replay_protection 
                    WHERE server_id = ?
                """, (report.server_id,)).fetchone()[0]
                
                if last_counter is not None and report.counter <= last_counter:
                    if DEBUG_INTEGRITY:
                        print(f"Counter regression: {report.counter} <= {last_counter} for server {report.server_id}")
                    return False
                
                # Record this report
                conn.execute("""
                    INSERT INTO replay_protection 
                    (server_id, nonce, counter, timestamp_ms)
                    VALUES (?, ?, ?, ?)
                """, (
                    report.server_id,
                    report.nonce,
                    report.counter,
                    report.client_timestamp_ms
                ))
                
                conn.commit()
                
                if DEBUG_INTEGRITY:
                    print(f"Report recorded: server={report.server_id}, counter={report.counter}, nonce={report.nonce[:10]}...")
                
                return True
                
        except Exception as e:
            if DEBUG_INTEGRITY:
                print(f"Replay protection error: {e}")
            return False
    
    def cleanup_old_entries(self, max_age_hours: int = 168):  # 7 days default
        """
        Clean up old replay protection entries
        
        Args:
            max_age_hours: Maximum age of entries to keep in hours
        """
        try:
            cutoff_ms = int((time.time() - max_age_hours * 3600) * 1000)
            
            with sqlite3.connect(self.db_path) as conn:
                result = conn.execute("""
                    DELETE FROM replay_protection 
                    WHERE timestamp_ms < ?
                """, (cutoff_ms,))
                
                deleted_count = result.rowcount
                conn.commit()
                
                if DEBUG_INTEGRITY and deleted_count > 0:
                    print(f"Cleaned up {deleted_count} old replay protection entries")
                    
        except Exception as e:
            if DEBUG_INTEGRITY:
                print(f"Cleanup error: {e}")
    
    def get_server_stats(self, server_id: str) -> Dict[str, Any]:
        """
        Get statistics for a server
        
        Args:
            server_id: Server to get stats for
            
        Returns:
            Dictionary with server statistics
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                stats = conn.execute("""
                    SELECT 
                        COUNT(*) as total_reports,
                        MAX(counter) as max_counter,
                        MIN(timestamp_ms) as first_seen_ms,
                        MAX(timestamp_ms) as last_seen_ms
                    FROM replay_protection 
                    WHERE server_id = ?
                """, (server_id,)).fetchone()
                
                if stats and stats[0] > 0:
                    return {
                        'total_reports': stats[0],
                        'max_counter': stats[1],
                        'first_seen_ms': stats[2],
                        'last_seen_ms': stats[3],
                        'active_hours': (stats[3] - stats[2]) / (1000 * 3600) if stats[2] else 0
                    }
                else:
                    return {
                        'total_reports': 0,
                        'max_counter': 0,
                        'first_seen_ms': 0,
                        'last_seen_ms': 0,
                        'active_hours': 0
                    }
                    
        except Exception as e:
            if DEBUG_INTEGRITY:
                print(f"Stats error: {e}")
            return {}


def stub_pubkey_resolver(server_id: str) -> Optional[bytes]:
    """
    Stub public key resolver for testing
    
    Args:
        server_id: Server ID to resolve
        
    Returns:
        Dummy public key bytes or None
    """
    if ALLOW_UNSIGNED:
        return None
    
    # For testing, return a dummy 32-byte key
    return hashlib.sha256(server_id.encode()).digest()[:32]


def verify_report_integrity(
    report: ServerReport,
    replay_protection: Optional[ReplayProtection] = None,
    pubkey_resolver: Optional[Callable[[str], Optional[bytes]]] = None
) -> Dict[str, bool]:
    """
    Complete integrity verification for a server report
    
    Args:
        report: Server report to verify
        replay_protection: Replay protection instance
        pubkey_resolver: Public key resolver function
        
    Returns:
        Dictionary with verification results
    """
    results = {
        'hash_valid': False,
        'signature_valid': False,
        'replay_check_passed': False,
        'overall_valid': False
    }
    
    try:
        # Verify payload hash
        results['hash_valid'] = verify_payload_hash(report)
        
        # Verify signature
        results['signature_valid'] = verify_signature(report, pubkey_resolver or stub_pubkey_resolver)
        
        # Check for replay attacks
        if replay_protection:
            results['replay_check_passed'] = replay_protection.check_and_record(report)
        else:
            results['replay_check_passed'] = True  # No replay protection configured
        
        # Overall validity
        results['overall_valid'] = all([
            results['hash_valid'],
            results['signature_valid'],
            results['replay_check_passed']
        ])
        
        if DEBUG_INTEGRITY:
            print(f"Integrity check results: {results}")
        
        return results
        
    except Exception as e:
        if DEBUG_INTEGRITY:
            print(f"Integrity verification error: {e}")
        return results


# Global replay protection instance
_global_replay_protection: Optional[ReplayProtection] = None

def get_replay_protection() -> ReplayProtection:
    """Get the global replay protection instance"""
    global _global_replay_protection
    if _global_replay_protection is None:
        _global_replay_protection = ReplayProtection()
    return _global_replay_protection
