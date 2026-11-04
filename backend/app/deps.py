from dataclasses import dataclass

from fastapi import Request

from .ulai.calls import CallManager
from .ulai.gateway import Gateway
from .ulai.hub import Hub
from .ulai.inbound import InboundListener


@dataclass
class Services:
    gateway: Gateway
    hub: Hub
    calls: CallManager
    inbound: InboundListener


def services(request: Request) -> Services:
    return request.app.state.services
