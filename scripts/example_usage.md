# Level114 Subnet Usage Examples

## Miner Setup

The Level114 miner connects your Minecraft server to the subnet, making it eligible for TAO rewards based on performance. The miner registers your server with the collector-center-main service and enables validator evaluation.

### Prerequisites
- **Python 3.8+** with pip installed
- **Bittensor wallet** configured and registered on subnet 114  
- **Running Minecraft server** with required plugins
- **Collector-center-main service** running (Level114 infrastructure)

### Required Minecraft Server Plugins
Your Minecraft server must have these plugins installed:
- **Level114** - Core subnet plugin (required)
- **SpecsPlugin** - Performance monitoring (required)
- **ViaVersion, ViaBackwards, ViaRewind** - Version compatibility (recommended)

### Basic Miner Usage

#### Interactive Mode (recommended for beginners):

```bash
# Run the interactive registration script
./scripts/run_miner.sh

# It will ask you for:
# - Collector-center-main IP address  
# - Minecraft server IP and port
# - Bittensor wallet name and hotkey
```

#### Non-Interactive Mode:

```bash
# Register with specific collector IP
./scripts/run_miner.sh \
    --non-interactive \
    --collector_ip 192.168.1.100 \
    --minecraft_ip YOUR_MINECRAFT_SERVER_IP \
    --wallet.name mywallet \
    --wallet.hotkey myhotkey

# With custom ports
./scripts/run_miner.sh \
    --non-interactive \
    --collector_ip collector.level114.io \
    --collector_port 3000 \
    --minecraft_ip YOUR_MINECRAFT_SERVER_IP \
    --minecraft_port 25565 \
    --wallet.name mywallet \
    --wallet.hotkey myhotkey
```

#### Direct Python execution:

```bash
python neurons/miner.py \
    --collector_url http://collector.level114.io:3000 \
    --minecraft_ip YOUR_MINECRAFT_SERVER_IP \
    --wallet.name mywallet \
    --wallet.hotkey myhotkey \
    --netuid 114 \
    --subtensor.network finney
```

### What happens when you run the miner:

1. **Registration**: Connects your Minecraft server to the Level114 subnet
2. **Validation**: Ensures required plugins are installed and functioning
3. **Monitoring**: Enables continuous performance monitoring and reporting
4. **Earning**: Makes your server eligible for TAO rewards based on performance

### Expected Output:

```
🎮 Registering Minecraft Server with Level114 Subnet...

📋 Configuration:
  - Bittensor Wallet: mywallet.myhotkey
  - Collector-Center: http://192.168.1.100:3000
  - Minecraft Server: 203.0.113.1:25565

🔄 What the registration will do:
  1. Connect your Minecraft server to the Level114 subnet
  2. Register server details with collector-center-main
  3. Make your server available for validator evaluation
  4. Enable earning TAO rewards based on server performance

📊 Your server will be scored on:
  • Infrastructure (40%): TPS performance, latency, memory usage
  • Participation (35%): Plugin compliance, player activity  
  • Reliability (25%): Uptime stability, consistency

================================================================

2025-09-19 16:00:00.000 | INFO     | Registering with collector-center-main...
2025-09-19 16:00:01.000 | SUCCESS  | ✅ Successfully registered with collector!
2025-09-19 16:00:01.000 | INFO     | Server ID: dd227594-2632-4d3e-9396-46f131e47712
2025-09-19 16:00:01.000 | INFO     | Public IP: 203.0.113.1
2025-09-19 16:00:01.000 | INFO     | Port: 25565
2025-09-19 16:00:01.000 | SUCCESS  | 🎯 Miner registration completed successfully!
2025-09-19 16:00:01.000 | INFO     | Your server is now part of the Level114 subnet!
```

### Earning Potential

Your server's earnings depend on performance scores:

| Score Range | Classification | Potential Earnings |
|-------------|---------------|-------------------|
| 850-1000 | **EXCELLENT** | Maximum TAO rewards |
| 650-849 | **GOOD** | High TAO rewards |
| 400-649 | **AVERAGE** | Medium TAO rewards |
| 300-399 | **POOR** | Low TAO rewards |
| 0-299 | **CRITICAL** | Minimal TAO rewards |

