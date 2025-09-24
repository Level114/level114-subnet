# Level114 Subnet - Scoring System Documentation

## Overview

The Level114 subnet scoring system evaluates Minecraft server performance across three key dimensions: **Infrastructure**, **Participation**, and **Reliability**. This comprehensive system combines real-time metrics with historical analysis to produce fair and accurate miner rankings.

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Collector     │    │    Validator     │    │   Bittensor     │
│   Center API    │◄───┤   Scoring System │───►│   Blockchain    │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                       │                       │
         │                       │                       │
    ┌────▼────┐              ┌───▼───┐               ┌───▼───┐
    │ Reports │              │Storage│               │Weights│
    │Database │              │ SQLite│               │Update │
    └─────────┘              └───────┘               └───────┘
```

## Scoring Components

### 1. Infrastructure (40% Weight)

Evaluates server technical performance and resource efficiency.

**Sub-components:**
- **TPS Performance (55%)** - Minecraft server tick rate
- **Network Latency (25%)** - HTTP response times
- **Memory Efficiency (20%)** - RAM usage and headroom

**Targets:**
- **Ideal TPS:** 20.0 (50ms tick time)
- **Excellent Latency:** <100ms
- **Good Latency:** <300ms
- **Memory Headroom:** >10% free

### 2. Participation (35% Weight)

Measures server engagement and compliance with subnet requirements.

**Sub-components:**
- **Compliance (55%)** - Required plugins and integrity checks
- **Player Activity (30%)** - Active player counts and engagement
- **Registration (15%)** - Proper validator registration status

**Requirements:**
- **Required Plugins:** Level114
- **Optimal Players:** 20-80% of max capacity
- **Max Player Weight:** 200 (anti-whale protection)

### 3. Reliability (25% Weight)

Analyzes server stability and consistency over time.

**Sub-components:**
- **Uptime Trends (50%)** - Server availability patterns
- **TPS Stability (35%)** - Performance consistency
- **Recovery Speed (15%)** - Time to recover from issues

**Thresholds:**
- **Uptime Bonus:** Capped at 72 hours
- **TPS Stability:** Coefficient of variation <30%
- **Recovery Time:** <30 minutes for full score

## Scoring Formula

```python
def calculate_score(miner_context):
    # Component scores [0.0 - 1.0]
    infrastructure = evaluate_infrastructure(context)  # 40%
    participation = evaluate_participation(context)    # 35% 
    reliability = evaluate_reliability(context)        # 25%
    
    # Weighted combination
    raw_score = (
        0.40 * infrastructure +
        0.35 * participation +
        0.25 * reliability
    )
    
    # Apply penalties for critical failures
    if not compliance_ok:
        raw_score = min(raw_score, 0.30)  # Hard cap
    
    # Normalize to [0, 1000] range
    return normalize_score(raw_score)
