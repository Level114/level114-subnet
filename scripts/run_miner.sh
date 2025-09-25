#!/bin/bash

# Level114 Subnet Miner Registration Script
# 
# This script registers your Minecraft server with the Level114 subnet
# by connecting to the collector-center-main service. The miner will register
# your server and make it available for validator evaluation.

set -e

# Default values
WALLET_NAME=""
WALLET_HOTKEY=""
# Hardcoded collector URL per request
COLLECTOR_URL="https://collector.level114.io"
MINECRAFT_IP=""
MINECRAFT_HOSTNAME=""
MINECRAFT_PORT=25565
INTERACTIVE_MODE=true

# Check for help or show usage
if [[ "$1" == "-h" ]] || [[ "$1" == "--help" ]]; then
    echo "🎮 Level114 Subnet Miner Registration"
    echo ""
    echo "This tool registers your Minecraft server with the Level114 subnet"
    echo "by connecting to the collector-center-main service."
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -h, --help                      Show this help message"
    echo "  --non-interactive               Run in non-interactive mode with all parameters"
    echo ""
    echo "In non-interactive mode, you can use:"
    echo "  --minecraft_ip IP               Minecraft server IP (required)"
    echo "  --minecraft_hostname HOST       Minecraft server hostname (e.g., play.myserver.com)"
    echo "  --minecraft_port PORT           Minecraft server port (default: 25565)"
    echo "  --wallet.name NAME              Your Bittensor wallet name"
    echo "  --wallet.hotkey HOTKEY          Your Bittensor wallet hotkey"
    echo ""
    echo "Note: Collector URL is fixed to $COLLECTOR_URL"
    echo ""
    exit 0
fi

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --non-interactive)
            INTERACTIVE_MODE=false
            shift
            ;;
        --minecraft_ip)
            MINECRAFT_IP="$2"
            shift 2
            ;;
        --minecraft_hostname)
            MINECRAFT_HOSTNAME="$2"
            shift 2
            ;;
        --minecraft_port)
            MINECRAFT_PORT="$2"
            shift 2
            ;;
        --wallet.name)
            WALLET_NAME="$2"
            shift 2
            ;;
        --wallet.hotkey)
            WALLET_HOTKEY="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use -h or --help for usage information"
            exit 1
            ;;
    esac
done

# Interactive mode - ask user for input
if [[ "$INTERACTIVE_MODE" == "true" ]]; then
    echo "🎮 Level114 Subnet Miner Registration - Interactive Mode"
    echo ""
    echo "I will register your Minecraft server with the Level114 subnet"
    echo "through the collector-center-main service."
    echo ""
    
    # Get Minecraft server information
    echo "🎮 Minecraft Server Information:"
    read -p "Minecraft server IP: " MINECRAFT_IP
    read -p "Minecraft server hostname (e.g., play.myserver.com): " MINECRAFT_HOSTNAME
    read -p "Minecraft server port (default 25565): " input_mc_port
    if [[ -n "$input_mc_port" ]]; then
        MINECRAFT_PORT="$input_mc_port"
    fi
    echo ""
    
    # Get wallet information
    echo "🔑 Bittensor Wallet Information:"
    read -p "Wallet name: " WALLET_NAME
    read -p "Hotkey name: " WALLET_HOTKEY
    echo ""
fi

# Validate required parameters
if [[ -z "$MINECRAFT_IP" ]]; then
    echo "❌ Error: Minecraft server IP is required"
    echo "Please enter the Minecraft server IP"
    exit 1
fi

# Hostname is optional

if [[ -z "$WALLET_NAME" ]]; then
    echo "❌ Error: Wallet name is required"
    echo "Please enter the Bittensor wallet name"
    exit 1
fi

if [[ -z "$WALLET_HOTKEY" ]]; then
    echo "❌ Error: Hotkey name is required"
    echo "Please enter the Bittensor hotkey name"
    exit 1
fi

# Collector URL already set (hardcoded)

# Resolve project root directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Check if we can find the project structure
if [[ ! -f "${PROJECT_ROOT}/neurons/miner.py" ]]; then
    echo "❌ Error: Cannot find Level114 subnet project structure"
    echo "Script location: $SCRIPT_DIR"  
    echo "Project root: $PROJECT_ROOT"
    echo "Expected file: ${PROJECT_ROOT}/neurons/miner.py"
    echo ""
    echo "Please ensure this script is in the scripts/ directory of the Level114 subnet project."
    exit 1
fi

# Change to project root for execution
cd "$PROJECT_ROOT"

# Check for Python command
PYTHON_CMD=""
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
else
    echo "❌ Error: Neither 'python' nor 'python3' command found"
    echo "Please install Python 3.8+ and ensure it's in your PATH"
    exit 1
fi

echo "✅ Using Python command: $PYTHON_CMD"

# Check if virtual environment is activated
if [[ -z "${VIRTUAL_ENV}" ]]; then
    echo "⚠️  Warning: No virtual environment detected. Consider activating a virtual environment first."
    read -p "Continue anyway? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo "🎮 Registering Minecraft Server with Level114 Subnet..."
echo ""
echo "📋 Configuration:"
echo "  - Bittensor Wallet: $WALLET_NAME.$WALLET_HOTKEY"
echo "  - Collector-Center: $COLLECTOR_URL"
if [[ -n "$MINECRAFT_HOSTNAME" ]]; then
    echo "  - Minecraft Server: $MINECRAFT_HOSTNAME ($MINECRAFT_IP):$MINECRAFT_PORT"
else
    echo "  - Minecraft Server: $MINECRAFT_IP:$MINECRAFT_PORT"
fi
echo ""
echo "🔄 What the registration will do:"
echo "  1. Connect your Minecraft server to the Level114 subnet"
echo "  2. Register server details with collector-center-main"
echo "  3. Make your server available for validator evaluation"
echo "  4. Enable earning TAO rewards based on server performance"
echo ""
echo "📊 Your server will be scored on:"
echo "  • Infrastructure (40%): TPS performance, latency, memory usage"
echo "  • Participation (35%): Plugin compliance, player activity"  
echo "  • Reliability (25%): Uptime stability, consistency"
echo ""
echo "================================================================"
echo ""

# Set Python path to include project root
export PYTHONPATH="${PROJECT_ROOT}:${PYTHONPATH}"

# Build minecraft arguments - always IP, hostname if provided
MINECRAFT_ARGS="--minecraft_ip $MINECRAFT_IP"
if [[ -n "$MINECRAFT_HOSTNAME" ]]; then
    MINECRAFT_ARGS="$MINECRAFT_ARGS --minecraft_hostname $MINECRAFT_HOSTNAME"
fi
if [[ "$MINECRAFT_PORT" != "25565" ]]; then
    MINECRAFT_ARGS="$MINECRAFT_ARGS --minecraft_port $MINECRAFT_PORT"
fi

# Register minecraft server
$PYTHON_CMD neurons/miner.py \
    --wallet.name "$WALLET_NAME" \
    --wallet.hotkey "$WALLET_HOTKEY" \
    --collector_url "$COLLECTOR_URL" \
    $MINECRAFT_ARGS \
    --logging.debug
