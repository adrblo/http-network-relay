import asyncio
from websockets.asyncio.client import connect
import argparse
import os
from .pydantic_models import SSHProxyCommandToServerMessage
# take 4 arguments: target_host_identifier, server_ip, server_port, protocol

parser = argparse.ArgumentParser(description="Connect to a server via a proxy command")
parser.add_argument("target_host_identifier", help="The target host identifier")
parser.add_argument("server_ip", help="The server IP")
parser.add_argument("server_port", type=int, help="The server port")
parser.add_argument("protocol", help="The protocol to use (e.g. 'udp' or 'tcp')")

# also takes the server_url but can take environment variable HTTP_NETWORK_RELAY_SERVER_URL
parser.add_argument("--server_url", help="The server URL", default=os.getenv("HTTP_NETWORK_RELAY_SERVER_URL"))



async def async_main():
    args = parser.parse_args()
    if args.server_url is None:
        raise ValueError("server_url is required")
    
    async with connect(args.server_url) as websocket:
        pass


def main():
    asyncio.run(async_main())