```

## Score Classifications

| Score Range | Classification | Description |
|-------------|---------------|-------------|
| 850 - 1000  | **Excellent** | Top-tier performance across all metrics |
| 650 - 849   | **Good**      | Solid performance with minor issues |
| 300 - 649   | **Average**   | Mixed performance needing improvement |
| 0 - 299     | **Poor**      | Significant issues requiring attention |

## Data Sources

### Collector Center API

**Endpoints:**
- `/validators/servers/ids?hotkeys=...` - Server registration lookup
- `/validators/servers/{id}/metrics` - Current server metrics
- `/validators/servers/{id}/reports?limit=N` - Historical reports

**Report Structure:**
```json
{
  "id": "report-uuid",
  "server_id": "server-uuid", 
  "counter": 123,
  "payload": {
    "active_players": [{"name": "Player", "uuid": "..."}],
    "max_players": 20000,
    "tps_millis": 50,
    "memory_ram_info": {
      "free_memory_bytes": 4000000000,
      "total_memory_bytes": 8000000000,
      "used_memory_bytes": 4000000000
    },
    "plugins": ["Level114", "..."],
    "system_info": {
      "cpu_cores": 20,
      "uptime_ms": 3600000,
      "..."
    }
  },
  "signature": "ed25519-signature",
  "created_at": "2025-09-19T12:46:41Z"
}
```

### Integrity Verification

**Security Measures:**
- **Payload Hash:** SHA256 of canonical JSON
- **Ed25519 Signature:** Cryptographic authenticity
- **Replay Protection:** Nonce and counter validation
- **Timestamp Validation:** Clock drift tolerance

## Anti-Cheat & Limits

**Sanity Checks:**
- Max players clamped to 10,000
- TPS millis range: 10-25,000 (0.04-100 TPS)
- Timestamp drift: ±15 minutes tolerance

**Penalties:**
- **Missing Required Plugins:** Score ≤300/1000
- **Integrity Failures:** Score ≤300/1000
- **Signature Failures:** Score ≤100/1000
- **Clock Drift:** 50% score reduction

## Smoothing & Stability

**Exponential Moving Average:**
- **Alpha:** 0.2 (configurable via `LEVEL114_EMA_ALPHA`)
- **Min Change:** 1 point threshold
- **Max Change:** 200 points per update

**History Management:**
- **Max Reports:** 60 per server
- **Reliability Window:** Last 20 reports for stability
- **Freshness:** Reports >5 minutes get reduced weight

## Configuration

### Environment Variables

```bash
# Performance targets
LEVEL114_IDEAL_TPS=20.0
LEVEL114_MAX_LATENCY_S=1.0
LEVEL114_MAX_PLAYERS_WEIGHT=200

# Scoring weights
LEVEL114_W_INFRA=0.40
LEVEL114_W_PART=0.35  
LEVEL114_W_RELY=0.25

# System behavior
LEVEL114_EMA_ALPHA=0.2
LEVEL114_MAX_SCORE=1000
LEVEL114_DEBUG_SCORING=false
```

### Required Plugins

```python
REQUIRED_PLUGINS = {
    "Level114"      # Subnet integration
}

BONUS_PLUGINS = {
    "ViaVersion", "ViaBackwards", "ViaRewind",  # Compatibility
    "EssentialsX", "WorldGuard", "LuckPerms",  # Management
    "Vault", "Dynmap", "mcMMO"                 # Features
}
```

## Usage Examples

### CLI Preview Tool

```bash
# Preview score from JSON file
python scripts/score_preview.py --json report.json

# Fetch from collector API
python scripts/score_preview.py \
  --server-id dd227594-2632-4d3e-9396-46f131e47712 \
  --from-api \
  --api-key vk_dev_...

# Show scoring configuration
python scripts/score_preview.py --show-constants
```

### Programmatic Usage

```python
from level114.validator.scoring import MinerContext, calculate_miner_score
from collections import deque

# Create context
context = MinerContext(
    report=server_report,
    http_latency_s=0.1,
    registration_ok=True,
    compliance_ok=True,
    history=deque(recent_reports, maxlen=60)
)

# Calculate score
final_score, components = calculate_miner_score(context)

