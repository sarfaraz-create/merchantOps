"""A merchant explanation must fail to publish if its recorded evidence contradicts it."""

import copy
import pytest
from merchantops.evidence import replay_evidence
from merchantops.refund_story import explain


def test_recorded_story_separates_approval_payment_and_advertising():
    stages = replay_evidence()["stages"]
    assert len(stages) == 6
    assert [s["story"]["actual"][1] for s in stages] == [
        7260,
        5260,
        5260,
        5260,
        4260,
        4260,
    ]
    assert [s["reconciliation"]["refund_payable"] for s in stages] == [
        0,
        2000,
        2000,
        0,
        0,
        0,
    ]
    assert stages[2]["ingestion"]["inserted_rows"] == 0
    assert stages[3]["story"]["actual"][3] == 2000
    assert stages[3]["story"]["actual"][5] == 0
    assert stages[4]["story"]["actual"][5] == 1000
    assert stages[5]["quarantined_batches"] == 1
    assert all(s["story"]["passed"] for s in stages)
    # A falsely changed figure must stop the build, not retain a green success label.
    corrupted = copy.deepcopy(stages[3])
    corrupted["reconciliation"]["returned"] = 0
    with pytest.raises(ValueError, match="failed its independent expected result"):
        explain(corrupted, 3)
