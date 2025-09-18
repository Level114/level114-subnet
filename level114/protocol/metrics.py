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
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any


class MetricsProtocol(bt.Synapse):
    """
    A protocol for requesting metrics from Level114 miners.
    
    This protocol allows validators to query miners for their performance metrics
    which are also reported to the collector-center-main service.
    
    Attributes:
    - miner_uid: The UID of the miner being queried
    - timestamp: When the request was made
    - cpu_usage: CPU usage percentage reported by the miner
    - memory_usage: Memory usage percentage reported by the miner
    - disk_usage: Disk usage percentage reported by the miner
    - network_latency: Network latency in ms reported by the miner
    - uptime: Uptime in seconds reported by the miner
    - tasks_completed: Number of tasks completed by the miner
    - error_rate: Error rate percentage reported by the miner
    - custom_metrics: Additional custom metrics from the miner
    - metrics_accepted: Whether the metrics request was successfully processed
    - next_report_time: When the next metrics report should be made
    """

    # Request fields - sent by validator to miner
    miner_uid: int = Field(
        description="UID of the miner in the subnet"
    )
    timestamp: float = Field(
        default_factory=time.time,
        description="Timestamp of the metrics request"
    )

    # Response fields - filled by miner
    cpu_usage: Optional[float] = Field(
        default=None,
        description="CPU usage percentage"
    )
    memory_usage: Optional[float] = Field(
        default=None,
        description="Memory usage percentage"
    )
    disk_usage: Optional[float] = Field(
        default=None,
        description="Disk usage percentage"
    )
    network_latency: Optional[float] = Field(
        default=None,
        description="Network latency in milliseconds"
    )
    uptime: Optional[float] = Field(
        default=None,
        description="Uptime in seconds"
    )
    tasks_completed: Optional[int] = Field(
        default=None,
        description="Number of tasks completed"
    )
    error_rate: Optional[float] = Field(
        default=None,
        description="Error rate percentage"
    )
    custom_metrics: Dict[str, Any] = Field(
        default_factory=dict,
        description="Custom performance metrics"
    )

    # Control fields
    metrics_accepted: bool = Field(
        default=False,
        description="Whether metrics were successfully processed"
    )
    next_report_time: Optional[float] = Field(
        default=None,
        description="Next expected report time"
    )

    def deserialize(self) -> Dict[str, Any]:
        """
        Returns the response of the protocol.
        
        Returns:
            Dict containing all the metrics data returned by the miner.
        """
        return {
            "miner_uid": self.miner_uid,
            "timestamp": self.timestamp,
            "cpu_usage": self.cpu_usage,
            "memory_usage": self.memory_usage,
            "disk_usage": self.disk_usage,
            "network_latency": self.network_latency,
            "uptime": self.uptime,
            "tasks_completed": self.tasks_completed,
            "error_rate": self.error_rate,
            "custom_metrics": self.custom_metrics,
            "metrics_accepted": self.metrics_accepted,
            "next_report_time": self.next_report_time,
        }


class HealthCheck(bt.Synapse):
    """
    A simple health check protocol for monitoring miner availability.
    """

    # Request fields
    check_timestamp: float = Field(
        default_factory=time.time,
        description="Timestamp of health check"
    )

    # Response fields
    is_healthy: bool = Field(
        default=False,
        description="Whether the miner is healthy"
    )
    uptime: Optional[float] = Field(
        default=None,
        description="Miner uptime in seconds"
    )
    version: Optional[str] = Field(
        default=None,
        description="Miner software version"
    )

    def deserialize(self) -> Dict[str, Any]:
        """
        Returns the response of the protocol.
        
        Returns:
            Dict containing the health check response.
        """
        return {
            "is_healthy": self.is_healthy,
            "uptime": self.uptime,
            "version": self.version,
            "check_timestamp": self.check_timestamp,
        }