print(f"Score: {final_score}/1000")
print(f"Infrastructure: {components['infrastructure']:.3f}")
print(f"Participation: {components['participation']:.3f}")
print(f"Reliability: {components['reliability']:.3f}")
```

## Performance Optimization

### Expected Thresholds for High Scores

**Excellent Servers (850+ points):**
- TPS: 19-20 consistently
- Latency: <200ms average
- Uptime: >48 hours without resets
- Players: 20-80% capacity utilization
- Memory: <70% usage with >20% headroom
- All required plugins installed
- Integrity checks passing

**Good Servers (650+ points):**
- TPS: 15-19 with occasional drops
- Latency: <500ms average
- Uptime: >24 hours 
- Players: >5 active users
- Memory: <85% usage
- Required plugins present
- Minor integrity issues acceptable

## Troubleshooting

### Low Infrastructure Scores

1. **TPS Issues:**
   - Optimize plugins (remove unnecessary ones)
   - Increase server resources
   - Reduce world size or complexity
   - Check for plugin conflicts

2. **Latency Problems:**
   - Improve hosting location
   - Use better network infrastructure
   - Optimize database queries
   - Enable compression

3. **Memory Issues:**
   - Increase allocated RAM
   - Optimize JVM garbage collection
   - Remove memory leaks in plugins
   - Limit chunk loading

### Low Participation Scores

1. **Missing Plugins:**
   ```bash
   # Required for subnet compliance
   /plugins install Level114
   ```

2. **Low Player Activity:**
   - Improve server marketing
   - Add engaging content
   - Optimize player experience
   - Host events

3. **Registration Issues:**
   - Verify hotkey mapping
   - Check validator registration
   - Ensure API connectivity

### Low Reliability Scores

1. **Uptime Problems:**
   - Implement automatic restarts
   - Monitor system health
   - Fix crash-causing issues
   - Improve infrastructure stability

2. **TPS Instability:**
   - Profile server performance
   - Identify lag sources
   - Balance plugin load
   - Optimize tick-heavy operations

3. **Recovery Issues:**
   - Implement health checks
   - Automate issue detection
   - Improve restart procedures
   - Monitor recovery times

## Integration with Validator Loop

The scoring system integrates with your validator's main loop:

```python
async def validator_cycle():
    for server_id in active_servers:
        # 1. Fetch latest report
        report = await fetch_latest_report(server_id)
        
        # 2. Verify integrity
        integrity_ok = verify_report_integrity(report)
        
        # 3. Build context
        context = MinerContext(
            report=report,
            http_latency_s=measure_latency(),
            registration_ok=is_registered(server_id),
            compliance_ok=integrity_ok,
            history=load_history(server_id)
        )
        
        # 4. Calculate score
        score, components = calculate_miner_score(context)
        
        # 5. Apply smoothing
        previous_score = storage.get_score(server_id)
        smoothed_score = apply_score_smoothing(score, previous_score)
        
        # 6. Store results
        storage.upsert_score(server_id, smoothed_score, 
                           components['infrastructure'],
                           components['participation'], 
                           components['reliability'])
        
        # 7. Update weights on blockchain
        hotkey = storage.get_server_hotkey(server_id)
        if hotkey:
            update_weight(hotkey, smoothed_score)
```

## Monitoring & Analytics

### Storage Schema

```sql
-- Historical reports for trend analysis
CREATE TABLE reports_by_server (
    server_id TEXT NOT NULL,
    ts INTEGER NOT NULL,
    tps REAL NOT NULL,
    uptime_ms INTEGER NOT NULL,
    players INTEGER NOT NULL,
    latency REAL NOT NULL,
    comp INTEGER NOT NULL,
    report_json TEXT NOT NULL,
    PRIMARY KEY (server_id, ts)
);

-- Current scores and components
CREATE TABLE miner_scores (
    server_id TEXT PRIMARY KEY,
    score INTEGER NOT NULL,
    infra REAL NOT NULL,
    part REAL NOT NULL,
    rely REAL NOT NULL,
    updated_at INTEGER NOT NULL
);

-- Server registration mapping
CREATE TABLE server_registry (
    server_id TEXT PRIMARY KEY,
    hotkey TEXT NOT NULL,
    registered_at INTEGER NOT NULL,
    last_seen INTEGER NOT NULL,
    status TEXT DEFAULT 'active'
);
```

### Metrics Dashboard

Key metrics to monitor:

- **Score Distribution:** Histogram of all server scores
- **Component Analysis:** Average infrastructure/participation/reliability
- **Trend Analysis:** Score changes over time
- **Health Indicators:** Servers with declining performance
- **Network Stats:** Overall subnet health metrics

## Testing

Run the comprehensive test suite:

```bash
# Run all tests
python -m pytest tests/test_scorer.py -v

# Run specific test categories  
python -m pytest tests/test_scorer.py::TestScoring -v
python -m pytest tests/test_scorer.py::TestIntegrity -v
python -m pytest tests/test_scorer.py::TestStorage -v
```

## Support

For issues or questions:

1. **Check logs** with `LEVEL114_DEBUG_SCORING=true`
2. **Use preview tool** for analysis
3. **Review constants** with `--show-constants`
4. **Verify integrity** checks are passing
5. **Monitor storage** for data consistency

The scoring system is designed to be fair, transparent, and resistant to gaming while rewarding genuine high-quality Minecraft server operation.