### Optimizing Your Server for Higher Scores

**Infrastructure (40% of score):**
- ✅ Maintain 20 TPS (perfect performance)
- ✅ Minimize server latency (<100ms response time)
- ✅ Keep memory usage efficient (>50% free RAM)

**Participation (35% of score):**  
- ✅ Install all required plugins (Level114, SpecsPlugin)
- ✅ Attract active players to your server
- ✅ Maintain proper registration with subnet

**Reliability (25% of score):**
- ✅ Maintain consistent uptime (avoid server restarts)
- ✅ Keep TPS stable (avoid performance spikes)
- ✅ Recover quickly from any issues

## Validator Setup

The Level114 validator features an advanced scoring system that evaluates Minecraft servers based on infrastructure performance, participation quality, and reliability metrics.

### Prerequisites
- Python 3.8+
- Bittensor wallet configured and registered on subnet 114
- **Collector API key** - Contact Level114 team for access
- Minimum 4GB RAM, 2 CPU cores, 50GB storage

### Basic Validator Usage:

#### Using the convenience script (recommended):

```bash
# Minimum required configuration
./scripts/run_validator.sh \
    --collector.api_key vk_your_api_key_here \
    --wallet.name mywallet \
    --wallet.hotkey myhotkey

# Production configuration with custom settings
./scripts/run_validator.sh \
    --netuid 114 \
    --network finney \
    --collector.api_key vk_prod_your_api_key_here \
    --collector.timeout 30.0 \
    --collector.reports_limit 50 \
    --validator.weight_update_interval 300 \
    --validator.validation_interval 30 \
    --wallet.name production_wallet \
    --wallet.hotkey validator_hotkey \
    --log_level INFO
```

#### Direct python execution:

```bash
python neurons/validator.py \
    --netuid 114 \
    --subtensor.network finney \
    --wallet.name mywallet \
    --wallet.hotkey myhotkey \
    --collector.url http://collector.level114.io:3000 \
    --collector.api_key vk_your_api_key_here \
    --validator.weight_update_interval 300 \
    --validator.validation_interval 30
```

### What the validator does:

1. **Comprehensive Scoring**: Evaluates Minecraft servers using advanced metrics:
   - **Infrastructure (40%)**: TPS performance, HTTP latency, memory usage
   - **Participation (35%)**: Plugin compliance, player activity, registration status  
   - **Reliability (25%)**: Uptime stability, TPS consistency, recovery speed

2. **Real-time Data Collection**: Fetches live performance reports from collector API

3. **Integrity Verification**: Validates report hashes, signatures, and prevents replay attacks

4. **Automatic Weight Setting**: Converts scores to Bittensor weights and updates blockchain every 5 minutes

5. **Data Persistence**: Maintains historical scoring data and analytics in SQLite database

### Expected Output:

```
🚀 Starting Level114 Validator...

✅ Level114 scoring system initialized successfully
📊 Storage: /home/user/.level114/validator.db
⚖️  Weight update interval: 300s

🔄 Starting Level114 validation cycle...
📊 Analyzing server dd227594-... with 10 reports
🖥️  Server Details:
   TPS: 20.0 (Perfect!)
   Players: 5/150 (3.3%)
   Memory: 25.2% used (4.3GB/17.2GB)
   Required plugins: ✅

🎯 Scoring Analysis:
   Infrastructure: 0.998 (40%)
   Participation: 0.653 (35%)  
   Reliability: 0.445 (25%)

🏆 Final Score: 724/1000 (GOOD)

🏋️ Updating blockchain weights...
✅ Weights updated for 3 miners (total weight: 1.000)

✅ Validation cycle complete: 3 servers processed, 3 scores updated, 0 errors, weights updated: true, cycle time: 2.1s
```

### Configuration Options:

#### Core Settings
- `--netuid 114` - Level114 subnet ID (default: 114)
- `--network finney` - Bittensor network (finney/test/local)
- `--wallet.name NAME` - Your wallet name
- `--wallet.hotkey HOTKEY` - Your validator hotkey

