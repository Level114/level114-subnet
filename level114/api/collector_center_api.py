"""
Collector Center API client
"""

from typing import Optional, Dict, List, Tuple, Any
from level114.types import ValidatorServer
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import json
import bittensor as bt


class CollectorCenterAPI:
    """Simple client for interacting with Collector-Center service."""

    def __init__(self, base_url: str, timeout_seconds: Optional[float] = 10.0, api_key: Optional[str] = None, reports_limit_default: Optional[int] = 25):
        if not base_url or not str(base_url).strip():
            raise ValueError("Collector base_url is required. Provide it via --collector.url")
        self.base_url = base_url.rstrip("/") if base_url else ""

        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else 10.0

        if not api_key or not str(api_key).strip():
            raise ValueError("Collector API key is required. Provide it via --collector.api_key")
        self.api_key = str(api_key).strip()
        self.reports_limit_default = int(reports_limit_default) if reports_limit_default is not None else 25

    def default_headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
            }
        return headers

    def _fetch_validator_server_ids_chunk(
        self,
        hotkeys_chunk: List[str],
        timeout: float,
        chunk_index: int,
        total_chunks: int,
    ) -> Tuple[int, List[ValidatorServer]]:
        """Fetch validator ids for a subset of hotkeys."""
        if not hotkeys_chunk:
            return 400, []

        query = urlencode({"hotkeys": ",".join(hotkeys_chunk)})
        url = f"{self.base_url}/validators/servers/ids?{query}"
        req = Request(url, headers=self.default_headers(), method="GET")

        try:
            with urlopen(req, timeout=timeout) as resp:
                status = resp.getcode()
                body = resp.read().decode("utf-8", errors="ignore")
                try:
                    data = json.loads(body)
                except json.JSONDecodeError:
                    if status < 200 or status >= 300:
                        bt.logging.error(
                            f"collector ids chunk={chunk_index}/{total_chunks} status={status} body={body}"
                        )
                    return status, []

                items_raw = data.get("items", []) if isinstance(data, dict) else []
                items: List[ValidatorServer] = []
                for item in items_raw:
                    if isinstance(item, dict):
                        vid = str(item.get("id", ""))
                        hk = str(item.get("hotkey", ""))
                        reg = item.get("registered_at")
                        if vid and hk:
                            items.append(ValidatorServer(id=vid, hotkey=hk, registered_at=reg))

                if status < 200 or status >= 300:
                    bt.logging.error(
                        f"collector ids chunk={chunk_index}/{total_chunks} status={status} body={body}"
                    )
                return status, items
        except HTTPError as e:
            bt.logging.error(
                f"collector ids chunk={chunk_index}/{total_chunks} error: HTTP {e.code} - {e.reason}"
            )
            return e.code, []
        except Exception as e:  # noqa: BLE001
            bt.logging.error(
                f"collector ids chunk={chunk_index}/{total_chunks} error: {e}"
            )
            return 599, []

    def get_validator_server_ids(
        self, hotkeys: List[str], timeout_seconds: Optional[float] = None
    ) -> Tuple[int, List[ValidatorServer]]:
        if not hotkeys:
            return 400, []

        # Preserve order while removing duplicates to keep requests as small as possible.
        unique_hotkeys = list(dict.fromkeys(hotkeys))

        timeout = timeout_seconds if timeout_seconds is not None else self.timeout_seconds

        max_chunks = 5
        chunk_count = min(max_chunks, len(unique_hotkeys)) or 1
        chunk_size = max(1, (len(unique_hotkeys) + chunk_count - 1) // chunk_count)
        total_chunks = (len(unique_hotkeys) + chunk_size - 1) // chunk_size

        aggregated: Dict[str, ValidatorServer] = {}
        first_error_status: Optional[int] = None
        any_success = False

        for idx in range(0, len(unique_hotkeys), chunk_size):
            chunk_index = (idx // chunk_size) + 1
            chunk_hotkeys = unique_hotkeys[idx : idx + chunk_size]
            status, items = self._fetch_validator_server_ids_chunk(
                chunk_hotkeys,
                timeout,
                chunk_index,
                total_chunks,
            )

            if first_error_status is None and (status < 200 or status >= 300):
                first_error_status = status
            if 200 <= status < 300:
                any_success = True

            for item in items:
                if item.hotkey not in aggregated:
                    aggregated[item.hotkey] = item

        if aggregated or any_success:
            return (first_error_status or 200), list(aggregated.values())

        return (first_error_status or 599), []

    def get_validator_server_ids_map(self, hotkeys: List[str], timeout_seconds: Optional[float] = None) -> Tuple[int, Dict[str, ValidatorServer]]:
        status, items = self.get_validator_server_ids(hotkeys, timeout_seconds)
        mapping: Dict[str, ValidatorServer] = {item.hotkey: item for item in items}
        return status, mapping

    def get_server_metrics(self, server_id: str, timeout_seconds: Optional[float] = None) -> Tuple[int, Any]:
        if not server_id:
            return 400, None
        url = f"{self.base_url}/validators/servers/{server_id}/metrics"
        req = Request(url, headers=self.default_headers(), method="GET")
        timeout = timeout_seconds if timeout_seconds is not None else self.timeout_seconds
        try:
            with urlopen(req, timeout=timeout) as resp:
                status = resp.getcode()
                body = resp.read().decode("utf-8", errors="ignore")
                try:
                    data = json.loads(body)
                    if status < 200 or status >= 300:
                        bt.logging.error(f"collector metrics status={status} server_id={server_id} body={body}")
                    return status, data
                except json.JSONDecodeError:
                    if status < 200 or status >= 300:
                        bt.logging.error(f"collector metrics status={status} server_id={server_id} body={body}")
                    return status, None
        except Exception as e:
            bt.logging.error(f"collector metrics error server_id={server_id}: {e}")
            return 599, None

    

    def get_server_reports(self, server_id: str, limit: Optional[int] = None, timeout_seconds: Optional[float] = None) -> Tuple[int, List[Dict[str, Any]]]:
        """
        Get server reports as raw dictionaries
        
        Args:
            server_id: Server ID to get reports for
            limit: Maximum number of reports to fetch
            timeout_seconds: Request timeout
            
        Returns:
            Tuple of (status_code, list_of_report_dicts)
        """
        if not server_id:
            return 400, []
        
        effective_limit = int(limit) if limit is not None else self.reports_limit_default
        query = urlencode({"limit": effective_limit})
        url = f"{self.base_url}/validators/servers/{server_id}/reports?{query}"
        req = Request(url, headers=self.default_headers(), method="GET")
        timeout = timeout_seconds if timeout_seconds is not None else self.timeout_seconds
        
        try:
            with urlopen(req, timeout=timeout) as resp:
                status = resp.getcode()
                body = resp.read().decode("utf-8", errors="ignore")
                
                try:
                    data = json.loads(body)
                except json.JSONDecodeError:
                    if status < 200 or status >= 300:
                        bt.logging.error(f"collector reports status={status} server_id={server_id} body={body}")
                    return status, []
                
                # Return raw report dictionaries - let the scoring system handle parsing
                items_raw = data.get("items", []) if isinstance(data, dict) else []
                items = [item for item in items_raw if isinstance(item, dict)]
                
                if status < 200 or status >= 300:
                    bt.logging.error(f"collector reports status={status} server_id={server_id} body={body}")
                
                return status, items
                
        except Exception as e:
            bt.logging.error(f"collector reports error server_id={server_id}: {e}")
            return 599, []
