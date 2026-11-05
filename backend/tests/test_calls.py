import json
from types import SimpleNamespace

import httpx

from app.ulai.gateway import CallGone
from app.ulai.inbound import inbound_call
from app.ulai.profile import build_agent, render

from .conftest import AGENT, caller_arrived, ended, eventually, said, tool_call, usage


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

    # The agent got the rendered prompt, the Gemini credentials and the tool definitions.
    ((_, session_id, sent, _, fields),) = gateway.calls("join_agent")
    assert sent.id == agent["id"]
    assert sent.instructions == "You help Ana with order ."
    assert sent.greeting == "Hi Ana!"
    assert sent.voice == "Kore" and sent.cloud.project == "gcp-proj" and sent.cloud.credentials_json
    assert sent.tools[0].name == "check_order" and sent.tools[0].required == ["order_id"]
    assert fields["customer_name"] == "Ana"

    # Attached: the call is live, and we answer the agent's tools.
    await eventually(_status_is(client, web["call_id"], "in_progress"))
    assert gateway.calls("attach")[0][2] == ["check_order"]
    q = gateway.agent_queues[session_id]
    await q.put(said("agent", "Hi Ana!"))
    await q.put(said("caller", "Where is my ord", final=False))
    await q.put(said("caller", "Where is my order A-17?"))
    await q.put(tool_call("check_order", {"order_id": "A-17"}))

    session = gateway.sessions[0]

    async def tool_answered():
        return session.answers

    await eventually(tool_answered)
    assert session.answers == [("check_order", {"status": "shipped"})]

    await q.put(usage(1200, 300))
    await q.put(ended())
    call = await eventually(_status_is(client, web["call_id"], "completed"))

    assert call["end_reason"] == "caller hung up"
    assert call["usage"]["prompt_tokens"] == 1200
    lines = [(e["kind"], e["speaker"], e["text"]) for e in call["events"]]
    assert ("transcript", "agent", "Hi Ana!") in lines
    assert ("transcript", "caller", "Where is my order A-17?") in lines
    assert not any(t == "Where is my ord" for _, _, t in lines)  # interim text isn't stored
    tool = next(e for e in call["events"] if e["kind"] == "tool_call")
    assert tool["data"]["result"] == {"status": "shipped"} and tool["data"]["ok"]


async def test_a_dropped_agent_stream_is_reattached(client, agent, gateway):
    web = (await client.post("/api/calls/web", json={"agent_id": agent["id"]})).json()
    session_id = gateway.calls("join_agent")[0][1]
    q = gateway.agent_queues[session_id]
    await q.put(said("agent", "Hello"))
    await q.put(None)  # the stream drops

    async def reattached():
        return len(gateway.calls("attach")) >= 2

    await eventually(reattached, within=5)
    assert gateway.calls("attach")[1][2] == ["check_order"]  # still answering the agent's tools
    await q.put(said("caller", "Hi"))
    await q.put(ended())
    call = await eventually(_status_is(client, web["call_id"], "completed"), within=5)
    texts = [e["text"] for e in call["events"] if e["kind"] == "transcript"]
    assert texts == ["Hello", "Hi"]


async def test_a_call_ulai_lost_is_recorded_as_failed(client, agent, gateway):
    web = (await client.post("/api/calls/web", json={"agent_id": agent["id"]})).json()
    session_id = gateway.calls("join_agent")[0][1]
    await gateway.agent_queues[session_id].put(CallGone("the model failed to connect", failed=True))
    call = await eventually(_status_is(client, web["call_id"], "failed"))
    assert "the model failed to connect" in call["error"]
    assert len(gateway.calls("attach")) == 1  # not retried: the call is gone


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


