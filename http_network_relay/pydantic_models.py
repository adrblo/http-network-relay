from typing import Literal, Union

from pydantic import BaseModel, Field


class EdgeAgentToRelayMessage(BaseModel):
    inner: Union["EtRStartMessage",] = Field(discriminator="kind")


class EtRStartMessage(BaseModel):
    kind: Literal["start"] = "start"
    name: str
    secret: str


class AccessClientToRelayMessage(BaseModel):
    inner: Union["AtRStartMessage", "AtRTCPDataMessage"] = Field(discriminator="kind")


class AtRStartMessage(BaseModel):
    kind: Literal["start"] = "start"
    connection_target: str
    target_ip: str
    target_port: int
    protocol: str
    secret: str


class AtRTCPDataMessage(BaseModel):
    kind: Literal["tcp_data"] = "tcp_data"
    data_base64: str


class RelayToAccessClientMessage(BaseModel):
    inner: Union["RtAErrorMessage", "RtAStartOKMessage", "RtATCPDataMessage"] = Field(
        discriminator="kind"
    )


class RtAErrorMessage(BaseModel):
    kind: Literal["error"] = "error"
    message: str


class RtAStartOKMessage(BaseModel):
    kind: Literal["start_ok"] = "start_ok"


class RtATCPDataMessage(BaseModel):
    kind: Literal["tcp_data"] = "tcp_data"
    data_base64: str


def main():
    pass
