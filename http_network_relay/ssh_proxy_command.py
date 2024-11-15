import asyncio
from websockets.asyncio.client import connect
import argparse
import os
from pydantic_models import SSHProxyCommandToServerMessage, StartPtSMessage

# take 4 arguments: target_host_identifier, server_ip, server_port, protocol

parser = argparse.ArgumentParser(description="Connect to a server via a proxy command")
parser.add_argument("target_host_identifier", help="The target host identifier")
parser.add_argument("server_ip", help="The server IP")
parser.add_argument("server_port", type=int, help="The server port")
parser.add_argument("protocol", help="The protocol to use (e.g. 'udp' or 'tcp')")

# also takes the server_url but can take environment variable HTTP_NETWORK_RELAY_SERVER_URL
parser.add_argument(
    "--server_url",
    help="The server URL",
    default=os.getenv("HTTP_NETWORK_RELAY_SERVER_URL"),
)


async def async_main():
    args = parser.parse_args()
    if args.server_url is None:
        raise ValueError("server_url is required")

    async with connect(args.server_url) as websocket:
        start_message = SSHProxyCommandToServerMessage(
            inner=StartPtSMessage(
                connection_target=args.target_host_identifier,
                server_ip=args.server_ip,
                server_port=args.server_port,
                protocol=args.protocol,
            )
        )
        await websocket.send(start_message.model_dump_json())
        print(f"Sent start message: {start_message}")
        while True:
            message = await websocket.recv()
            print(f"Received message: {message}")


def main():
    asyncio.run(async_main())
