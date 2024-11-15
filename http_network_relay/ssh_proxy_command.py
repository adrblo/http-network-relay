import asyncio
from websockets.asyncio.client import connect
import argparse
import os
from .pydantic_models import PtSTCPDataMessage, SSHProxyCommandToServerMessage, PtSStartMessage, ServerToSSHProxyCommandMessage, StPErrorMessage, StPStartOKMessage, StPTCPDataMessage
import websockets
import sys
# take 4 arguments: target_host_identifier, server_ip, server_port, protocol
import base64
parser = argparse.ArgumentParser(description="Connect to a server via a proxy command")
parser.add_argument("target_host_identifier", help="The target host identifier")
parser.add_argument("server_ip", help="The server IP")
parser.add_argument("server_port", type=int, help="The server port")
parser.add_argument("protocol", help="The protocol to use (e.g. 'udp' or 'tcp')")

# also takes the server_url but can take environment variable HTTP_NETWORK_RELAY_SERVER_URL
parser.add_argument(
    "--server_url",
    help="The server URL",
    default=os.getenv("HTTP_NETWORK_RELAY_SERVER_URL", "ws://127.0.0.1:8000/ws_for_ssh_proxy_command"),
)

debug = False
if os.getenv("DEBUG") == "1":
    debug = True

def eprint(*args, **kwargs):
    if debug:
        print(*args, file=sys.stderr, **kwargs)

async def async_main():
    args = parser.parse_args()
    if args.server_url is None:
        raise ValueError("server_url is required")

    async with connect(args.server_url) as websocket:
        start_message = SSHProxyCommandToServerMessage(
            inner=PtSStartMessage(
                connection_target=args.target_host_identifier,
                target_ip=args.server_ip,
                target_port=args.server_port,
                protocol=args.protocol,
            )
        )
        await websocket.send(start_message.model_dump_json())
        eprint(f"Sent start message: {start_message}")
        start_response_json = await websocket.recv()
        start_response = ServerToSSHProxyCommandMessage.model_validate_json(start_response_json)
        eprint(f"Received start response: {start_response}")
        if isinstance(start_response.inner, StPErrorMessage):
            eprint(f"Received error message: {start_response}")
            return
        elif isinstance(start_response.inner, StPStartOKMessage):
            eprint(f"Received OK message: {start_response}")
            
        # start async coroutine to read stdin and send it to the server
        async def read_stdin_and_send():
            loop = asyncio.get_event_loop()
            reader = asyncio.StreamReader()
            reader_protocol = asyncio.StreamReaderProtocol(reader)
            await loop.connect_read_pipe(lambda: reader_protocol, sys.stdin)
            while True:
                data = await reader.read(1024)
                if not data:
                    break
                await websocket.send(
                    SSHProxyCommandToServerMessage(
                        inner=PtSTCPDataMessage(data_base64=base64.b64encode(data).decode("utf-8"))
                    ).model_dump_json()
                )

        read_stdin_and_send_task = asyncio.create_task(read_stdin_and_send())

        while True:
            try:
                json_data = await websocket.recv()
            except websockets.exceptions.ConnectionClosedError as e:
                eprint(f"Connection closed: Error: {e}")
                break
            except websockets.exceptions.ConnectionClosedOK as e:
                eprint(f"Connection closed: OK: {e}")
                break
            message = ServerToSSHProxyCommandMessage.model_validate_json(json_data)
            eprint(f"Received message: {message}")
            if isinstance(message.inner, StPTCPDataMessage):
                tcp_data_message = message.inner
                eprint(f"Received TCP data message: {tcp_data_message}")
                sys.stdout.buffer.write(base64.b64decode(tcp_data_message.data_base64))
                sys.stdout.flush()
            else:
                eprint(f"Unknown message received: {message}")
        
        eprint("Exiting")
        read_stdin_and_send_task.cancel()


def main():
    asyncio.run(async_main())
