from typing import Literal, Union
from pydantic import BaseModel, Field


class ClientToServerMessage(BaseModel):
    inner: Union[
        "CtSStartMessage",
        "CtSInitiateConnectionErrorMessage",
        "CtSInitiateConnectionOKMessage",
        "CtSTCPDataMessage",
        "CtSConnectionResetMessage",
    ] = Field(discriminator="kind")


class CtSStartMessage(BaseModel):
    kind: Literal["start"] = "start"
    client_name: str


class CtSInitiateConnectionErrorMessage(BaseModel):
    kind: Literal["initiate_connection_error"] = "initiate_connection_error"
    message: str
    connection_id: str


class CtSInitiateConnectionOKMessage(BaseModel):
    kind: Literal["initiate_connection_ok"] = "initiate_connection_ok"
    connection_id: str


class CtSTCPDataMessage(BaseModel):
    kind: Literal["tcp_data"] = "tcp_data"
    connection_id: str
    data_base64: str

class CtSConnectionResetMessage(BaseModel):
    kind: Literal["connection_reset"] = "connection_reset"
    message: str
    connection_id: str
class ServerToClientMessage(BaseModel):
    inner: Union["StCInitiateConnectionMessage", "StCTCPDataMessage"] = Field(
        discriminator="kind"
    )


class StCInitiateConnectionMessage(BaseModel):
    kind: Literal["initiate_connection"] = "initiate_connection"
    target_ip: str
    target_port: int
    protocol: str
    connection_id: str


class StCTCPDataMessage(BaseModel):
    kind: Literal["tcp_data"] = "tcp_data"
    connection_id: str
    data_base64: str


class SSHProxyCommandToServerMessage(BaseModel):
    inner: Union["PtSStartMessage", "PtSTCPDataMessage"] = Field(discriminator="kind")


# PtS = (SSH) *P*roxy (Command) *t*o *S*erver


class PtSStartMessage(BaseModel):
    kind: Literal["start"] = "start"
    connection_target: str
    target_ip: str
    target_port: int
    protocol: str


class PtSTCPDataMessage(BaseModel):
    kind: Literal["tcp_data"] = "tcp_data"
    data_base64: str


class ServerToSSHProxyCommandMessage(BaseModel):
    inner: Union["StPErrorMessage", "StPStartOKMessage", "StPTCPDataMessage"] = Field(
        discriminator="kind"
    )


class StPErrorMessage(BaseModel):
    kind: Literal["error"] = "error"
    message: str


class StPStartOKMessage(BaseModel):
    kind: Literal["start_ok"] = "start_ok"


class StPTCPDataMessage(BaseModel):
    kind: Literal["tcp_data"] = "tcp_data"
    data_base64: str


def main():
    pass
