#!/usr/bin/env python
import asyncio
from typing import Union
import uvicorn
import argparse
import os
import uuid

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from .pydantic_models import (
    ClientToServerMessage,
    CtSConnectionResetMessage,
    CtSInitiateConnectionErrorMessage,
    CtSInitiateConnectionOKMessage,
    CtSStartMessage,
    CtSTCPDataMessage,
    PtSTCPDataMessage,
    ServerToClientMessage,
    SSHProxyCommandToServerMessage,
    ServerToSSHProxyCommandMessage,
    PtSStartMessage,
    StCInitiateConnectionMessage,
    StCTCPDataMessage,
    StPErrorMessage,
    StPStartOKMessage,
    StPTCPDataMessage,
)
import sys
import json

app = FastAPI()

client_connections = []
registered_client_connections = {}  # name -> connection
ssh_proxy_command_connections = []

initiate_connection_answer_queue = asyncio.Queue()

debug = False
if os.getenv("DEBUG") == "1":
    debug = True


def eprint(*args, only_debug=False, **kwargs):
    if (debug and only_debug) or (not only_debug):
        print(*args, file=sys.stderr, **kwargs)


CREDENTIALS_FILE = os.getenv("HTTP_NETWORK_RELAY_CREDENTIALS_FILE", "credentials.json")

with open(CREDENTIALS_FILE) as f:
    credentials = json.load(f)


@app.websocket("/ws_for_clients")
async def websocket_for_clients(websocket: WebSocket):
    await websocket.accept()
    client_connections.append(websocket)
    start_message_json_data = await websocket.receive_text()
    start_message = ClientToServerMessage.model_validate_json(
        start_message_json_data
    ).inner
    eprint(f"Message received from client: {start_message}")
    if not isinstance(start_message, CtSStartMessage):
        eprint(f"Unknown message received from client: {start_message}")
        return
    #  check if we know the client
    if start_message.client_name not in credentials["clients"]:
        eprint(f"Unknown client: {start_message.client_name}")
        # close the connection
        await websocket.close()
        return

    # check if the secret is correct
    if credentials["clients"][start_message.client_name] != start_message.client_secret:
        eprint(f"Invalid secret for client: {start_message.client_name}")
        # close the connection
        await websocket.close()
        return

    # check if the client is already registered
    if start_message.client_name in registered_client_connections:
        eprint(f"Client already registered: {start_message.client_name}")
        # close the connection
        await websocket.close()
        return

    registered_client_connections[start_message.client_name] = websocket
    eprint(f"Registered client connection: {start_message.client_name}")

    while True:
        try:
            json_data = await websocket.receive_text()
        except WebSocketDisconnect:
            eprint(f"Client disconnected: {start_message.client_name}")
            del registered_client_connections[start_message.client_name]
            break
        message = ClientToServerMessage.model_validate_json(json_data)
        eprint(f"Message received from client: {message}", only_debug=True)
        if isinstance(message.inner, CtSInitiateConnectionErrorMessage):
            eprint(f"Received initiate connection error message from client: {message}")
            await initiate_connection_answer_queue.put(message.inner)
        elif isinstance(message.inner, CtSInitiateConnectionOKMessage):
            eprint(f"Received initiate connection OK message from client: {message}")
            await initiate_connection_answer_queue.put(message.inner)
        elif isinstance(message.inner, CtSTCPDataMessage):
            eprint(f"Received TCP data message from client: {message}", only_debug=True)
            tcp_data_message = message.inner
            if tcp_data_message.connection_id not in active_connections:
                eprint(f"Unknown connection_id: {tcp_data_message.connection_id}")
                continue
            client_connection, proxy_command_connection = active_connections[
                tcp_data_message.connection_id
            ]
            await proxy_command_connection.send_text(
                ServerToSSHProxyCommandMessage(
                    inner=StPTCPDataMessage(
                        data_base64=tcp_data_message.data_base64,
                    )
                ).model_dump_json()
            )
        elif isinstance(message.inner, CtSConnectionResetMessage):
            eprint(f"Received connection reset message from client: {message}")
            connection_reset_message = message.inner
            if connection_reset_message.connection_id not in active_connections:
                eprint(
                    f"Unknown connection_id: {connection_reset_message.connection_id}"
                )
                continue
            client_connection, proxy_command_connection = active_connections[
                connection_reset_message.connection_id
            ]
            await proxy_command_connection.send_text(
                ServerToSSHProxyCommandMessage(
                    inner=StPErrorMessage(
                        message=connection_reset_message.message,
                    )
                ).model_dump_json()
            )
            del active_connections[connection_reset_message.connection_id]
            # close the connection
            await proxy_command_connection.close()
        else:
            eprint(f"Unknown message received from client: {message}")


