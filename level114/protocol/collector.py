# The MIT License (MIT)
# Copyright © 2025 Level114 Team

# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
# documentation files (the "Software"), to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all copies or substantial portions of
# the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO
# THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.

import typing
import time
import bittensor as bt
from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any, List
from datetime import datetime
import re


class CollectorProtocol(bt.Synapse):
    """
    A protocol for communicating with the collector-center-main service.
    
    This protocol is used by miners to register themselves with the collector
    service and report their performance metrics.
    
    Attributes:
    - operation: The operation to perform ("register", "report_metrics", "health_check")
    - ip: Public IP address of the miner
    - port: Port number where miner is listening
    - hotkey: Hotkey address of the miner
    - signature: Signature proving ownership of hotkey
    - metrics: Performance metrics to report
    - server_id: Server ID assigned by collector
    - api_token: API token for authenticated requests
    - success: Whether the operation was successful
    - message: Additional message from the collector
    """

    # Request fields
    operation: str = Field(
        description="Operation to perform: 'register', 'report_metrics', 'health_check'"
    )
    ip: Optional[str] = Field(
        default=None,
        description="Public IP address of the miner"
    )
    port: Optional[int] = Field(
        default=None,
        description="Port number where miner is listening"
    )
    hotkey: Optional[str] = Field(
        default=None,
        description="Hotkey address of the miner"
    )
    signature: Optional[str] = Field(
        default=None,
        description="Signature proving ownership of hotkey"
    )
    metrics: Dict[str, Any] = Field(
        default_factory=dict,
        description="Performance metrics to report"
    )
    timestamp: float = Field(
        default_factory=time.time,
        description="Timestamp of the request"
    )

    # Response fields
    server_id: Optional[str] = Field(
        default=None,
        description="Server ID assigned by collector"
    )
    api_token: Optional[str] = Field(
        default=None,
        description="API token for authenticated requests"
    )
    key_id: Optional[str] = Field(
        default=None,
        description="Public key ID for cryptographic operations"
    )
    success: bool = Field(
        default=False,
        description="Whether the operation was successful"
    )
    message: Optional[str] = Field(
        default=None,
        description="Additional message from the collector"
    )
    next_report_time: Optional[float] = Field(
        default=None,
        description="When the next report should be made"
    )

    @validator('ip')
    def validate_ip(cls, v):
        """Validate IPv4 address format"""
        if v is None:
            return v
        import ipaddress
        try:
            addr = ipaddress.IPv4Address(v)
            if addr.is_loopback or addr.is_private:
                raise ValueError("IP must be a public, non-local IPv4 address")
            return str(addr)
        except ipaddress.AddressValueError:
            raise ValueError("Invalid IPv4 address format")

    @validator('port')
    def validate_port(cls, v):
        """Validate port range"""
        if v is None:
            return v
        if not (1 <= v <= 65535):
            raise ValueError("Port must be between 1 and 65535")
        return v

    @validator('hotkey')
    def validate_hotkey(cls, v):
        """Validate TAO address format"""
        if v is None:
            return v
        # Basic TAO address validation (SS58 format)
        if not re.match(r'^5[A-HJ-NP-Z1-9]+$', v):
            raise ValueError("Invalid TAO address format")
        return v

    @validator('signature')
    def validate_signature(cls, v):
        """Validate signature length"""
        if v is None:
            return v
        if len(v) != 128:
            raise ValueError("Signature must be 128 characters long")
        return v

    def deserialize(self) -> Dict[str, Any]:
        """
        Returns the response of the protocol.
        
        Returns:
            Dict containing the collector response data.
        """
        return {
            "operation": self.operation,
            "server_id": self.server_id,
            "api_token": self.api_token,
            "key_id": self.key_id,
            "success": self.success,
            "message": self.message,
            "next_report_time": self.next_report_time,
            "timestamp": self.timestamp,
        }


# Additional data models for collector communication

class ServerRegistrationRequest(BaseModel):
    """Request model for server registration with collector-center"""
    
    ip: str = Field(description="Public IPv4 address of the server")
    port: int = Field(description="Port number where server is listening", ge=1, le=65535)
    hotkey: str = Field(description="Hotkey address of the server")
    signature: str = Field(description="Signature proving ownership of hotkey", min_length=128, max_length=128)


class ServerRegistrationResponse(BaseModel):
    """Response model for server registration"""
    
    server_id: str = Field(description="Unique server ID")
    api_token: str = Field(description="API access token")
    key_id: Optional[str] = Field(default=None, description="Public key ID")
    created_at: datetime = Field(description="Server creation timestamp")


class MetricsReport(BaseModel):
    """Metrics report model for submission to collector"""
    
    server_id: str = Field(description="Server ID reporting metrics")
    timestamp: datetime = Field(description="Metrics timestamp")
    
    # Performance metrics
    cpu_usage: Optional[float] = Field(default=None, description="CPU usage percentage", ge=0, le=100)
    memory_usage: Optional[float] = Field(default=None, description="Memory usage percentage", ge=0, le=100)
    disk_usage: Optional[float] = Field(default=None, description="Disk usage percentage", ge=0, le=100)
    network_latency: Optional[float] = Field(default=None, description="Network latency in milliseconds", ge=0)
    uptime: Optional[float] = Field(default=None, description="Uptime in seconds", ge=0)
    
    # Application metrics
    tasks_completed: Optional[int] = Field(default=None, description="Number of tasks completed", ge=0)
    error_rate: Optional[float] = Field(default=None, description="Error rate percentage", ge=0, le=100)
    throughput: Optional[float] = Field(default=None, description="Throughput rate", ge=0)
    
    # Custom metrics
    custom_metrics: Dict[str, Any] = Field(default_factory=dict, description="Additional custom metrics")


class CollectorHealthResponse(BaseModel):
    """Health check response from collector"""
    
    status: str = Field(description="Health status")
    timestamp: datetime = Field(description="Health check timestamp")
    version: Optional[str] = Field(default=None, description="Collector version")
