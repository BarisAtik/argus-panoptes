from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]


def compose():
    return yaml.safe_load((ROOT / "docker-compose.yml").read_text())


def test_every_published_port_is_local_only():
    for service in compose()["services"].values():
        assert all(port.startswith("127.0.0.1:") for port in service.get("ports", []))


def test_security_is_on_and_license_is_basic():
    environment = compose()["services"]["elasticsearch"]["environment"]
    assert environment["xpack.security.enabled"] == "true"
    assert environment["xpack.license.self_generated.type"] == "basic"


def test_passwords_must_be_supplied():
    text = (ROOT / "docker-compose.yml").read_text()
    assert "${ELASTIC_PASSWORD:?" in text
    assert "${KIBANA_PASSWORD:?" in text


def test_example_env_holds_only_placeholders():
    for line in (ROOT / ".env.example").read_text().splitlines():
        if "PASSWORD=" in line or "KEY=" in line:
            value = line.split("=", 1)[1]
            assert value == "" or value.startswith("change-me"), line