@app.websocket("/ws_for_ssh_proxy_command")
async def websocket_for_ssh_proxy_command(websocket: WebSocket):
    await websocket.accept()
    ssh_proxy_command_connections.append(websocket)
    json_data = await websocket.receive_text()
    message = SSHProxyCommandToServerMessage.model_validate_json(json_data)
    eprint(f"Message received from SSH proxy command: {message}")
    if not isinstance(message.inner, PtSStartMessage):
        eprint(f"Unknown message received from SSH proxy command: {message}")
        return
    start_message = message.inner
    # check if credentials are correct
    if start_message.secret_key not in credentials["proxy_users"]:
        eprint(f"Invalid secret key: {start_message.secret_key}")
        # send a message back and kill the connection
        await websocket.send_text(
            ServerToSSHProxyCommandMessage(
                inner=StPErrorMessage(message="Invalid secret key")
            ).model_dump_json()
        )
    # check if the client is registered
    if not start_message.connection_target in registered_client_connections:
        eprint(f"Client not registered: {start_message.connection_target}")
        # send a message back and kill the connection
        await websocket.send_text(
            ServerToSSHProxyCommandMessage(
                inner=StPErrorMessage(message="Client not registered")
            ).model_dump_json()
        )
        await websocket.close()
        return
    client_connection = registered_client_connections[start_message.connection_target]
    await start_connection(
        client_connection=client_connection,
        proxy_command_connection=websocket,
        connection_target=start_message.connection_target,
        target_ip=start_message.target_ip,
        target_port=start_message.target_port,
        protocol=start_message.protocol,
    )


active_connections = (
    {}
)  # connection_id -> (client_connection, proxy_command_connection)


async def start_connection(
    client_connection,
    proxy_command_connection,
    connection_target,
    target_ip,
    target_port,
    protocol,
):
    connection_id = str(uuid.uuid4())
    eprint(
        f"Starting connection to {target_ip}:{target_port} for {connection_target} using {protocol} with connection_id {connection_id}"
    )
    active_connections[connection_id] = (client_connection, proxy_command_connection)
    await client_connection.send_text(
        ServerToClientMessage(
            inner=StCInitiateConnectionMessage(
                target_ip=target_ip,
                target_port=target_port,
                protocol=protocol,
                connection_id=connection_id,
            )
        ).model_dump_json()
    )
    # wait for the client to respond
    message = await initiate_connection_answer_queue.get()
    if not isinstance(
        message, (CtSInitiateConnectionErrorMessage, CtSInitiateConnectionOKMessage)
    ):
        raise ValueError(f"Unexpected message: {message}")
    if message.connection_id != connection_id:
        raise ValueError(f"Unexpected connection_id: {message.connection_id}")
    if isinstance(message, CtSInitiateConnectionErrorMessage):
        eprint(f"Received error message from client: {message}")
        await proxy_command_connection.send_text(
            ServerToSSHProxyCommandMessage(
                inner=StPErrorMessage(
                    message=f"Initiating connection failed: {message.message}"
                )
            ).model_dump_json()
        )
        # close the connection
        await proxy_command_connection.close()
        del active_connections[connection_id]
        return
    if isinstance(message, CtSInitiateConnectionOKMessage):
        eprint(f"Received OK message from client: {message}")
    await proxy_command_connection.send_text(
        ServerToSSHProxyCommandMessage(inner=StPStartOKMessage()).model_dump_json()
    )

    while True:
        try:
            json_data = await proxy_command_connection.receive_text()
        except WebSocketDisconnect:
            eprint(f"SSH proxy command disconnected: {connection_id}")
            if connection_id in active_connections:
                del active_connections[connection_id]
            break
        message = SSHProxyCommandToServerMessage.model_validate_json(json_data)
        if isinstance(message.inner, PtSTCPDataMessage):
            eprint(f"Received TCP data message from SSH proxy command: {message}", only_debug=True)
            await client_connection.send_text(
                ServerToClientMessage(
                    inner=StCTCPDataMessage(
                        connection_id=connection_id,
                        data_base64=message.inner.data_base64,
                    )
                ).model_dump_json()
            )
        else:
            eprint(f"Unknown message received from SSH proxy command: {message}")


parser = argparse.ArgumentParser(description="Run the HTTP network relay server")
parser.add_argument(
    "--host",
    help="The host to bind to",
    default=os.getenv("HTTP_NETWORK_RELAY_SERVER_HOST", "127.0.0.1"),
)
parser.add_argument(
    "--port",
    help="The port to bind to",
    type=int,
    default=int(os.getenv("HTTP_NETWORK_RELAY_SERVER_PORT", "8000")),
)


def main():
    args = parser.parse_args()
    uvicorn.run(
        "http_network_relay.server:app",
        host=args.host,
        port=args.port,
        log_level="info",
    )
