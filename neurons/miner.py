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

import requests
import sys
import argparse
import bittensor as bt


class MinecraftServerRegistration:
    """
    Simple Level114 miner that ONLY registers Minecraft server information 
    with collector-center-main and exits.
    
    No axon, no background processes, no validator serving.
    """

    def __init__(self, config):
        self.config = config
        
        # Initialize wallet for signature
        self.wallet = bt.wallet(
            name=config.wallet_name,
            hotkey=config.wallet_hotkey,
            path=config.wallet_path
        )

    def get_public_ip(self) -> str:
        """Get public IP address of this server"""
        try:
            response = requests.get('https://api.ipify.org', timeout=10)
            if response.status_code == 200:
                return response.text.strip()
        except Exception as e:
            bt.logging.warning(f"Could not get public IP: {e}")
        return None

    def create_signature(self, message: str) -> str:
        """Create signature for message using wallet hotkey"""
        try:
            bt.logging.debug(f"Creating signature for message: {message}")
            bt.logging.debug(f"Using hotkey: {self.wallet.hotkey.ss58_address}")
            
            # Convert message to bytes
            message_bytes = message.encode('utf-8')
            
            # Sign the message using Bittensor wallet
            signature = self.wallet.hotkey.sign(message_bytes)
            
            # Convert to hex string (lowercase)
            signature_hex = signature.hex()
            bt.logging.debug(f"Generated signature: {signature_hex[:20]}...")
            
            return signature_hex
            
        except Exception as e:
            bt.logging.error(f"Error creating signature: {e}")
            bt.logging.error(f"Message was: {message}")
            bt.logging.error(f"Hotkey: {self.wallet.hotkey.ss58_address}")
            raise

    def register_minecraft_server(self) -> bool:
        """Register Minecraft server with collector-center-main"""
        try:
            bt.logging.info("🎮 Registering Minecraft server with collector-center-main...")
            
            # Get server IP
            minecraft_ip = getattr(self.config, 'minecraft_ip', None) or self.get_public_ip()
            minecraft_port = getattr(self.config, 'minecraft_port', 25565)
            
            if not minecraft_ip:
                bt.logging.error("Could not determine Minecraft server IP address")
                return False
            
            # Create registration message (format expected by collector-center-main)
            message = f"register:{minecraft_ip}:{minecraft_port}"
            signature = self.create_signature(message)
            
            # Prepare registration data (matching collector-center-main expected format)
            registration_data = {
                "ip": minecraft_ip,
                "port": minecraft_port,
                "hotkey": self.wallet.hotkey.ss58_address,
                "signature": signature
            }
            
            # Make registration request to collector
            collector_url = getattr(self.config, 'collector_url', 'http://localhost:8000')
            bt.logging.info(f"Registering Minecraft server at {minecraft_ip}:{minecraft_port}")
            bt.logging.info(f"Collector URL: {collector_url}")
            
            response = requests.post(
                f"{collector_url}/servers/register",
                json=registration_data,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                server_id = result.get('server', {}).get('id', 'unknown')
                api_token = result.get('credentials', {}).get('token', 'unknown')
                key_id = result.get('server', {}).get('key_id', 'unknown')
                
                bt.logging.success(f"✅ Minecraft server registered successfully!")
                bt.logging.info(f"🎯 Server ID: {server_id}")
                bt.logging.info(f"🔑 API Token: {api_token[:20]}...")
                bt.logging.info(f"🌍 Minecraft IP: {minecraft_ip}")
                bt.logging.info(f"🚪 Minecraft Port: {minecraft_port}")
                bt.logging.info(f"🔐 Hotkey: {self.wallet.hotkey.ss58_address}")
                
                # Save credentials to file
                self._save_credentials(server_id, api_token, key_id, minecraft_ip, minecraft_port)
                
                return True
            else:
                bt.logging.error(f"❌ Failed to register Minecraft server: {response.status_code}")
                bt.logging.error(f"Response: {response.text}")
                return False
                
        except Exception as e:
            bt.logging.error(f"❌ Error registering Minecraft server: {e}")
            return False

    def _save_credentials(self, server_id: str, api_token: str, key_id: str, minecraft_ip: str, minecraft_port: int):
        """Save server credentials to file"""
        try:
            import os
            from datetime import datetime
            
            # Create credentials directory if it doesn't exist
            creds_dir = "credentials"
            if not os.path.exists(creds_dir):
                os.makedirs(creds_dir)
            
            # Create filename based on wallet and minecraft server
            wallet_name = getattr(self.config, 'wallet_name', 'unknown')
            hotkey_name = getattr(self.config, 'wallet_hotkey', 'unknown')
            filename = f"{creds_dir}/minecraft_server_{wallet_name}_{hotkey_name}_{minecraft_ip.replace('.', '_')}.txt"
            
            # Prepare credentials content
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            credentials_content = f"""# Level114 Minecraft Server Credentials
# Generated on: {timestamp}
# 
# KEEP THIS FILE SECURE!
# This information is necessary for server management.

[Server Information]
Server ID: {server_id}
API Token: {api_token}
Key ID: {key_id}
Minecraft IP: {minecraft_ip}
Minecraft Port: {minecraft_port}

[Wallet Information]
Wallet Name: {wallet_name}
Hotkey Name: {hotkey_name}
Hotkey Address: {self.wallet.hotkey.ss58_address}

[Collector Information]
Collector URL: {getattr(self.config, 'collector_url', 'unknown')}
Registration Time: {timestamp}

# How to use these credentials:
# - Server ID: Unique identifier of the server in the system
# - API Token: Token for authentication with collector-center-main
# - Keep this information for future interactions with the system
"""
            
            # Write credentials to file
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(credentials_content)
            
            # Also create a simple JSON format for programmatic access
            import json
            json_filename = filename.replace('.txt', '.json')
            json_data = {
                "server_id": server_id,
                "api_token": api_token,
                "key_id": key_id,
                "minecraft_ip": minecraft_ip,
                "minecraft_port": minecraft_port,
                "wallet_name": wallet_name,
                "hotkey_name": hotkey_name,
                "hotkey_address": self.wallet.hotkey.ss58_address,
                "collector_url": getattr(self.config, 'collector_url', 'unknown'),
                "registration_time": timestamp
            }
            
            with open(json_filename, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, indent=2, ensure_ascii=False)
            
            bt.logging.success(f"💾 Credentials saved to files:")
            bt.logging.info(f"   📄 Text format: {filename}")
            bt.logging.info(f"   🔧 JSON format: {json_filename}")
            bt.logging.warning(f"⚠️  IMPORTANT: Keep these files secure!")
            
        except Exception as e:
            bt.logging.error(f"❌ Error saving credentials: {e}")
            bt.logging.warning("Credentials were not saved to file, but registration was successful")


def main():
    """Main entry point - register Minecraft server and exit"""
    
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Level114 Minecraft Server Registration')
    
    # Wallet arguments
    parser.add_argument('--wallet.name', dest='wallet_name', type=str, required=True, help='Wallet name')
    parser.add_argument('--wallet.hotkey', dest='wallet_hotkey', type=str, required=True, help='Wallet hotkey')
    parser.add_argument('--wallet.path', dest='wallet_path', type=str, default='~/.bittensor/wallets/', help='Wallet path')
    
    # Collector arguments
    parser.add_argument('--collector_url', type=str, required=True, help='Collector center URL')
    
    # Minecraft server arguments
    parser.add_argument('--minecraft_ip', type=str, help='Minecraft server IP (auto-detected if not provided)')
    parser.add_argument('--minecraft_port', type=int, default=25565, help='Minecraft server port (default: 25565)')
    
    # Logging
    parser.add_argument('--logging.debug', action='store_true', dest='debug', help='Enable debug logging')
    
    args = parser.parse_args()
    
    # Set up logging
    if args.debug:
        bt.logging.set_debug(True)
    
    bt.logging.info("🚀 Starting Level114 Minecraft Server Registration")
    bt.logging.info(f"Wallet: {args.wallet_name}.{args.wallet_hotkey}")
    bt.logging.info(f"Collector: {args.collector_url}")
    
    try:
        # Create registration client
        registrar = MinecraftServerRegistration(args)
        
        # Register Minecraft server
        if registrar.register_minecraft_server():
            bt.logging.success("🎉 Registration completed successfully!")
            bt.logging.info("💡 Your Minecraft server is now registered with collector-center-main")
            bt.logging.info("")
            bt.logging.info("🔍 Check the 'credentials/' folder for your server credentials:")
            bt.logging.info(f"   📁 credentials/minecraft_server_{args.wallet_name}_{args.wallet_hotkey}_*.txt")
            bt.logging.info(f"   📁 credentials/minecraft_server_{args.wallet_name}_{args.wallet_hotkey}_*.json")
            bt.logging.info("")
            bt.logging.warning("⚠️  IMPORTANT: Keep the credentials files secure!")
            bt.logging.warning("   They contain Server ID and API Token necessary for server management.")
            sys.exit(0)
        else:
            bt.logging.error("❌ Registration failed!")
            sys.exit(1)
            
    except KeyboardInterrupt:
        bt.logging.info("👋 Registration cancelled by user")
        sys.exit(1)
    except Exception as e:
        bt.logging.error(f"❌ Registration error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
