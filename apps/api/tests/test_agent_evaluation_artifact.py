"""Evaluation receipts cannot reuse an older success after an interrupted attempt."""

import asyncio
import importlib.util
import json
from pathlib import Path

import pytest


@pytest.mark.parametrize("interrupted", [False, True])
def test_evaluation_replaces_stale_receipt_and_labels_quality(tmp_path, monkeypatch, interrupted):
    spec = importlib.util.spec_from_file_location(
        "workbench_evaluation", Path(__file__).with_name("evaluate_agent_workbench.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    target = tmp_path / "result.json"
    target.write_text('{"completed":true,"old_success":true}')
    original_validate = module.provider.validate_output
    calls = []

    async def generate(kind, brief, sources, config):
        receipt = json.loads(target.read_text())
        assert receipt["completed"] is False
        assert "old_success" not in receipt
        calls.append(kind)
        if interrupted:
            raise asyncio.CancelledError
        raise ValueError("synthetic private failure must not enter artifact")

    monkeypatch.setattr(module.provider, "generate", generate)
    try:
        if interrupted:
            with pytest.raises(asyncio.CancelledError):
                asyncio.run(module.evaluate(target))
        else:
            with pytest.raises(SystemExit):
                asyncio.run(module.evaluate(target))
    finally:
        restored = module.provider.validate_output is original_validate
        module.provider.validate_output = original_validate
    assert restored
    assert module.provider.validate_output is original_validate
    receipt = json.loads(target.read_text())
    assert receipt["completed"] is (not interrupted)
    assert receipt["quality_acceptance"] == "not_assessed_by_script"
    assert len(calls) == (1 if interrupted else 4)
    assert len(receipt["cases"]) == (0 if interrupted else 4)
    assert "synthetic private failure" not in target.read_text()
    assert not target.with_suffix(".json.tmp").exists()
    for case in receipt["cases"]:
        assert not case["passed"]
        assert case["brief"] and "sources" in case
