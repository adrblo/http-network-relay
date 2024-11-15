
from typing import Literal, Union
from pydantic import BaseModel, Field

class ClientToServerMessage(BaseModel):
    pass

class ServerToClientMessage(BaseModel):
    pass

class SSHProxyCommandToServerMessage(BaseModel):
    inner: Union["StartPtSMessage"] = Field(discriminator="kind")

# PtS = (SSH) *P*roxy (Command) *t*o *S*erver

class StartPtSMessage(BaseModel):
    kind: Literal["start"] = "start"
    connection_target: str
    server_ip: str
    server_port: int
    protocol: str
class ServerToSSHProxyCommandMessage(BaseModel):
    pass


def main():
    pass
