import pytest
from app.db import engine
from app.models import AuditEvent
from app.modules.agent_workbench.learning import LESSONS, VERSION
from app.modules.agent_workbench.models import AgentRun
from sqlalchemy import func, select
from sqlalchemy.orm import Session


def test_training_auth_and_shared_versioned_content_without_model(world):
    client, headers, *_ = world
    assert client.get("/api/v1/agent-workbench/lessons").status_code == 401
    for token in headers:
        response = client.get("/api/v1/agent-workbench/lessons", headers=token)
        assert response.status_code == 200
        body = response.json()
        assert body["version"] == VERSION
        assert not body["generated_by_model"] and not body["progress_persisted"]
        assert len(body["lessons"]) == 3
        for lesson in body["lessons"]:
            assert lesson["reference"].startswith("docs/")
            assert all("answer" not in q and "explanation" not in q for q in lesson["questions"])


def test_self_checks_give_correct_feedback_and_never_write_business_or_progress(world):
    client, headers, *_ = world
    with Session(engine()) as db:
        before = [db.scalar(select(func.count()).select_from(m)) for m in (AgentRun, AuditEvent)]
    for lesson in LESSONS:
        path = f"/api/v1/agent-workbench/lessons/{lesson['id']}/check"
        answers = {q["id"]: q["answer"] for q in lesson["questions"]}
        assert client.post(path, json={"version": VERSION, "answers": answers}).status_code == 401
        # A viewer may learn; this read-only computation grants no domain write permission.
        correct = client.post(
            path, headers=headers[2], json={"version": VERSION, "answers": answers}
        ).json()
        assert correct["correct_count"] == correct["question_count"] == len(answers)
        assert all(q["correct"] for q in correct["feedback"])
        assert not correct["progress_persisted"] and not correct["financial_approval"]
        wrong = {q["id"]: (q["answer"] + 1) % len(q["options"]) for q in lesson["questions"]}
        response = client.post(
            path, headers=headers[0], json={"version": VERSION, "answers": wrong}
        )
        assert response.status_code == 200
        assert response.json()["correct_count"] == 0
        assert all(q["explanation"] for q in response.json()["feedback"])
        assert (
            client.post(
                path, headers=headers[0], json={"version": VERSION, "answers": wrong}
            ).json()
            == response.json()
        )
    with Session(engine()) as db:
        assert before == [
            db.scalar(select(func.count()).select_from(m)) for m in (AgentRun, AuditEvent)
        ]


@pytest.mark.parametrize(
    "answers",
    [
        {"owner": 0},
        {"owner": 0, "move": 1, "extra": 0},
        {"owner": -1, "move": 1},
        {"owner": 3, "move": 1},
        {"owner": True, "move": 1},
        {"owner": "0", "move": 1},
    ],
)
def test_invalid_self_checks_fail_closed(world, answers):
    client, headers, *_ = world
    response = client.post(
        "/api/v1/agent-workbench/lessons/ownership/check",
        headers=headers[0],
        json={"version": VERSION, "answers": answers},
    )
    assert response.status_code == 422


def test_unknown_lesson_and_arbitrary_organization_input(world):
    client, headers, orgs, *_ = world
    assert (
        client.post(
            "/api/v1/agent-workbench/lessons/unknown/check",
            headers=headers[0],
            json={"version": VERSION, "answers": {"owner": 0}},
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/v1/agent-workbench/lessons/ownership/check",
            headers=headers[0],
            json={
                "version": VERSION,
                "answers": {"owner": 0, "move": 1},
                "organization_id": orgs[1],
            },
        ).status_code
        == 422
    )


@pytest.mark.parametrize("version", [None, "old-course-version"])
def test_version_mismatch_never_grades_a_different_curriculum(world, version):
    client, headers, *_ = world
    body = {"answers": {"owner": 0, "move": 1}}
    if version is not None:
        body["version"] = version
    response = client.post(
        "/api/v1/agent-workbench/lessons/ownership/check", headers=headers[0], json=body
    )
    assert response.status_code == 422
