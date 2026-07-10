"""backtest_run job queue: claim/result/fail idempotency — the worker
protocol as a pure DB state machine, no worker process involved."""

import pytest

from app.backtests import service
from app.backtests.service import JobQueueError
from app.config import Settings
from app.db import session as db_session
from app.db.session import init_db


@pytest.fixture(autouse=True)
def temp_db(tmp_path):
    init_db(Settings(db_url=f"sqlite:///{tmp_path}/test.db"))
    yield
    db_session._engine = None


def test_claim_returns_the_oldest_queued_job_for_the_engine():
    service.enqueue(spec_id=1, engine="optopsy", params={"a": 1})
    service.enqueue(spec_id=1, engine="optopsy", params={"a": 2})
    claimed = service.claim("optopsy")
    assert claimed["params"] == {"a": 1}


def test_claim_marks_the_job_running_so_it_is_not_claimed_twice():
    service.enqueue(spec_id=1, engine="optopsy", params={})
    first = service.claim("optopsy")
    second = service.claim("optopsy")
    assert first is not None
    assert second is None


def test_claim_ignores_jobs_for_a_different_engine():
    service.enqueue(spec_id=1, engine="oo_manual", params={})
    assert service.claim("optopsy") is None


def test_claim_returns_none_when_queue_is_empty():
    assert service.claim("optopsy") is None


def test_record_result_transitions_running_to_done():
    run_id = service.enqueue(spec_id=1, engine="optopsy", params={})
    service.claim("optopsy")
    service.record_result(run_id, metrics={"cagr": 0.1}, trades=[], equity_curve=[10000], engine_raw={})
    # queue is now empty for this engine
    assert service.claim("optopsy") is None


def test_record_result_on_a_non_running_job_raises():
    run_id = service.enqueue(spec_id=1, engine="optopsy", params={})
    with pytest.raises(JobQueueError, match="not running"):
        service.record_result(run_id, metrics={}, trades=[], equity_curve=[], engine_raw={})


def test_record_result_twice_raises_on_the_second_call():
    run_id = service.enqueue(spec_id=1, engine="optopsy", params={})
    service.claim("optopsy")
    service.record_result(run_id, metrics={}, trades=[], equity_curve=[], engine_raw={})
    with pytest.raises(JobQueueError):
        service.record_result(run_id, metrics={}, trades=[], equity_curve=[], engine_raw={})


def test_record_failure_transitions_running_to_failed():
    run_id = service.enqueue(spec_id=1, engine="optopsy", params={})
    service.claim("optopsy")
    service.record_failure(run_id, "worker crashed")
    assert service.claim("optopsy") is None


def test_record_failure_is_idempotent_when_already_failed():
    run_id = service.enqueue(spec_id=1, engine="optopsy", params={})
    service.claim("optopsy")
    service.record_failure(run_id, "first error")
    service.record_failure(run_id, "second error")  # must not raise


def test_record_failure_after_done_raises():
    run_id = service.enqueue(spec_id=1, engine="optopsy", params={})
    service.claim("optopsy")
    service.record_result(run_id, metrics={}, trades=[], equity_curve=[], engine_raw={})
    with pytest.raises(JobQueueError, match="already completed"):
        service.record_failure(run_id, "too late")


def test_unknown_run_id_raises():
    with pytest.raises(JobQueueError, match="not found"):
        service.record_result(999, metrics={}, trades=[], equity_curve=[], engine_raw={})
