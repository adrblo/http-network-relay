#!/usr/bin/env python
import argparse
import asyncio
import json
import os
import sys
import uuid
from typing import Union

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from .pydantic_models import (
    AccessClientToRelayMessage,
    AtRStartMessage,
    AtRTCPDataMessage,
    EdgeAgentToRelayMessage,
    EtRConnectionResetMessage,
    EtRInitiateConnectionErrorMessage,
    EtRInitiateConnectionOKMessage,
    EtRStartMessage,
    EtRTCPDataMessage,
    RelayToAccessClientMessage,
    RelayToEdgeAgentMessage,
    RtAErrorMessage,
    RtAStartOKMessage,
    RtATCPDataMessage,
    RtEInitiateConnectionMessage,
    RtETCPDataMessage,
)

app = FastAPI()

agent_connections = []
registered_agent_connections = {}  # name -> connection
access_client_connections = []

initiate_connection_answer_queue = asyncio.Queue()

debug = False
if os.getenv("DEBUG") == "1":
    debug = True


def eprint(*args, only_debug=False, **kwargs):
    if (debug and only_debug) or (not only_debug):
        print(*args, file=sys.stderr, **kwargs)


CREDENTIALS_FILE = os.getenv("HTTP_NETWORK_RELAY_CREDENTIALS_FILE", "credentials.json")
CREDENTIALS = None

@app.websocket("/ws_for_edge_agents")
async def ws_for_edge_agents(websocket: WebSocket):
    await websocket.accept()
    agent_connections.append(websocket)
    start_message_json_data = await websocket.receive_text()
    start_message = EdgeAgentToRelayMessage.model_validate_json(
        start_message_json_data
    ).inner
    eprint(f"Message received from client: {start_message}")
    if not isinstance(start_message, EtRStartMessage):
        eprint(f"Unknown message received from client: {start_message}")
        return
    #  check if we know the client
    if start_message.name not in CREDENTIALS["edge-agents"]:
        eprint(f"Unknown client: {start_message.name}")
        # close the connection
        await websocket.close()
        return

    # check if the secret is correct
    if CREDENTIALS["edge-agents"][start_message.name] != start_message.secret:
        eprint(f"Invalid secret for client: {start_message.name}")
        # close the connection
        await websocket.close()
        return

    # check if the client is already registered
    if start_message.name in registered_agent_connections:
        eprint(f"Client already registered: {start_message.name}")
        # close the connection
        await websocket.close()
        return

    registered_agent_connections[start_message.name] = websocket
    eprint(f"Registered client connection: {start_message.name}")

    while True:
        try:
            json_data = await websocket.receive_text()
        except WebSocketDisconnect:
            eprint(f"Client disconnected: {start_message.name}")
            del registered_agent_connections[start_message.name]
            break
        message = EdgeAgentToRelayMessage.model_validate_json(json_data)
        eprint(f"Message received from client: {message}", only_debug=True)
        if isinstance(message.inner, EtRInitiateConnectionErrorMessage):
            eprint(f"Received initiate connection error message from client: {message}")
            await initiate_connection_answer_queue.put(message.inner)
        elif isinstance(message.inner, EtRInitiateConnectionOKMessage):
            eprint(f"Received initiate connection OK message from client: {message}")
            await initiate_connection_answer_queue.put(message.inner)
        elif isinstance(message.inner, EtRTCPDataMessage):
            eprint(f"Received TCP data message from client: {message}", only_debug=True)
            tcp_data_message = message.inner
            if tcp_data_message.connection_id not in active_connections:
                eprint(f"Unknown connection_id: {tcp_data_message.connection_id}")
                continue
            _agent_connection, access_client_connection = active_connections[
                tcp_data_message.connection_id
            ]
            await access_client_connection.send_text(
                RelayToAccessClientMessage(
                    inner=RtATCPDataMessage(
                        data_base64=tcp_data_message.data_base64,
                    )
                ).model_dump_json()
            )
        elif isinstance(message.inner, EtRConnectionResetMessage):
            eprint(f"Received connection reset message from client: {message}")
            connection_reset_message = message.inner
            if connection_reset_message.connection_id not in active_connections:
                eprint(
                    f"Unknown connection_id: {connection_reset_message.connection_id}"
                )
                continue
            agent_connection, access_client_connection = active_connections[
                connection_reset_message.connection_id
            ]
            await access_client_connection.send_text(
                RelayToAccessClientMessage(
                    inner=RtAErrorMessage(
                        message=connection_reset_message.message,
                    )
                ).model_dump_json()
            )
            del active_connections[connection_reset_message.connection_id]
            # close the connection
            await access_client_connection.close()
        else:
            eprint(f"Unknown message received from client: {message}")


