#!/usr/bin/env python
from typing import Union
import uvicorn
import argparse
import os

from fastapi import FastAPI, WebSocket
from .pydantic_models import ClientToServerMessage, ServerToClientMessage, SSHProxyCommandToServerMessage, ServerToSSHProxyCommandMessage

app = FastAPI()

client_connections = []
ssh_proxy_command_connections = []

@app.websocket("/ws_for_clients")
async def websocket_for_clients(websocket: WebSocket):
    await websocket.accept()
    client_connections.append(websocket)
    while True:
        json_data = await websocket.receive_json()
        message = ClientToServerMessage.model_validate_json(json_data)
        print(f"Message received from client: {message}")

@app.websocket("/ws_for_ssh_proxy_command")
async def websocket_for_ssh_proxy_command(websocket: WebSocket):
    await websocket.accept()
    ssh_proxy_command_connections.append(websocket)
    while True:
        json_data = await websocket.receive_json()
        print(f"Received message from SSH proxy command: {json_data}")
        message = SSHProxyCommandToServerMessage.model_validate_json(json_data)
        print(f"Message received from SSH proxy command: {message}")

parser = argparse.ArgumentParser(description="Run the HTTP network relay server")
parser.add_argument("--host", help="The host to bind to", default=os.getenv("HTTP_NETWORK_RELAY_SERVER_HOST", "127.0.0.1"))
parser.add_argument("--port", help="The port to bind to", type=int, default=os.getenv("HTTP_NETWORK_RELAY_SERVER_PORT", 8000))


def main():
    args = parser.parse_args()
    uvicorn.run("http_network_relay.server:app", host=args.host, port=args.port, log_level="info")