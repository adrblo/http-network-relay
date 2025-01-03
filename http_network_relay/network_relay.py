#!/usr/bin/env python
import os
import sys
from typing import Never, Type

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ValidationError

from .pydantic_models import EdgeAgentToRelayMessage, EtRStartMessage

debug = False
if os.getenv("DEBUG") == "1":
    debug = True


def eprint(*args, only_debug=False, **kwargs):
    if (debug and only_debug) or (not only_debug):
        print(*args, file=sys.stderr, **kwargs)


class NetworkRelay:
    CustomAgentToRelayMessage: Type[BaseModel] = Never
    CustomRelayToAgentMessage: Type[BaseModel] = Never

    def __init__(self, credentials):
        self.agent_connections = []
        self.registered_agent_connections = {}  # name -> connection

        self.credentials = credentials

    async def ws_for_edge_agents(self, websocket: WebSocket):
        await websocket.accept()
        self.agent_connections.append(websocket)
        start_message_json_data = await websocket.receive_text()
        start_message = EdgeAgentToRelayMessage.model_validate_json(
            start_message_json_data
        ).inner
        eprint(f"Message received from agent: {start_message}")
        if not isinstance(start_message, EtRStartMessage):
            eprint(f"Unknown message received from agent: {start_message}")
            return
        #  check if we know the client
        if start_message.name not in self.credentials["edge-agents"]:
            eprint(f"Unknown agent: {start_message.name}")
            # close the connection
            await websocket.close()
            return

        # check if the secret is correct
        if self.credentials["edge-agents"][start_message.name] != start_message.secret:
            eprint(f"Invalid secret for agent: {start_message.name}")
            # close the connection
            await websocket.close()
            return

        # check if the client is already registered
        if start_message.name in self.registered_agent_connections:
            eprint(f"Agent already registered: {start_message.name}")
            # close the connection
            await websocket.close()
            return

        self.registered_agent_connections[start_message.name] = websocket
        eprint(f"Registered agent connection: {start_message.name}")

        while True:
            try:
                json_data = await websocket.receive_text()
            except WebSocketDisconnect:
                eprint(f"Agent disconnected: {start_message.name}")
                del self.registered_agent_connections[start_message.name]
                break
            try:
                message = EdgeAgentToRelayMessage.model_validate_json(json_data).inner
            except ValidationError:
                if self.CustomAgentToRelayMessage != Never:
                    message = self.CustomAgentToRelayMessage.model_validate_json(
                        json_data
                    )  # pylint: disable=E1101
            eprint(f"Message received from agent: {message}", only_debug=True)
            if self.CustomAgentToRelayMessage != Never:
                assert isinstance(message, self.CustomAgentToRelayMessage)
                await self.handle_custom_agent_message(message)
            else:
                eprint(f"Unknown message received from agent: {message}")

    async def handle_custom_agent_message(self, message_wrapped: BaseModel):
        raise NotImplementedError()