async def test_an_inbound_caller_gets_the_rules_agent(client, agent, gateway, app):
    await client.post(
        "/api/trunks/inbound", json={"name": "Main", "numbers": ["+14155550100"], "agent_id": agent["id"]}
    )

    async def subscribed():
        return gateway.subscribed

    await eventually(subscribed)

    # Ignored: our own outbound leg, and a caller for an agent this studio doesn't have.
    await gateway.project_queue.put(
        caller_arrived("sess-out", agent["id"], "+14155550199", "+14155550777", direction="OUTBOUND")
    )
    await gateway.project_queue.put(caller_arrived("sess-other", "someone-elses-agent", "+1", "+2"))
    await gateway.project_queue.put(caller_arrived("sess-in-1", agent["id"], "+14155550777", "+14155550100"))

    async def attached():
        return gateway.calls("attach")

    ((_, session_id, tools),) = await eventually(attached)
    assert session_id == "sess-in-1" and tools == ["check_order"]
    # The studio put the agent in, as for an outbound call; defaults fill in its variables.
    ((_, joined_session, sent, _, fields),) = gateway.calls("join_agent")
    assert joined_session == "sess-in-1" and sent.id == agent["id"]
    assert sent.instructions == "You help there with order ."
    assert fields["direction"] == "inbound"

    calls = (await client.get("/api/calls", params={"direction": "inbound"})).json()["items"]
    assert len(calls) == 1
    assert calls[0]["from_number"] == "+14155550777" and calls[0]["status"] == "in_progress"
    assert calls[0]["trunk_id"]

    # The same caller announced twice (e.g. after the listener reconnects) is answered once.
    await gateway.project_queue.put(caller_arrived("sess-in-1", agent["id"], "+14155550777", "+14155550100"))
    await gateway.project_queue.put(caller_arrived("sess-in-2", agent["id"], "+14155550778", "+14155550100"))
    await eventually(lambda: _async(len(gateway.calls("join_agent")) == 2))
    assert [c[1] for c in gateway.calls("join_agent")] == ["sess-in-1", "sess-in-2"]


async def test_an_inbound_caller_is_hung_up_on_if_the_agent_cant_start(client, agent, gateway):
    await client.post(
        "/api/trunks/inbound", json={"name": "Main", "numbers": ["+14155550100"], "agent_id": agent["id"]}
    )
    await eventually(lambda: _async(gateway.subscribed))
    gateway.fail.add("join_agent")
    await gateway.project_queue.put(caller_arrived("sess-in-1", agent["id"], "+14155550777", "+14155550100"))
    await eventually(lambda: _async(gateway.calls("terminate_session")))
    call = (await client.get("/api/calls", params={"direction": "inbound"})).json()["items"][0]
    assert call["status"] == "failed" and "join_agent failed" in call["error"]


def test_inbound_call_reads_the_sip_gateways_metadata():
    msg = caller_arrived("s1", "agent-1", "+14155550777", "+14155550100")
    assert inbound_call(msg) == ("s1", "agent-1", "+14155550777", "+14155550100")
    # The rule's dispatch metadata names the agent when assigned_agent is empty.
    msg["metadata"] = {"assigned_agent": "", "studio_agent_id": "agent-2", "direction": "inbound"}
    assert inbound_call(msg)[1] == "agent-2"
    assert inbound_call({**msg, "type": "participant_left"}) is None
    assert inbound_call({**msg, "kind": "STANDARD"}) is None


async def _async(value):
    return value


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
        id="a1",
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
    assert build_agent(agent, settings, {}, direction="outbound").options.voicemail_detection is True
    assert build_agent(agent, settings, {}, direction="inbound").options.voicemail_detection is False


async def test_test_call_can_use_unsaved_edits(client, agent, gateway):
    draft = {**AGENT, "greeting": "Draft hello", "voice": "Puck", "opening": "caller"}
    resp = await client.post("/api/calls/web", json={"agent_id": agent["id"], "draft": draft})
    assert resp.status_code == 200, resp.text
    ((_, _, sent, _, _),) = gateway.calls("join_agent")
    assert sent.id == agent["id"]
    assert sent.greeting == "Draft hello" and sent.voice == "Puck" and sent.opening == "caller"
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
