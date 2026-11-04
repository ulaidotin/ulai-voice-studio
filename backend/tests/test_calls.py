import json
from types import SimpleNamespace

import httpx

from app.ulai.profile import build_profile, render

from .conftest import AGENT, ended, eventually, said, started, tool_call, usage


async def _call(client, call_id):
    return (await client.get(f"/api/calls/{call_id}")).json()


def _status_is(client, call_id, *statuses):
    async def check():
        call = await _call(client, call_id)
        return call if call["status"] in statuses else None

    return check


async def test_web_call_end_to_end(client, agent, gateway, app):
    # Tool webhooks are answered by a stub service.
    def tool_service(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["arguments"] == {"order_id": "A-17"}
        return httpx.Response(200, json={"status": "shipped"})

    app.state.services.calls.http = httpx.AsyncClient(transport=httpx.MockTransport(tool_service))

    resp = await client.post(
        "/api/calls/web", json={"agent_id": agent["id"], "variables": {"customer_name": "Ana"}}
    )
    assert resp.status_code == 200, resp.text
    web = resp.json()
    assert web["ticket"] == "ticket-1" and web["node_address"] == "node.example:443"
    assert web["ice_servers"][0]["urls"] == ["stun:stun.l.google.com:19302"]

    # The agent got the rendered profile, the Gemini credentials and the tool definitions.
    ((_, session_id, agent_id, _, profile, custom),) = gateway.calls("join_agent")
    assert agent_id == agent["id"]
    assert profile["prompt"] == "You help Ana with order ."
    assert profile["greeting"] == "Hi Ana!"
    assert profile["voice"] == "Kore" and profile["gemini_project_id"] == "gcp-proj"
    assert profile["google_credentials_json"]
    assert profile["tools"][0]["required"] == ["order_id"]
    assert custom["customer_name"] == "Ana"

    q = gateway.agent_queues[session_id]
    await q.put(started())
    await eventually(_status_is(client, web["call_id"], "in_progress"))
    await q.put(said(2, "agent", "Hi Ana!"))
    await q.put(said(3, "caller", "Where is my ord", final=False))
    await q.put(said(4, "caller", "Where is my order A-17?"))
    await q.put(tool_call(5, "check_order", {"order_id": "A-17"}))

    stream = gateway.streams[0]
    assert gateway.calls("attach")[0][3] == ["check_order"]  # told Ulai we answer this tool

    async def tool_answered():
        return stream.sent

    await eventually(tool_answered)
    result = stream.sent[0].tool_result
    assert result.name == "check_order" and json.loads(result.result_json) == {"status": "shipped"}

    await q.put(usage(6, 1200, 300))
    await q.put(ended(7))
    call = await eventually(_status_is(client, web["call_id"], "completed"))

    assert call["end_reason"] == "caller hung up"
    assert call["usage"]["prompt_tokens"] == 1200
    lines = [(e["kind"], e["speaker"], e["text"]) for e in call["events"]]
    assert ("transcript", "agent", "Hi Ana!") in lines
    assert ("transcript", "caller", "Where is my order A-17?") in lines
    assert not any(t == "Where is my ord" for _, _, t in lines)  # interim text isn't stored
    tool = next(e for e in call["events"] if e["kind"] == "tool_call")
    assert tool["data"]["result"] == {"status": "shipped"} and tool["data"]["ok"]


async def test_reattaching_does_not_duplicate_the_transcript(client, agent, gateway):
    web = (await client.post("/api/calls/web", json={"agent_id": agent["id"]})).json()
    session_id = gateway.calls("join_agent")[0][1]
    q = gateway.agent_queues[session_id]
    await q.put(started())
    await q.put(said(2, "agent", "Hello"))
    await q.put(None)  # the stream drops

    # On re-attach Ulai replays history; already-stored lines must be skipped.
    async def reattached():
        return len(gateway.calls("attach")) >= 2

    await eventually(reattached, within=5)
    await q.put(started())
    await q.put(said(2, "agent", "Hello"))
    await q.put(said(3, "caller", "Hi"))
    await q.put(ended(4))
    call = await eventually(_status_is(client, web["call_id"], "completed"), within=5)
    texts = [e["text"] for e in call["events"] if e["kind"] == "transcript"]
    assert texts == ["Hello", "Hi"]


async def _outbound_setup(client):
    trunk = (
        await client.post(
            "/api/trunks/outbound",
            json={"name": "T", "address": "sip.example.com", "numbers": ["+14155550199"]},
        )
    ).json()
    return trunk


async def test_outbound_call_rings_then_answers(client, agent, gateway):
    trunk = await _outbound_setup(client)
    resp = await client.post(
        "/api/calls/outbound",
        json={"agent_id": agent["id"], "trunk_id": trunk["id"], "to_number": "+44 20 7946 0958"},
    )
    assert resp.status_code == 201, resp.text
    call = resp.json()
    assert call["status"] == "ringing" and call["from_number"] == "+14155550199"
    assert call["to_number"] == "+442079460958"

    # The agent joins before we dial, so it's there when the callee picks up.
    names = [entry[0] for entry in gateway.log]
    assert names.index("join_agent") < names.index("originate")
    ((_, session_id, remote_trunk, to, frm),) = gateway.calls("originate")
    assert remote_trunk.startswith("out-") and to == "+442079460958" and frm == "+14155550199"

    await gateway.session_queues[session_id].put({"type": "participant_joined", "kind": "SIP", "id": "e1"})
    answered = await eventually(_status_is(client, call["id"], "in_progress"))
    assert answered["answered_at"]

    await gateway.session_queues[session_id].put({"type": "session_terminated", "id": "e2"})
    done = await eventually(_status_is(client, call["id"], "completed"))
    assert done["duration_seconds"] is not None


async def test_unanswered_outbound_call_times_out(client, agent, gateway, app, settings):
    settings.ring_timeout_seconds = 0
    trunk = await _outbound_setup(client)
    call = (
        await client.post(
            "/api/calls/outbound",
            json={"agent_id": agent["id"], "trunk_id": trunk["id"], "to_number": "+14155550123"},
        )
    ).json()
    done = await eventually(_status_is(client, call["id"], "no_answer"))
    assert "No answer" in done["end_reason"]
    assert gateway.calls("terminate_session")


async def test_outbound_call_validation(client, agent):
    trunk = await _outbound_setup(client)
    bad_from = await client.post(
        "/api/calls/outbound",
        json={
            "agent_id": agent["id"],
            "trunk_id": trunk["id"],
            "to_number": "+14155550123",
            "from_number": "+14155550000",
        },
    )
    assert bad_from.status_code == 422
    bad_to = await client.post(
        "/api/calls/outbound", json={"agent_id": agent["id"], "trunk_id": trunk["id"], "to_number": "12345"}
    )
    assert bad_to.status_code == 422


async def test_failed_dial_is_recorded_and_the_session_closed(client, agent, gateway):
    trunk = await _outbound_setup(client)
    gateway.fail.add("originate")
    resp = await client.post(
        "/api/calls/outbound",
        json={"agent_id": agent["id"], "trunk_id": trunk["id"], "to_number": "+14155550123"},
    )
    assert resp.status_code == 502
    call = (await client.get("/api/calls")).json()["items"][0]
    assert call["status"] == "failed" and "originate failed" in call["error"]
    assert gateway.calls("terminate_session")


async def test_inbound_assignment_is_answered_with_the_agents_profile(client, agent, gateway, app):
    await client.post(
        "/api/trunks/inbound", json={"name": "Main", "numbers": ["+14155550100"], "agent_id": agent["id"]}
    )

    async def subscribed():
        return gateway.subscribed and gateway.subscribed[-1] == [agent["id"]]

    await eventually(subscribed)

    info = SimpleNamespace(agent_id=agent["id"], from_number="+14155550777", to_number="+14155550100")
    await gateway.assignment_queue.put(SimpleNamespace(session_id="sess-in-1", call=info))

    async def attached():
        return gateway.calls("attach")

    ((_, session_id, profile, tools),) = await eventually(attached)
    assert session_id == "sess-in-1"
    assert profile["prompt"] == "You help there with order ."  # defaults fill in for inbound calls
    assert tools == ["check_order"]

    calls = (await client.get("/api/calls", params={"direction": "inbound"})).json()["items"]
    assert calls[0]["from_number"] == "+14155550777" and calls[0]["status"] == "in_progress"
    assert calls[0]["trunk_id"]


async def test_end_call_from_the_studio(client, agent, gateway):
    web = (await client.post("/api/calls/web", json={"agent_id": agent["id"]})).json()
    resp = await client.post(f"/api/calls/{web['call_id']}/end")
    assert resp.status_code == 200 and resp.json()["status"] == "completed"
    assert gateway.calls("leave_agent") and gateway.calls("terminate_session")


async def test_list_filters_and_csv_export(client, agent, gateway):
    await client.post("/api/calls/web", json={"agent_id": agent["id"]})
    assert (await client.get("/api/calls", params={"direction": "web"})).json()["total"] == 1
    assert (await client.get("/api/calls", params={"direction": "inbound"})).json()["total"] == 0
    assert (await client.get("/api/calls", params={"q": "Support"})).json()["total"] == 1
    csv = await client.get("/api/calls/export.csv")
    assert csv.headers["content-type"].startswith("text/csv") and "Support" in csv.text


async def test_overview_and_health(client, agent):
    await client.post("/api/calls/web", json={"agent_id": agent["id"]})
    ov = (await client.get("/api/overview")).json()
    assert ov["calls_today"] == 1 and ov["agents"] == 1 and len(ov["daily"]) == 7
    assert sum(d["web"] for d in ov["daily"]) == 1
    health = (await client.get("/api/health")).json()
    assert health["ulai"] == "ok" and health["google_credentials"] is True


def test_placeholders():
    values = {"name": "Ana"}
    assert render("Hi {{ name }}, {{missing}}!", values) == "Hi Ana, !"


def test_voicemail_detection_only_on_outbound(settings):
    agent = SimpleNamespace(
        prompt="",
        greeting="",
        closing="",
        opening=SimpleNamespace(value="agent"),
        model="m",
        voice="Puck",
        language="",
        temperature=0.5,
        allow_interruptions=True,
        greeting_interruptible=True,
        silence_monitor=True,
        backchannel_gate=True,
        background_noise=False,
        voicemail_detection=True,
        max_call_duration_seconds=60,
        engagement_timeout_seconds=10,
        tools=[],
    )
    assert build_profile(agent, settings, {}, direction="outbound")["amd_enabled"] is True
    assert build_profile(agent, settings, {}, direction="inbound")["amd_enabled"] is False


async def test_test_call_can_use_unsaved_edits(client, agent, gateway):
    draft = {**AGENT, "greeting": "Draft hello", "voice": "Puck", "opening": "caller"}
    resp = await client.post("/api/calls/web", json={"agent_id": agent["id"], "draft": draft})
    assert resp.status_code == 200, resp.text
    ((_, _, agent_id, _, profile, _),) = gateway.calls("join_agent")
    assert agent_id == agent["id"]
    assert (
        profile["greeting"] == "Draft hello" and profile["voice"] == "Puck" and profile["opening"] == "caller"
    )
    # The saved agent is untouched.
    saved = (await client.get(f"/api/agents/{agent['id']}")).json()
    assert saved["greeting"] == AGENT["greeting"] and saved["voice"] == "Kore"


async def test_catalog_lists_builtin_variables(client):
    cat = (await client.get("/api/catalog")).json()
    assert {v["name"] for v in cat["builtin_variables"]} == {
        "caller_number",
        "call_direction",
        "current_date",
        "current_time_utc",
    }
    assert cat["voices"] and cat["models"] and cat["languages"][0]["id"] == ""


async def test_timestamps_are_utc_even_on_sqlite(client, agent):
    # SQLite drops the timezone; the API must still say UTC, or browsers read it as local time.
    assert agent["created_at"].endswith(("+00:00", "Z"))
    await client.post("/api/calls/web", json={"agent_id": agent["id"]})
    listed = (await client.get("/api/calls")).json()["items"][0]
    assert listed["created_at"].endswith(("+00:00", "Z")), listed["created_at"]
