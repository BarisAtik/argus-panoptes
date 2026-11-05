import pytest

pytest.importorskip("agentdojo")
pytest.importorskip("sklearn")

from gauntlet.task_router import covers, pick_tau, predict, task_scores  # noqa: E402

DOCS = {"send_money": "send money to a recipient iban", "get_balance": "get the account balance",
        "update_password": "update the user password", "read_file": "read a file"}
PROMPTS = ["pay my rent by sending money to the landlord", "send money to Bob", "change my password please"]
GOLD = [{"send_money"}, {"send_money"}, {"update_password"}]


def test_reads_are_not_routed():
    s = task_scores(PROMPTS, GOLD, DOCS, "docs")[0]
    assert set(s) == {"send_money", "update_password"}


def test_docs_prefers_the_matching_tool():
    s = task_scores(PROMPTS, GOLD, DOCS, "docs")[2]
    assert s["update_password"] > s["send_money"]


def test_history_excludes_the_task_itself():
    # With a lone task for this tool, leave-one-out must give the tool no score from itself.
    s = task_scores(PROMPTS, GOLD, DOCS, "history")[2]
    assert s["update_password"] == 0


def test_predict_keeps_reads_and_thresholds():
    assert predict({"send_money": 0.5, "update_password": 0.1}, list(DOCS), 0.3) == {"send_money", "get_balance", "read_file"}


def test_tau_is_the_strictest_that_meets_the_target():
    assert pick_tau({0.1: 0.95, 0.2: 0.91, 0.3: 0.7}) == 0.2
    assert pick_tau({0.1: 0.5, 0.2: 0.4}) == 0.1  # nothing meets it: fall back to most permissive


def test_covers():
    assert covers({"a", "b"}, {"a"}) and not covers({"a"}, {"a", "b"})
