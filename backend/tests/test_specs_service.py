"""Service-layer tests: spec persistence round trip, versioning, and
the approval gate (unspecified exits cannot be approved)."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.db import session as db_session
from app.specs import service
from app.specs.schema import ExitRules
from app.specs.seed import SEED_SLUG, seed_default_specs
from tests.test_spec_schema import sample_spec


@pytest.fixture(autouse=True)
def temp_db(tmp_path):
    db_session.init_db(Settings(db_url=f"sqlite:///{tmp_path}/test.db"))
    yield
    db_session._engine = None


def test_create_and_get_round_trip():
    record = service.create_spec(sample_spec())
    found = service.get_spec(record.id)
    assert found is not None
    stored_record, version = found
    assert stored_record.slug == "45-dte-put-credit-spread"
    # stop loss unstated -> created as needs_review
    assert stored_record.status == "needs_review"
    assert stored_record.section_status["exit"] == "partial"
    assert version.spec() == sample_spec()


def test_add_version_increments_and_updates_current():
    record = service.create_spec(sample_spec())
    updated = sample_spec(
        exit=ExitRules(
            profit_target_pct_credit=50.0, stop_loss_x_credit=2.0, time_exit_dte=21
        )
    )
    v2 = service.add_version(record.id, updated)
    assert v2.version == 2
    stored_record, version = service.get_spec(record.id)
    assert stored_record.current_version_id == v2.id
    assert version.spec().exit.stop_loss_x_credit == 2.0
    assert stored_record.section_status["exit"] == "defined"


def test_approve_blocked_while_exits_unspecified():
    record = service.create_spec(sample_spec())
    with pytest.raises(ValueError, match="stop_loss_x_credit"):
        service.approve_spec(record.id)
    # resolve the exits, then approval succeeds
    service.add_version(
        record.id,
        sample_spec(
            exit=ExitRules(
                profit_target_pct_credit=50.0, stop_loss_x_credit=2.0, time_exit_dte=21
            )
        ),
    )
    approved = service.approve_spec(record.id)
    assert approved.status == "approved"


def test_slug_collision_gets_suffix():
    a = service.create_spec(sample_spec())
    b = service.create_spec(sample_spec())
    assert a.slug != b.slug
    assert b.slug.startswith(a.slug)


def test_seed_is_idempotent():
    seed_default_specs()
    seed_default_specs()
    seeded = [r for r in service.list_specs() if r.slug == SEED_SLUG]
    assert len(seeded) == 1
    _, version = service.get_spec(seeded[0].id)
    spec = version.spec()
    assert spec.exit.profit_target_pct_credit == 50.0
    assert spec.exit.time_exit_dte == 21


def test_list_filters():
    service.create_spec(sample_spec())
    assert service.list_specs(origin="manual")
    assert not service.list_specs(origin="corpus")
    assert service.list_specs(status="needs_review")
