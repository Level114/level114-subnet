# Level114 Subnet Usage Examples

## Miner Setup

The Level114 miner is designed to be simple - it only registers with the collector-center-main service and responds to validator queries.

### Prerequisites
- Python 3.8+
- Bittensor wallet configured
- Access to a running collector-center-main service

### Basic Miner Usage

**IMPORTANT**: You must provide the IP address of the collector-center-main server. The miner can run on any server and will connect to the collector remotely.

#### Using the convenience script (recommended):

```bash
# If collector is running on IP 192.168.1.100
./scripts/run_miner.sh \
    --collector_ip 192.168.1.100 \
    --wallet.name mywallet \
    --wallet.hotkey myhotkey

# If collector is running on a domain with custom port
./scripts/run_miner.sh \
    --collector_ip collector.mydomain.com \
    --collector_port 8080 \
    --wallet.name mywallet \
    --wallet.hotkey myhotkey
```

#### Direct python execution:

```bash
python neurons/miner.py \
    --collector_url http://192.168.1.100:8000 \
    --wallet.name mywallet \
    --wallet.hotkey myhotkey \
    --netuid 114 \
    --subtensor.network finney
```

### What happens when you run the miner:

1. **Registration**: Miner registers once with collector-center-main at startup
2. **Serving**: Miner serves validator requests for basic system metrics
3. **Waiting**: Miner waits for validator queries - no background tasks

### Expected Output:

```
🚀 Starting Level114 Miner...

Configuration:
  - NetUID: 114
  - Network: finney
  - Wallet: mywallet.myhotkey
  - Collector: http://192.168.1.100:8000

📋 What this miner does:
  1. Registers with collector-center-main at 192.168.1.100
  2. Serves validator requests for metrics
  3. That's it - no other background processes!

================================================================

2023-01-01 12:00:00.000 | INFO     | Registering with collector-center-main...
2023-01-01 12:00:01.000 | SUCCESS  | ✅ Successfully registered with collector!
2023-01-01 12:00:01.000 | INFO     | Server ID: abc-123-def
2023-01-01 12:00:01.000 | INFO     | Public IP: 203.0.113.1
2023-01-01 12:00:01.000 | INFO     | Port: 8091
2023-01-01 12:00:01.000 | SUCCESS  | 🎯 Miner registration completed successfully!
2023-01-01 12:00:01.000 | INFO     | The miner will now serve validator requests...
```

## Validator Setup

### Basic Validator Usage:

```bash
# Using the convenience script
./scripts/run_validator.sh \
    --wallet.name mywallet \
    --wallet.hotkey myhotkey

# Direct python execution
python neurons/validator.py \
    --wallet.name mywallet \
    --wallet.hotkey myhotkey \
    --netuid 114 \
    --subtensor.network finney \
    --neuron.sample_size 10
```

### What the validator does:

1. **Query miners**: Asks miners for their performance metrics
2. **Evaluate performance**: Scores miners based on efficiency, uptime, etc.
3. **Set weights**: Updates network weights based on miner performance

## Common Issues

### Miner Issues

**"Failed to register with collector"**
- Check that the collector IP is correct and reachable
- Verify the collector service is running on the specified port
- Check firewall settings

**"Could not determine public IP address"**
- Check your internet connection
- The miner needs to determine its public IP for registration

### Validator Issues  

**"No miners found"**
- Wait for miners to register and join the subnet
- Check that you're on the correct netuid

## Network Configuration



### Mainnet (finney):
```bash
--subtensor.network finney --netuid 114
```

### Local subtensor:
```bash
--subtensor.network local --netuid 1
```
