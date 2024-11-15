import asyncio
import base64
from websockets.asyncio.client import connect
import argparse
import os
from .pydantic_models import (
    ClientToServerMessage,
    CtSConnectionResetMessage,
    CtSInitiateConnectionErrorMessage,
    CtSInitiateConnectionOKMessage,
    CtSStartMessage,
    CtSTCPDataMessage,
    ServerToClientMessage,
    StCInitiateConnectionMessage,
    StCTCPDataMessage,
)
import websockets
import random
from websockets.asyncio.client import ClientConnection
import sys

# take 4 arguments: target_host_identifier, server_ip, server_port, protocol
debug = False
if os.getenv("DEBUG") == "1":
    debug = True

def eprint(*args, **kwargs):
    if debug:
        print(*args, file=sys.stderr, **kwargs)

parser = argparse.ArgumentParser(description="Client for the HTTP network relay")
parser.add_argument(
    "--server_url",
    help="The server URL",
    default=os.getenv(
        "HTTP_NETWORK_RELAY_SERVER_URL", "ws://127.0.0.1:8000/ws_for_clients"
    ),
)
parser.add_argument(
    "--client-name",
    help="The client name",
    default=os.getenv(
        "HTTP_NETWORK_RELAY_CLIENT_NAME", f"client-{random.randbytes(4).hex()}"
    ),
)

active_connections = {} # connection_id -> (tcp_reader, tcp_writer)


async def async_main():
    args = parser.parse_args()
    if args.server_url is None:
        raise ValueError("server_url is required")

    async with connect(args.server_url) as websocket:
        start_message = ClientToServerMessage(
            inner=CtSStartMessage(client_name=args.client_name)
        )
        await websocket.send(start_message.model_dump_json())
        eprint(f"Sent start message: {start_message}")
        while True:
            try:
                json_data = await websocket.recv()
            except websockets.exceptions.ConnectionClosedError:
                eprint("Connection closed")
                break
            message = ServerToClientMessage.model_validate_json(json_data)
            eprint(f"Received message: {message}")
            if isinstance(message.inner, StCInitiateConnectionMessage):
                eprint(f"Received initiate connection message: {message}")
                try:
                    await initiate_connection(message.inner, websocket)
                except Exception as e:
                    eprint(f"Error while initiating connection: {e}")
                    # send an error message back
                    await websocket.send(
                        ClientToServerMessage(
                            inner=CtSInitiateConnectionErrorMessage(message=str(e), connection_id=message.inner.connection_id)
                        ).model_dump_json()
                    )
            elif isinstance(message.inner, StCTCPDataMessage):
                tcp_data_message = message.inner
                eprint(f"Received TCP data message: {tcp_data_message}")
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
                        ClientToServerMessage(
                            inner=CtSConnectionResetMessage(
                                message="Connection reset while writing data",
                                connection_id=tcp_data_message.connection_id,
                            )
                        ).model_dump_json()
                    )
            else:
                eprint(f"Unknown message received: {message}")


async def initiate_connection(message: StCInitiateConnectionMessage, server_websocket: ClientConnection):
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
        ClientToServerMessage(
            inner=CtSInitiateConnectionOKMessage(
                connection_id=message.connection_id
            )
        ).model_dump_json()
    )
    
    # start async coroutine to read from the TCP connection and send it to the server
    async def read_from_tcp_and_send():
        while True:
            data = await reader.read(1024)
            if not data:
                break
            await server_websocket.send(
                ClientToServerMessage(
                    inner=CtSTCPDataMessage(
                        connection_id=message.connection_id,
                        data_base64=base64.b64encode(data).decode("utf-8"),
                    )
                ).model_dump_json()
            )

    read_from_tcp_and_send_task = asyncio.create_task(read_from_tcp_and_send())

def main():
    asyncio.run(async_main())
