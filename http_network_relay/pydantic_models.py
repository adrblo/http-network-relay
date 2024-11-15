
from pydantic import BaseModel

class ClientToServerMessage(BaseModel):
    pass

class ServerToClientMessage(BaseModel):
    pass

class SSHProxyCommandToServerMessage(BaseModel):
    pass

class ServerToSSHProxyCommandMessage(BaseModel):
    pass