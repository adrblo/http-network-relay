#!/usr/bin/env python
from typing import Union

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
        message = SSHProxyCommandToServerMessage.model_validate_json(json_data)
        print(f"Message received from SSH proxy command: {message}")


def main():
    pass
