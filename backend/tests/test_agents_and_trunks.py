from .conftest import AGENT


async def test_agent_crud(client, agent):
    assert agent["voice"] == "Kore" and agent["model"] == "gemini-live-2.5-flash-native-audio"

    listed = (await client.get("/api/agents")).json()
    assert [a["id"] for a in listed] == [agent["id"]]

    updated = await client.put(
        f"/api/agents/{agent['id']}", json={**AGENT, "name": "Sales", "temperature": 0.3}
    )
    assert updated.status_code == 200 and updated.json()["name"] == "Sales"

    copy = await client.post(f"/api/agents/{agent['id']}/duplicate")
    assert copy.status_code == 201 and copy.json()["name"] == "Sales (copy)"
    assert copy.json()["tools"] == updated.json()["tools"]

    assert (await client.delete(f"/api/agents/{agent['id']}")).status_code == 204
    assert (await client.get(f"/api/agents/{agent['id']}")).status_code == 404


async def test_agent_validation(client):
    cases = [
        {**AGENT, "voice": "NotAVoice"},
        {**AGENT, "language": "xx-XX"},
        {**AGENT, "variables": [{"name": "a"}, {"name": "a"}]},
        {**AGENT, "variables": [{"name": "1bad"}]},
        {**AGENT, "tools": [{**AGENT["tools"][0], "name": "has space"}]},
        {**AGENT, "temperature": 3},
    ]
    for body in cases:
        assert (await client.post("/api/agents", json=body)).status_code == 422


async def test_inbound_trunk_routes_its_numbers_to_the_agent(client, agent, gateway):
    resp = await client.post(
        "/api/trunks/inbound",
        json={"name": "Main line", "numbers": ["+1 415 555 0100"], "agent_id": agent["id"]},
    )
    assert resp.status_code == 201, resp.text
    trunk = resp.json()
    assert trunk["numbers"] == ["+14155550100"]  # normalised to E.164
    assert trunk["agent"] == {"id": agent["id"], "name": agent["name"]}
    ((_, _, routed_agent, remote_trunk),) = gateway.calls("create_rule")
    assert routed_agent == agent["id"] and remote_trunk.startswith("in-")

    # The agent list shows which numbers ring it.
    assert (await client.get("/api/agents")).json()[0]["inbound_numbers"] == ["+14155550100"]

    # Unassigning removes the routing rule on Ulai.
    resp = await client.patch(f"/api/trunks/{trunk['id']}", json={"agent_id": None})
    assert resp.json()["agent"] is None
    assert len(gateway.calls("delete_rule")) == 1


async def test_a_number_can_only_ring_one_trunk(client):
    body = {"name": "A", "numbers": ["+14155550100"]}
    assert (await client.post("/api/trunks/inbound", json=body)).status_code == 201
    resp = await client.post("/api/trunks/inbound", json={**body, "name": "B"})
    assert resp.status_code == 409 and "+14155550100" in resp.json()["detail"]


async def test_deleting_an_agent_unroutes_its_numbers_first(client, agent, gateway):
    await client.post(
        "/api/trunks/inbound", json={"name": "A", "numbers": ["+14155550100"], "agent_id": agent["id"]}
    )
    assert (await client.delete(f"/api/agents/{agent['id']}")).status_code == 204
    assert len(gateway.calls("delete_rule")) == 1
    assert (await client.get("/api/trunks")).json()[0]["agent"] is None


async def test_outbound_trunk_never_stores_the_password(client, gateway):
    resp = await client.post(
        "/api/trunks/outbound",
        json={
            "name": "Twilio",
            "address": "x.pstn.twilio.com",
            "transport": "tls",
            "username": "u",
            "password": "secret-pw",
            "numbers": ["+14155550199"],
        },
    )
    assert resp.status_code == 201
    assert "secret-pw" not in resp.text
    assert gateway.calls("create_outbound_trunk")[0][-1] == "secret-pw"  # passed on to Ulai

    # A blank password on edit means "keep the current one".
    await client.patch(
        f"/api/trunks/{resp.json()['id']}", json={"address": "y.pstn.twilio.com", "password": ""}
    )
    ((_, _, fields),) = gateway.calls("update_outbound_trunk")
    assert fields == {"address": "y.pstn.twilio.com"}


async def test_ulai_failures_surface_as_502_and_leave_nothing_behind(client, gateway):
    gateway.fail.add("create_outbound_trunk")
    resp = await client.post(
        "/api/trunks/outbound",
        json={"name": "T", "address": "sip.example.com", "numbers": ["+14155550199"]},
    )
    assert resp.status_code == 502 and "failed" in resp.json()["detail"]
    assert (await client.get("/api/trunks")).json() == []


async def test_inbound_listener_recovers_to_idle_when_routing_is_removed(client, agent, app, gateway):
    from .conftest import eventually

    listener = app.state.services.inbound
    failing = True

    async def assignments(agent_ids):
        gateway.subscribed.append(agent_ids)
        if failing:
            raise RuntimeError("UNAUTHENTICATED invalid api key")
        yield  # pragma: no cover

    gateway.assignments = assignments
    trunk = (
        await client.post(
            "/api/trunks/inbound", json={"name": "A", "numbers": ["+14155550100"], "agent_id": agent["id"]}
        )
    ).json()

    async def errored():
        return listener.state == "error"

    await eventually(errored)
    # Let it reach a long back-off, then unassign: it should settle to idle right away, not after the wait.
    await eventually(lambda: _async(len(gateway.subscribed) >= 3), within=10)
    await client.patch(f"/api/trunks/{trunk['id']}", json={"agent_id": None})

    async def idle():
        return listener.state == "idle"

    await eventually(idle, within=2)


async def _async(value):
    return value
