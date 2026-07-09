"""Safety invariant: transmit=True may only ever appear in the one
paper-gated broker adapter branch. A grep test (the invariant is about
the codebase as a whole, not one function) plus behavioral tests against
a FakeIB proving the gate can't be fooled by the flag alone."""

import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace

from app.brokers.base import DraftLeg, DraftOrder
from app.brokers.ibkr_adapter import PAPER_PORTS, IBKRAdapter
from app.config import Settings

APP_ROOT = Path(__file__).resolve().parents[1] / "app"
ALLOWED_FILE = "brokers/ibkr_adapter.py"


def _is_literal_true(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value is True


def _sets_transmit_true(tree: ast.AST) -> bool:
    """AST, not grep: a docstring that merely *mentions* transmit=True
    (like ibkr/orders.py's own safety comment) must not trip this."""
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg == "transmit" and _is_literal_true(node.value):
            return True
        if isinstance(node, ast.Assign) and _is_literal_true(node.value):
            targets = node.targets
            if any(isinstance(t, ast.Attribute) and t.attr == "transmit" for t in targets):
                return True
    return False


def test_transmit_true_appears_only_in_the_guarded_broker_adapter():
    hits = []
    for path in APP_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        if _sets_transmit_true(tree):
            hits.append(str(path.relative_to(APP_ROOT.parent)))
    assert hits == [f"app/{ALLOWED_FILE}"], (
        f"transmit=True must appear only in app/{ALLOWED_FILE}; found in: {hits}"
    )


class FakeQualified:
    conId = 1


class FakeTrade:
    def __init__(self, order):
        self.order = order


class FakeIB:
    def __init__(self):
        self.placed = []

    async def qualifyContractsAsync(self, contract):
        return [FakeQualified()]

    def placeOrder(self, contract, order):
        order.orderId = len(self.placed) + 1
        self.placed.append(order)
        return FakeTrade(order)


class FakeClient:
    def __init__(self, port):
        self.settings = SimpleNamespace(ibkr_port=port)
        self.ib = FakeIB()

    def require(self):
        return self.ib


DRAFT = DraftOrder(
    legs=[
        DraftLeg("SPY", "OPT", "P", 95.0, "2026-08-21", "SELL", 1),
        DraftLeg("SPY", "OPT", "P", 90.0, "2026-08-21", "BUY", 1),
    ],
    quantity=1,
    limit_price=-0.60,
)


def test_paper_mode_with_flag_on_paper_port_transmits():
    client = FakeClient(port=4002)
    settings = Settings(ibkr_mode="paper", paper_auto_transmit=True)
    adapter = IBKRAdapter(client, settings)
    asyncio.run(adapter.place(DRAFT))
    assert client.ib.placed[-1].transmit is True


def test_live_mode_never_auto_transmits_even_with_flag_on():
    client = FakeClient(port=4002)
    settings = Settings(ibkr_mode="live", paper_auto_transmit=True)
    adapter = IBKRAdapter(client, settings)
    asyncio.run(adapter.place(DRAFT))
    assert client.ib.placed[-1].transmit is False


def test_paper_mode_with_flag_off_stages_only():
    client = FakeClient(port=4002)
    settings = Settings(ibkr_mode="paper", paper_auto_transmit=False)
    adapter = IBKRAdapter(client, settings)
    asyncio.run(adapter.place(DRAFT))
    assert client.ib.placed[-1].transmit is False


def test_paper_mode_flag_on_but_wrong_port_refuses_to_transmit():
    # a misconfigured port (e.g. pointed at live 4001 while ibkr_mode
    # still says "paper") must not fire a live order on the mode string alone
    client = FakeClient(port=4001)
    settings = Settings(ibkr_mode="paper", paper_auto_transmit=True)
    adapter = IBKRAdapter(client, settings)
    asyncio.run(adapter.place(DRAFT))
    assert client.ib.placed[-1].transmit is False


def test_paper_ports_constant_matches_documented_ports():
    assert PAPER_PORTS == frozenset({4002, 7497})