@app.websocket("/ws_for_access_clients")
async def ws_for_access_clients(websocket: WebSocket):
    await websocket.accept()
    access_client_connections.append(websocket)
    json_data = await websocket.receive_text()
    message = AccessClientToRelayMessage.model_validate_json(json_data)
    eprint(f"Message received from access client: {message}")
    if not isinstance(message.inner, AtRStartMessage):
        eprint(f"Unknown message received from access client: {message}")
        return
    start_message = message.inner
    # check if credentials are correct
    if start_message.secret not in CREDENTIALS["access-client-secrets"]:
        eprint(f"Invalid access client secret: {start_message.secret}")
        # send a message back and kill the connection
        await websocket.send_text(
            RelayToAccessClientMessage(
                inner=RtAErrorMessage(message="Invalid access client secret")
            ).model_dump_json()
        )
    # check if the client is registered
    if not start_message.connection_target in registered_agent_connections:
        eprint(f"Agent not registered: {start_message.connection_target}")
        # send a message back and kill the connection
        await websocket.send_text(
            RelayToAccessClientMessage(
                inner=RtAErrorMessage(message="Agent not registered")
            ).model_dump_json()
        )
        await websocket.close()
        return
    agent_connection = registered_agent_connections[start_message.connection_target]
    await start_connection(
        agent_connection=agent_connection,
        access_client_connection=websocket,
        connection_target=start_message.connection_target,
        target_ip=start_message.target_ip,
        target_port=start_message.target_port,
        protocol=start_message.protocol,
    )


active_connections = {}  # connection_id -> (agent_connection, access_client_connection)


async def start_connection(
    agent_connection,
    access_client_connection,
    connection_target,
    target_ip,
    target_port,
    protocol,
):
    connection_id = str(uuid.uuid4())
    eprint(
        f"Starting connection to {target_ip}:{target_port} for {connection_target} using {protocol} with connection_id {connection_id}"
    )
    active_connections[connection_id] = (agent_connection, access_client_connection)
    await agent_connection.send_text(
        RelayToEdgeAgentMessage(
            inner=RtEInitiateConnectionMessage(
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
        message, (EtRInitiateConnectionErrorMessage, EtRInitiateConnectionOKMessage)
    ):
        raise ValueError(f"Unexpected message: {message}")
    if message.connection_id != connection_id:
        raise ValueError(f"Unexpected connection_id: {message.connection_id}")
    if isinstance(message, EtRInitiateConnectionErrorMessage):
        eprint(f"Received error message from client: {message}")
        await access_client_connection.send_text(
            RelayToAccessClientMessage(
                inner=RtAErrorMessage(
                    message=f"Initiating connection failed: {message.message}"
                )
            ).model_dump_json()
        )
        # close the connection
        await access_client_connection.close()
        del active_connections[connection_id]
        return
    if isinstance(message, EtRInitiateConnectionOKMessage):
        eprint(f"Received OK message from client: {message}")
    await access_client_connection.send_text(
        RelayToAccessClientMessage(inner=RtAStartOKMessage()).model_dump_json()
    )

    while True:
        try:
            json_data = await access_client_connection.receive_text()
        except WebSocketDisconnect:
            eprint(f"access client disconnected: {connection_id}")
            if connection_id in active_connections:
                del active_connections[connection_id]
            break
        message = AccessClientToRelayMessage.model_validate_json(json_data)
        if isinstance(message.inner, AtRTCPDataMessage):
            eprint(
                f"Received TCP data message from access client: {message}",
                only_debug=True,
            )
            await agent_connection.send_text(
                RelayToEdgeAgentMessage(
                    inner=RtETCPDataMessage(
                        connection_id=connection_id,
                        data_base64=message.inner.data_base64,
                    )
                ).model_dump_json()
            )
        else:
            eprint(f"Unknown message received from access client: {message}")


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
parser.add_argument(
    "--credentials-file",
    help="The credentials file",
    default=CREDENTIALS_FILE,
)


def main():
    args = parser.parse_args()
    with open(args.credentials_file) as f:
        global CREDENTIALS
        CREDENTIALS = json.load(f)

    uvicorn.run(
        "http_network_relay.network_relay:app",
        host=args.host,
        port=args.port,
        log_level="info",
    )

if __name__ == "__main__":
    main()
else:
    with open(CREDENTIALS_FILE) as f:
        CREDENTIALS = json.load(f)