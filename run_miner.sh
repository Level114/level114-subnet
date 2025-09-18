#!/bin/bash

# Level114 Subnet Minecraft Server Registration Script (Interactive Mode)
# 
# This script interactively asks for Minecraft server details and registers it 
# with collector-center-main service, then exits.

set -e

# Default values
WALLET_NAME=""
WALLET_HOTKEY=""
COLLECTOR_IP=""
COLLECTOR_PORT=3000
MINECRAFT_IP=""
MINECRAFT_PORT=25565
INTERACTIVE_MODE=true

# Check for help or show usage
if [[ "$1" == "-h" ]] || [[ "$1" == "--help" ]]; then
    echo "🎮 Level114 Minecraft Server Registration (Interactive Mode)"
    echo ""
    echo "This tool will interactively ask for your Minecraft server details"
    echo "and register it with collector-center-main, then exit."
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -h, --help                      Show this help message"
    echo "  --non-interactive               Run in non-interactive mode with all parameters"
    echo ""
    echo "In non-interactive mode, you can use:"
    echo "  --collector_ip IP               IP address of collector-center-main server"
    echo "  --collector_port PORT           Collector port (default: 3000)"
    echo "  --minecraft_ip IP               Minecraft server IP"
    echo "  --minecraft_port PORT           Minecraft server port (default: 25565)"
    echo "  --wallet.name NAME              Your Bittensor wallet name"
    echo "  --wallet.hotkey HOTKEY          Your Bittensor wallet hotkey"
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
        --collector_ip)
            COLLECTOR_IP="$2"
            INTERACTIVE_MODE=false
            shift 2
            ;;
        --collector_port)
            COLLECTOR_PORT="$2"
            shift 2
            ;;
        --minecraft_ip)
            MINECRAFT_IP="$2"
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
    echo "🎮 Level114 Minecraft Server Registration - Interactive Mode"
    echo ""
    echo "I will register your Minecraft server with collector-center-main"
    echo ""
    
    # Get collector information
    echo "📡 Collector-Center-Main Information:"
    read -p "Collector-center-main IP: " COLLECTOR_IP
    read -p "Collector-center-main port (default 3000): " input_port
    if [[ -n "$input_port" ]]; then
        COLLECTOR_PORT="$input_port"
    fi
    echo ""
    
    # Get Minecraft server information
    echo "🎮 Minecraft Server Information:"
    read -p "Minecraft server IP: " MINECRAFT_IP
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
if [[ -z "$COLLECTOR_IP" ]]; then
    echo "❌ Error: Collector IP is required"
    echo "Please enter the collector-center-main server IP"
    exit 1
fi

if [[ -z "$MINECRAFT_IP" ]]; then
    echo "❌ Error: Minecraft server IP is required"
    echo "Please enter the Minecraft server IP"
    exit 1
fi

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

# Build collector URL
COLLECTOR_URL="http://${COLLECTOR_IP}:${COLLECTOR_PORT}"

# Check if the script is run from the correct directory
if [[ ! -f "neurons/miner.py" ]]; then
    echo "❌ Error: This script must be run from the level114 subnet root directory"
    echo "Current directory: $(pwd)"
    echo "Expected files: neurons/miner.py"
    exit 1
fi

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

echo "🎮 Registering Minecraft Server with Level114..."
echo ""
echo "📋 Configuration:"
echo "  - Bittensor Wallet: $WALLET_NAME.$WALLET_HOTKEY"
echo "  - Collector-Center: $COLLECTOR_URL"
echo "  - Minecraft Server: $MINECRAFT_IP:$MINECRAFT_PORT"
echo ""
echo "🔄 What the script will do:"
echo "  1. Register your Minecraft server with collector-center-main"
echo "  2. Exit after successful registration"
echo "  3. No background processes or validator serving!"
echo ""
echo "================================================================"
echo ""

# Set Python path to include current directory
export PYTHONPATH="${PWD}:${PYTHONPATH}"

# Build minecraft arguments - always pass the IP since it's required now
MINECRAFT_ARGS="--minecraft_ip $MINECRAFT_IP"
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