"""SdkGateway against a real gRPC agent server: what the studio sends through ulai-agents, over the wire.
Also dialling, through ulai-api, against a fake HTTP transport."""

import json

import grpc
import httpx
import pytest
import ulai_agents as ua
from pydantic import SecretStr
from ulai.agent.v1 import agent_pb2 as pb
from ulai.agent.v1 import agent_pb2_grpc as rpc

from app.models import Agent, Opening
from app.ulai.gateway import SdkGateway, agent_server_address
from app.ulai.profile import build_agent, build_tools

from .conftest import AGENT


class AgentServer(rpc.RoomServicer, rpc.SessionServicer):
    def __init__(self) -> None:
        self.joins: list[pb.JoinRoomRequest] = []
        self.keys: list[str] = []
        self.tool_results: list[pb.ToolResult] = []

    async def Join(self, request, context):
        self.keys.append(dict(context.invocation_metadata()).get("x-api-key", ""))
        self.joins.append(request)
        return pb.JoinRoomResponse(room_id=request.room_id, participant_id=request.participant_id)

    async def Run(self, request_iterator, context):
        attach = await context.read()
        assert attach.attach.session_id == "sess-1" and not attach.attach.replay_history
        started = pb.SessionStarted(session_id="sess-1")
        await context.write(pb.ServerEvent(sequence=1, session_started=started))
        handled = await context.read()
        assert list(handled.handled_tools.names) == ["check_order"]
        call = pb.ToolCall(id="tc-1", name="check_order", args_json='{"order_id": "A-17"}')
        await context.write(pb.ServerEvent(sequence=2, tool_call=call))
        result = await context.read()
        self.tool_results.append(result.tool_result)
        ended = pb.SessionEnded(reason="caller hung up")
        await context.write(pb.ServerEvent(sequence=3, session_ended=ended))


@pytest.fixture
async def server():
    s = AgentServer()
    srv = grpc.aio.server()
    rpc.add_RoomServicer_to_server(s, srv)
    rpc.add_SessionServicer_to_server(s, srv)
    port = srv.add_insecure_port("127.0.0.1:0")
    await srv.start()
    s.url = f"http://127.0.0.1:{port}"
    yield s
    await srv.stop(None)


def _agent() -> Agent:
    body = {k: v for k, v in AGENT.items() if k != "variables"}
    return Agent(
        id="agent-1",
        **body,
        model="gemini-live-2.5-flash-native-audio",
        language="en-AU",  # not in this SDK version's list: Ulai judges it
        opening=Opening.CALLER,
        temperature=0.6,
        allow_interruptions=False,
        greeting_interruptible=True,
        silence_monitor=True,
        backchannel_gate=True,
        background_noise=False,
        voicemail_detection=True,
        max_call_duration_seconds=600,
        engagement_timeout_seconds=20,
        variables=[],
    )


async def test_join_sends_the_agent_and_the_room(settings, server):
    settings.ulai_agent_url = server.url
    gw = SdkGateway(settings)
    try:
        agent = build_agent(_agent(), settings, {"customer_name": "Ana"}, direction="outbound")
        await gw.join_agent("sess-1", agent, participant_id="agent-abc", fields={"call_id": "c1"})
    finally:
        await gw.close()

    (req,) = server.joins
    assert server.keys == ["ulai_test"]  # ULAI_AGENT_API_KEY falls back to ULAI_API_KEY
    assert req.room_id == "sess-1" and req.participant_id == "agent-abc"
    assert req.room_url == settings.ulai_cp_url and req.room_token == "ulai_test"
    assert json.loads(req.custom_fields_json) == {"call_id": "c1"}
    assert req.opening == pb.OPENING_TURN_CALLER
    p = req.profile
    assert p.prompt == "You help Ana with order ." and p.greeting == "Hi Ana!"
    assert p.voice == "Kore" and p.language == "en-AU" and p.model == "gemini-live-2.5-flash-native-audio"
    assert p.provider_project == "gcp-proj" and p.provider_credentials and p.provider_region == "us-central1"
    assert not p.allow_interruptions and p.amd_enabled and p.live_transcription
    assert p.max_call_duration_seconds == 600 and p.initial_engagement_deadline_ms == 20_000
    assert [t.name for t in p.tools] == ["check_order"] and list(p.tools[0].required) == ["order_id"]


async def test_attach_answers_tools_with_the_studios_handler(settings, server):
    settings.ulai_agent_url = server.url
    gw = SdkGateway(settings)
    asked: list[dict] = []

    async def answer(tool: dict, args: dict) -> dict:
        asked.append(args)
        return {"status": "shipped"}

    try:
        session = await gw.attach("sess-1", build_tools(AGENT["tools"], answer))
        kinds = [type(ev).__name__ async for ev in session.events()]
        await session.close()
    finally:
        await gw.close()

    assert kinds == ["ToolCall", "Ended"]
    assert asked == [{"order_id": "A-17"}]
    (result,) = server.tool_results
    assert result.id == "tc-1" and json.loads(result.result_json) == {"status": "shipped"}


def test_agent_server_address():
    assert agent_server_address("https://stgags.ulai.co") == ("stgags.ulai.co:443", True)
    assert agent_server_address("https://ags.example:8443/") == ("ags.example:8443", True)
    assert agent_server_address("http://127.0.0.1:50052") == ("127.0.0.1:50052", False)
    assert agent_server_address("ags.example:50052") == ("ags.example:50052", True)
    assert agent_server_address("localhost:50052") == ("localhost:50052", False)


def test_an_agent_without_google_credentials_is_refused_before_dialling(settings, tmp_path):
    settings.google_credentials_path = tmp_path / "missing.json"
    settings.__dict__.pop("google_credentials_json", None)
    agent = build_agent(_agent(), settings, {}, direction="web")
    with pytest.raises(ua.ValidationError, match="Agent.cloud"):
        agent.validate(allow_unlisted_values=True)


async def test_originate_dials_through_ulai_api_at_the_configured_url(settings, monkeypatch):
    settings.ulai_sip_originate_url = "https://sip.test/sip/originate"
    settings.ulai_system_secret = SecretStr("sys-secret")
    requests: list[httpx.Request] = []

    def ulai(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/v1/auth/me":
            return httpx.Response(200, json={"project_id": "proj-1"})
        return httpx.Response(200, json={})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.MockTransport(ulai), **kw)
    )
    gw = SdkGateway(settings)
    try:
        await gw.originate(session_id="sess-1", trunk_id="trunk-1", to_number="+1555", from_number="+1666")
    finally:
        await gw.close()

    dial = requests[-1]
    assert str(dial.url) == "https://sip.test/sip/originate"
    assert (
        dial.headers["authorization"] == "Bearer ulai_test"
        and dial.headers["x-system-secret"] == "sys-secret"
    )
    body = json.loads(dial.content)
    assert body["session_id"] == "sess-1" and body["trunk_id"] == "trunk-1" and body["project_id"] == "proj-1"
    assert (body["to_number"], body["from_number"]) == ("+1555", "+1666")
