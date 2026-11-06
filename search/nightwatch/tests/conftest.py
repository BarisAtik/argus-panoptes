import os

import pytest

from nightwatch.engine import Engine
from nightwatch.rules import parse_rule

RULE = """
title: Test Rule
id: 11111111-1111-4111-8111-111111111111
status: stable
level: high
date: 2020-01-02
tags:
  - attack.execution
  - attack.t1059.001
logsource:
  category: process_creation
  product: windows
detection:
  selection:
    Image|endswith: '\\\\cmd.exe'
    CommandLine|contains: 'whoami'
  filter:
    User: 'SYSTEM'
  condition: selection and not filter
"""


@pytest.fixture
def rule():
    return parse_rule(RULE, "rule.yml")


@pytest.fixture
def sysmon_event():
    return {
        "Channel": "Microsoft-Windows-Sysmon/Operational",
        "EventID": "1",
        "Image": "C:\\Windows\\System32\\CMD.EXE",
        "CommandLine": "cmd /c WhoAmI /all",
        "User": "LAB\\user",
    }


@pytest.fixture
def engine():
    if not os.environ.get("NIGHTWATCH_IT"):
        pytest.skip("set NIGHTWATCH_IT=1 and ES_URL to run against an engine")
    engine = Engine(
        os.environ.get("ES_URL", "http://localhost:9200"),
        os.environ.get("ES_USER"),
        os.environ.get("ELASTIC_PASSWORD"),
    )
    yield engine
    engine.client.delete("/nw-it-*")
