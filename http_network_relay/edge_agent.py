import argparse
import asyncio
import base64
import os
import random
import socket
import sys
import time

import websockets
from websockets.asyncio.client import ClientConnection, connect

from .pydantic_models import (
    EdgeAgentToRelayMessage,
    EtRConnectionResetMessage,
    EtRInitiateConnectionErrorMessage,
    EtRInitiateConnectionOKMessage,
    EtRStartMessage,
    EtRTCPDataMessage,
    RelayToEdgeAgentMessage,
    RtEInitiateConnectionMessage,
    RtETCPDataMessage,
)

debug = False
if os.getenv("DEBUG") == "1":
    debug = True


def eprint(*args, only_debug=False, **kwargs):
    if (debug and only_debug) or (not only_debug):
        print(*args, file=sys.stderr, **kwargs)


parser = argparse.ArgumentParser(
    description="Edge agent for HTTP network relay, allows `access-client` to connect to it"
)
parser.add_argument(
    "--relay-url",
    help="The server URL",
    default=os.getenv(
        "HTTP_NETWORK_RELAY_URL", "ws://127.0.0.1:8000/ws_for_edge_agents"
    ),
)
parser.add_argument(
    "--name",
    help="The edge-agents name",
    default=os.getenv(
        "HTTP_NETWORK_RELAY_CLIENT_NAME",
        f"unnamed-fqdn-{socket.getfqdn()}-edge-agent-{random.randbytes(4).hex()}",
    ),
)
parser.add_argument(
    "--secret",
    help="The secret used to authenticate with the relay",
    default=os.getenv("HTTP_NETWORK_RELAY_CLIENT_SECRET", None),
)

active_connections = {}  # connection_id -> (tcp_reader, tcp_writer)


async def async_main():
    args = parser.parse_args()
    if args.relay_url is None:
        raise ValueError("relay_url is required")
    if args.secret is None:
        raise ValueError("secret is required")
    connection_delay = 1
    last_connection_attempt_time = 0
    while True:
        eprint("Connecting to server...")
        # exponential backoff
        try:
            await connect_to_server(args)
        except ConnectionRefusedError as e:
            eprint(f"Connection refused: {e}")
        except Exception as e:
            eprint(f"Error: {e}")
        if time.time() - last_connection_attempt_time >= 60:
            # if it's been more than 60 seconds since the last connection attempt
            # then the connection has been stable
            # and we can reset the connection delay
            connection_delay = 1
        eprint(f"Connection closed, reconnecting in {connection_delay} seconds")
        time.sleep(connection_delay)
        connection_delay = min(2 * connection_delay, 60)
        last_connection_attempt_time = time.time()


async def connect_to_server(args):
    async with connect(args.relay_url) as websocket:
        start_message = EdgeAgentToRelayMessage(
            inner=EtRStartMessage(name=args.name, secret=args.secret)
        )
        await websocket.send(start_message.model_dump_json())
        eprint(f"Sent start message: {start_message}")

        while True:
            try:
                json_data = await websocket.recv()
            except websockets.exceptions.ConnectionClosedError as e:
                eprint(f"Connection closed with error: {e}")
                break
            except websockets.exceptions.ConnectionClosedOK as e:
                eprint(f"Connection closed OK: {e}")
                break
            message = RelayToEdgeAgentMessage.model_validate_json(json_data)
            eprint(f"Received message: {message}", only_debug=True)
            if isinstance(message.inner, RtEInitiateConnectionMessage):
                eprint(f"Received initiate connection message: {message}")
                try:
                    await initiate_connection(message.inner, websocket)
                except Exception as e:
                    eprint(f"Error while initiating connection: {e}")
                    # send an error message back
                    await websocket.send(
                        EdgeAgentToRelayMessage(
                            inner=EtRInitiateConnectionErrorMessage(
                                message=str(e),
                                connection_id=message.inner.connection_id,
                            )
                        ).model_dump_json()
                    )
            elif isinstance(message.inner, RtETCPDataMessage):
                tcp_data_message = message.inner
                eprint(
                    f"Received TCP data message: {tcp_data_message}", only_debug=True
                )
                # associate the connection_id with the websocket
                if tcp_data_message.connection_id not in active_connections:
                    eprint(f"Unknown connection_id: {tcp_data_message.connection_id}")
                    continue
                reader, writer = active_connections[tcp_data_message.connection_id]
                writer.write(base64.b64decode(tcp_data_message.data_base64))
                try:
                    await writer.drain()
                except ConnectionResetError:
                    eprint(f"Connection reset while writing data")
                    writer.close()
                    del active_connections[tcp_data_message.connection_id]
                    await websocket.send(
                        EdgeAgentToRelayMessage(
                            inner=EtRConnectionResetMessage(
                                message="Connection reset while writing data",
                                connection_id=tcp_data_message.connection_id,
                            )
                        ).model_dump_json()
                    )
            else:
                eprint(f"Unknown message received: {message}")


async def initiate_connection(
    message: RtEInitiateConnectionMessage, server_websocket: ClientConnection
):
    eprint(
        f"Initiating connection to {message.target_ip}:{message.target_port} using {message.protocol}"
    )
    if message.protocol != "tcp":
        eprint(f"Unsupported protocol: {message.protocol}")
        raise NotImplementedError(f"Unsupported protocol: {message.protocol}")
    reader, writer = await asyncio.open_connection(
        message.target_ip, message.target_port
    )
    active_connections[message.connection_id] = (reader, writer)
    eprint(f"Connected to {message.target_ip}:{message.target_port}")
    # send OK message back
    await server_websocket.send(
        EdgeAgentToRelayMessage(
            inner=EtRInitiateConnectionOKMessage(connection_id=message.connection_id)
        ).model_dump_json()
    )

    # start async coroutine to read from the TCP connection and send it to the server
    async def read_from_tcp_and_send():
        while True:
            data = await reader.read(1024)
            if not data:
                break
            await server_websocket.send(
                EdgeAgentToRelayMessage(
                    inner=EtRTCPDataMessage(
                        connection_id=message.connection_id,
                        data_base64=base64.b64encode(data).decode("utf-8"),
                    )
                ).model_dump_json()
            )

    read_from_tcp_and_send_task = asyncio.create_task(read_from_tcp_and_send())


def main():
    asyncio.run(async_main())

if __name__ == "__main__":
    main()