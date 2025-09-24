"""
Level114 Subnet - Server Report Schema

Pydantic models for parsing and validating collector server reports.
Provides strong typing and safe defaults for handling partial data.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, validator
from datetime import datetime
import json

from .constants import REQUIRED_PLUGINS


class MemoryInfo(BaseModel):
    """Memory information from server reports"""
    free_bytes: int = Field(default=0, ge=0)
    used_bytes: int = Field(default=0, ge=0) 
    total_bytes: int = Field(default=0, ge=0)
    
    @validator('total_bytes')
    def validate_total_bytes(cls, v, values):
        """Ensure total >= used + free (within reasonable tolerance)"""
        if 'used_bytes' in values and 'free_bytes' in values:
            expected_total = values['used_bytes'] + values['free_bytes']
            # Allow 5% tolerance for measurement differences
            if expected_total > 0 and abs(v - expected_total) / expected_total > 0.05:
                # Use the computed total if the provided one seems wrong
                return expected_total
        return max(v, 0)
    
    @property
    def usage_ratio(self) -> float:
        """Memory usage ratio [0.0-1.0]"""
        if self.total_bytes <= 0:
            return 0.0
        return min(self.used_bytes / self.total_bytes, 1.0)
    
    @property
    def free_ratio(self) -> float:
        """Memory free ratio [0.0-1.0]"""
        if self.total_bytes <= 0:
            return 0.0
        return min(self.free_bytes / self.total_bytes, 1.0)
    
    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> 'MemoryInfo':
        """Safely create from dictionary with defaults"""
        if not data:
            return cls()
        
        return cls(
            free_bytes=data.get('free_memory_bytes', 0),
            used_bytes=data.get('used_memory_bytes', 0),
            total_bytes=data.get('total_memory_bytes', 0)
        )


class SystemInfo(BaseModel):
    """System information from server reports"""
    cpu_cores: int = Field(default=1, ge=1, le=256)
    cpu_threads: int = Field(default=1, ge=1, le=512)
    cpu_model: str = Field(default="Unknown CPU")
    java_version: str = Field(default="Unknown")
    os_name: str = Field(default="Unknown")
    os_version: str = Field(default="Unknown") 
    os_arch: str = Field(default="Unknown")
    uptime_ms: int = Field(default=0, ge=0)
    memory_ram_info: MemoryInfo = Field(default_factory=MemoryInfo)
    
    @validator('uptime_ms')
    def validate_uptime(cls, v):
        """Ensure uptime is reasonable (max ~100 years)"""
        max_uptime = 100 * 365 * 24 * 60 * 60 * 1000  # 100 years in ms
        return min(v, max_uptime)
    
    @property
    def uptime_hours(self) -> float:
        """Uptime in hours"""
        return self.uptime_ms / (1000 * 60 * 60)
    
    @property
    def uptime_days(self) -> float:
        """Uptime in days"""
        return self.uptime_hours / 24
    
    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> 'SystemInfo':
        """Safely create from dictionary with defaults"""
        if not data:
            return cls()
        
        return cls(
            cpu_cores=data.get('cpu_cores', 1),
            cpu_threads=data.get('cpu_threads', 1),
            cpu_model=data.get('cpu_model', 'Unknown CPU'),
            java_version=data.get('java_version', 'Unknown'),
            os_name=data.get('os_name', 'Unknown'),
            os_version=data.get('os_version', 'Unknown'),
            os_arch=data.get('os_arch', 'Unknown'),
            uptime_ms=data.get('uptime_ms', 0),
            memory_ram_info=MemoryInfo.from_dict(data.get('memory_ram_info'))
        )


class ActivePlayer(BaseModel):
    """Active player information"""
    name: str = Field(default="Unknown")
    uuid: str = Field(default="00000000-0000-0000-0000-000000000000")
    
    @validator('uuid')
    def validate_uuid(cls, v):
        """Basic UUID format validation"""
        if len(v) != 36 or v.count('-') != 4:
            return "00000000-0000-0000-0000-000000000000"
        return v
    
    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> 'ActivePlayer':
        """Safely create from dictionary with defaults"""
        if not data:
            return cls()
        
        return cls(
            name=str(data.get('name', 'Unknown')),
            uuid=str(data.get('uuid', '00000000-0000-0000-0000-000000000000'))
        )


class Payload(BaseModel):
    """Server report payload data"""
    active_players: List[ActivePlayer] = Field(default_factory=list)
    max_players: int = Field(default=20, ge=1, le=50000)
    memory_ram_info: MemoryInfo = Field(default_factory=MemoryInfo)
    plugins: List[str] = Field(default_factory=list)
    system_info: SystemInfo = Field(default_factory=SystemInfo)
    tps_millis: int = Field(default=50, ge=0, le=25000)  # TPS in milliseconds
    uptime_ms: int = Field(default=0, ge=0)
    
    @validator('tps_millis')
    def validate_tps(cls, v):
        """Validate TPS is in reasonable range"""
        if v < 0 or v > 25000:  # 0-0.04 TPS range
            return 50  # Default to 20 TPS
        return v
    
    @validator('active_players', pre=True)
    def parse_active_players(cls, v):
        """Parse active players from various formats"""
        if not v:
            return []
        
        players = []
        for player_data in v:
            if isinstance(player_data, str):
                # Handle simple string format
                players.append(ActivePlayer(name=player_data))
            elif isinstance(player_data, dict):
                # Handle dict format
                players.append(ActivePlayer.from_dict(player_data))
        
        return players
    
    @validator('plugins', pre=True)
    def parse_plugins(cls, v):
        """Ensure plugins is a list of strings"""
        if not v:
            return []
        if isinstance(v, str):
            return [v]
        return [str(plugin) for plugin in v if plugin]
    
    @property
    def tps_actual(self) -> float:
        """Convert TPS from millis format to actual TPS value"""
        if self.tps_millis <= 0:
            return 0.0
        # TPS = tps_millis / 1000 (since tps_millis is TPS × 1000 fixed-point format)
        return min(self.tps_millis / 1000.0, 20.0)  # Cap at 20 TPS
    
    @property
    def player_count(self) -> int:
        """Number of active players"""
        return len(self.active_players)
    
    @property
    def player_ratio(self) -> float:
        """Player occupancy ratio [0.0-1.0]"""
        if self.max_players <= 0:
            return 0.0
        return min(self.player_count / self.max_players, 1.0)
    
    @property
    def has_required_plugins(self) -> bool:
        """Check if required plugins are present"""
        if not REQUIRED_PLUGINS:
            return True

        plugin_set = {
            plugin.strip().lower()
            for plugin in self.plugins
            if isinstance(plugin, str) and plugin.strip()
        }
        required = {plugin.strip().lower() for plugin in REQUIRED_PLUGINS if plugin}
        return required.issubset(plugin_set)
    
    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> 'Payload':
        """Safely create from dictionary with defaults"""
        if not data:
            return cls()
        
        return cls(
            active_players=data.get('active_players', []),
            max_players=data.get('max_players', 20),
            memory_ram_info=MemoryInfo.from_dict(data.get('memory_ram_info')),
            plugins=data.get('plugins', []),
            system_info=SystemInfo.from_dict(data.get('system_info')),
            tps_millis=data.get('tps_millis', 50),
            uptime_ms=data.get('uptime_ms', 0)
        )


class ServerReport(BaseModel):
    """Complete server report from collector"""
    id: str = Field(default="")
    server_id: str = Field(default="")
    counter: int = Field(default=0, ge=0)
    client_timestamp_ms: int = Field(default=0, ge=0)
    nonce: str = Field(default="")
    plugin_hash: str = Field(default="")
    payload_hash: str = Field(default="")
    payload: Payload = Field(default_factory=Payload)
    signature: str = Field(default="")
    created_at: str = Field(default="")
    
    @validator('client_timestamp_ms')
    def validate_timestamp(cls, v):
        """Ensure timestamp is reasonable (not too far in future/past)"""
        import time
        current_ms = int(time.time() * 1000)
        max_drift = 24 * 60 * 60 * 1000  # 24 hours
        
        # If timestamp is wildly off, use current time
        if abs(v - current_ms) > max_drift:
            return current_ms
        return v
    
    @validator('created_at')
    def validate_created_at(cls, v):
        """Ensure created_at is valid ISO format or provide default"""
        if not v:
            return datetime.now().isoformat() + 'Z'
        
        # Try to parse the datetime to validate format
        try:
            datetime.fromisoformat(v.replace('Z', '+00:00'))
            return v
        except (ValueError, AttributeError):
            return datetime.now().isoformat() + 'Z'
    
    @property
    def age_seconds(self) -> float:
        """Age of the report in seconds"""
        try:
            import time
            current_ms = int(time.time() * 1000)
            return (current_ms - self.client_timestamp_ms) / 1000.0
        except:
            return 0.0
    
    @property
    def is_fresh(self) -> bool:
        """Check if report is fresh (< 5 minutes old)"""
        return self.age_seconds < 300
    
    def to_canonical_dict(self) -> Dict[str, Any]:
        """Convert to canonical dict format for hash computation"""
        payload_dict = self.payload.model_dump()
        
        # Ensure deterministic ordering and format
        return {
            'active_players': sorted([
                {'name': p.name, 'uuid': p.uuid} 
                for p in self.payload.active_players
            ], key=lambda x: x['uuid']),
            'max_players': payload_dict['max_players'],
            'memory_ram_info': payload_dict['memory_ram_info'],
            'plugins': sorted(payload_dict['plugins']),
            'system_info': payload_dict['system_info'],
            'tps_millis': payload_dict['tps_millis'],
            'uptime_ms': payload_dict['uptime_ms']
        }
    
    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> 'ServerReport':
        """Safely create from dictionary with defaults"""
        if not data:
            return cls()
        
        return cls(
            id=str(data.get('id', '')),
            server_id=str(data.get('server_id', '')),
            counter=data.get('counter', 0),
            client_timestamp_ms=data.get('client_timestamp_ms', 0),
            nonce=str(data.get('nonce', '')),
            plugin_hash=str(data.get('plugin_hash', '')),
            payload_hash=str(data.get('payload_hash', '')),
            payload=Payload.from_dict(data.get('payload')),
            signature=str(data.get('signature', '')),
            created_at=str(data.get('created_at', ''))
        )
    
    @classmethod
    def from_json(cls, json_str: str) -> 'ServerReport':
        """Create from JSON string with error handling"""
        try:
            data = json.loads(json_str)
            return cls.from_dict(data)
        except (json.JSONDecodeError, Exception) as e:
            # Return default report on parse error
            return cls()