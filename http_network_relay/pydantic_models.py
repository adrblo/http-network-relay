
from typing import Literal, Union
from pydantic import BaseModel

class ClientToServerMessage(BaseModel):
    pass

class ServerToClientMessage(BaseModel):
    pass

class SSHProxyCommandToServerMessage(BaseModel):
    kind: Literal["start"]
    inner: Union["StartPtSMessage"]

# PtS = (SSH) *P*roxy (Command) *t*o *S*erver

class StartPtSMessage(BaseModel):
    connection_target: str
    server_ip: str
    server_port: int
    protocol: str
class ServerToSSHProxyCommandMessage(BaseModel):
    pass


def main():
    pass