#### Collector API Settings (**Required**)
- `--collector.url URL` - Collector API base URL (default: http://collector.level114.io:3000)
- `--collector.api_key KEY` - **Required** - Your validator API key
- `--collector.timeout SECONDS` - API timeout (default: 10.0)
- `--collector.reports_limit N` - Max reports per query (default: 25)

#### Validator Scoring Settings
- `--validator.weight_update_interval SEC` - Weight update frequency (default: 300 = 5 minutes)
- `--validator.validation_interval SEC` - Validation cycle interval (default: 30 seconds)

### Scoring System Overview:

| Score Range | Classification | Weight | Description |
|-------------|---------------|--------|-------------|
| 850-1000 | **EXCELLENT** | 0.85-1.00 | Perfect TPS, high uptime, full compliance |
| 650-849 | **GOOD** | 0.65-0.84 | Solid performance, minor issues |
| 400-649 | **AVERAGE** | 0.40-0.64 | Acceptable but needs improvement |
| 300-399 | **POOR** | 0.30-0.39 | Significant performance problems |
| 0-299 | **CRITICAL** | 0.00-0.29 | Major issues, minimal rewards |

## Common Issues

### Miner Issues

**"❌ Error: Cannot find Level114 subnet project structure"**
- Ensure you're running the script from the correct location
- The script should be in the `scripts/` directory of the Level114 project
- Check that `neurons/miner.py` exists in the project root

**"❌ Error: Collector IP is required"**
- You must provide the IP address of the collector-center-main server
- In interactive mode, you'll be prompted for this
- In non-interactive mode, use `--collector_ip YOUR_IP`

**"❌ Error: Minecraft server IP is required"**
- You must specify your Minecraft server's IP address
- Use your server's public IP if validators need to connect remotely
- Use `--minecraft_ip YOUR_SERVER_IP`

**"Failed to register with collector"**
- Check that the collector IP is correct and reachable
- Verify the collector service is running on the specified port (default: 3000)
- Check firewall settings on both collector and miner machines
- Ensure your Bittensor wallet is properly configured

**"Missing required plugins"**
- Your Minecraft server must have Level114 and SpecsPlugin installed
- Download plugins from the Level114 repository
- Restart your Minecraft server after installing plugins
- Check plugin compatibility with your Minecraft version

**"Could not determine public IP address"**
- Check your internet connection
- The miner needs to determine its public IP for registration
- Ensure your server can make outbound HTTP requests

**"Wallet not registered on subnet 114"**
- Register your miner wallet on subnet 114 first
- Ensure you have sufficient TAO for registration fees
- Check your wallet hotkey is configured correctly

**"Low server performance scores"**
- Review the optimization guide above
- Check TPS performance (target: 20 TPS)
- Monitor memory usage and server load
- Ensure required plugins are functioning correctly

### Validator Issues

**"❌ --collector.api_key is required"**
- You must provide a valid collector API key
- Contact the Level114 team to obtain your validator API key
- Ensure the API key starts with `vk_`

**"❌ Failed to initialize scoring system"**
- Check that all required dependencies are installed: `pip install -r requirements.txt`
- Verify your Python version is 3.8+
- Ensure sufficient disk space for SQLite database

**"⚠️ Collector API status 401 (Unauthorized)"**
- Your API key is invalid or expired
- Check that you're using the correct API key for your validator
- Contact Level114 team if the key was recently issued

**"⚠️ Collector API status 500 (Internal Server Error)"**
- Temporary collector service issue
- The validator will retry automatically
- Check the collector service status or contact support if persistent

**"⚠️ Using basic fallback validation"**
- The advanced scoring system encountered an error
- Check logs for specific error details
- The validator continues with basic functionality while issues are resolved

**"❌ Error updating weights"**
- Check your wallet has sufficient TAO for transaction fees
- Verify you're registered as a validator on subnet 114
- Ensure your hotkey has the correct permissions

**"No valid reports found"**
- No miners have submitted reports recently
- Wait for miners to register and start reporting
- Check that miners are running the correct collector integration

### Performance Issues

**"Validation cycles taking too long (>60s)"**
- Increase `--validator.validation_interval` to reduce frequency
- Check network connectivity to collector API
- Consider reducing `--collector.reports_limit` for faster queries

**"Weight updates failing frequently"**
- Check subtensor connection stability
- Verify wallet balance for transaction fees
- Monitor network congestion and retry timing

**"High memory usage"**
- The validator stores 7 days of historical data by default
- Memory usage typically 200-500MB for normal operation
- Restart validator if memory usage exceeds 1GB

### Debugging Commands

**Test validator integration:**
```bash
python3 test_validator_weights.py --api-key YOUR_API_KEY --miner-hotkey YOUR_MINER_HOTKEY
```

**Preview scoring for a specific server:**
```bash
python3 scripts/score_preview.py --server-id YOUR_SERVER_ID --from-api --api-key YOUR_API_KEY
```

**Check scoring constants:**
```bash
python3 scripts/score_preview.py --show-constants
```

**Test collector API manually:**
```bash
curl -H "Authorization: Bearer YOUR_API_KEY" \
  http://collector.level114.io:3000/validators/health
```

## Network Configuration

### Mainnet (finney) - Production:
```bash
./scripts/run_validator.sh \
    --netuid 114 \
    --network finney \
    --collector.url http://collector.level114.io:3000 \
    --collector.api_key vk_prod_your_key \
    --wallet.name production_wallet \
    --wallet.hotkey production_hotkey
```

### Testnet - Development:
```bash
./scripts/run_validator.sh \
    --netuid 114 \
    --network test \
    --collector.url http://collector.level114.io:3000 \
    --collector.api_key vk_test_your_key \
    --validator.validation_interval 60 \
    --wallet.name test_wallet \
    --wallet.hotkey test_hotkey
```

### Local subtensor - Testing:
```bash
./scripts/run_validator.sh \
    --netuid 1 \
    --network local \
    --collector.url http://localhost:3000 \
    --collector.api_key vk_local_test_key \
    --validator.weight_update_interval 60 \
    --validator.validation_interval 15 \
    --wallet.name local_wallet \
    --wallet.hotkey local_hotkey
```

## Monitoring Your Validator

### Success Indicators:
✅ **Consistent validation cycles** with 0 errors  
✅ **Regular weight updates** every 5 minutes  
✅ **Growing number of cached scores**  
✅ **Stable API connectivity** (200 status codes)  
✅ **Increasing storage** with historical data  
✅ **Balanced score distribution** across miners  

### Status Summary (every 10 cycles):
```bash
📊 LEVEL114 VALIDATOR STATUS SUMMARY
🔄 Cycles completed: 25
⚖️  Last weights update: Fri Sep 19 16:00:00 2025
🗂️  Cached scores: 8
💾 Storage: /home/user/.level114/validator.db
🌐 Network: finney
🔢 Subnet: 114
👥 Metagraph size: 50
⏰ Next weight update: 245s
```

### Performance Expectations:
- **Validation cycles**: 30-60 seconds each
- **Weight updates**: Every 5 minutes (300s)
- **API latency**: <500ms average
- **Storage growth**: ~1MB per day
- **Memory usage**: 200-500MB
- **CPU usage**: 5-15% average

## Advanced Configuration

### High-Performance Setup:
```bash
./scripts/run_validator.sh \
    --validator.validation_interval 15 \
    --validator.weight_update_interval 120 \
    --collector.reports_limit 100 \
    --collector.timeout 30.0 \
    --log_level INFO
```

### Conservative Setup:
```bash
./scripts/run_validator.sh \
    --validator.validation_interval 60 \
    --validator.weight_update_interval 600 \
    --collector.reports_limit 10 \
    --collector.timeout 10.0 \
    --log_level WARNING
```

### Development/Debug Setup:
```bash
./scripts/run_validator.sh \
    --validator.validation_interval 120 \
    --validator.weight_update_interval 300 \
    --log_level DEBUG
```

## Support and Resources

- **Documentation**: See `docs/running_validator.md` for comprehensive guide
- **Scoring Details**: See `docs/scoring.md` for technical details
- **GitHub**: [Level114/level114-subnet](https://github.com/Level114/level114-subnet)
- **Discord**: Level114 Community Server
- **Issues**: Use GitHub Issues for bugs and feature requests

---

**The Level114 validator automatically rewards high-performing Minecraft servers and creates strong incentives for infrastructure optimization! 🎮⚖️**
