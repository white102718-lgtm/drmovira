from uuid import UUID

import pytest


def test_device_origin_rejects_untrusted_url_parts():
    from orbit_agent.adspower_status import ProbeError
    from orbit_agent.transport import device_origin

    for target in (
        "http://localhost:8443",
        "https://user:secret@localhost:8443",
        "https://localhost:8443/path",
        "https://localhost:8443?key=secret",
    ):
        with pytest.raises(ProbeError):
            device_origin(target)
    assert device_origin("https://localhost:8443") == "https://localhost:8443"


def test_ack_exact_current_agent_and_state():
    from orbit_agent.adspower_status import ProbeError
    from orbit_agent.transport import validate_ack

    agent = str(UUID(int=1))
    value = {"id": agent, "revision": 1, "state": "SUSPECT", "request_id": str(UUID(int=2))}
    assert validate_ack("heartbeat", value, agent) == value
    for change in (
        {"id": str(UUID(int=3))},
        {"state": "SUCCEEDED"},
        {"revision": True},
        {"cookie": "x"},
    ):
        with pytest.raises(ProbeError):
            validate_ack("heartbeat", value | change, agent)
