import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from app.db import SessionLocal
from app.main import app
from app.models.loop_entities import ChapterLoopRun, ModelCall, RunStep


ORIGINAL_CONTENT = "人工正文，审批前不得覆盖。"


class StabilityMockHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        prompt = payload.get("messages", [{}])[0].get("content", "")
        chapter_match = re.search(r"章节 ID：([^\n]+)", prompt)
        chapter_id = chapter_match.group(1).strip() if chapter_match else ""
        mode = getattr(self.server, "mode", "normal")

        if mode == "timeout":
            time.sleep(5.5)

        if "AGENT: revision_writer" in prompt:
            content = json.dumps(
                {
                    "chapter_id": chapter_id,
                    "draft_markdown": "修订版本：林澈按用户反馈补充了锁死期间的纸质记录。",
                    "scene_breakdown": [],
                    "self_notes": ["已响应人工反馈"],
                },
                ensure_ascii=False,
            )
        elif "AGENT: draft_writer" in prompt:
            if mode == "markdown":
                content = "林澈推开下层档案室的铁门，潮湿纸张的气味扑面而来。午夜锁死留下的七分钟空白仍在墙钟上无声跳动。"
            elif mode == "invalid-draft-json":
                content = (
                    '{"chapter_id":"legacy","draft_markdown":"林澈推开下层档案室的铁门，'
                    '在纸质记录里发现午夜锁死持续了整整七分钟。",'
                    '"scene_breakdown":[}'
                )
            elif mode == "error-text":
                content = "Error: model unavailable and unable to generate the requested chapter draft."
            else:
                draft = "" if mode == "empty" else "初稿版本：林澈在下层记录了午夜七分钟锁死。"
                content = json.dumps(
                    {
                        "chapter_id": chapter_id,
                        "draft_markdown": draft,
                        "scene_breakdown": [],
                        "self_notes": [],
                    },
                    ensure_ascii=False,
                )
        elif "AGENT: continuity_checker" in prompt:
            if mode == "schema":
                content = json.dumps(
                    {"passed": True, "severity": 123, "issues": []},
                    ensure_ascii=False,
                )
            else:
                content = json.dumps(
                    {"passed": True, "severity": "none", "issues": []},
                    ensure_ascii=False,
                )
        else:
            content = json.dumps({"unexpected": True})

        body = json.dumps(
            {
                "choices": [{"message": {"role": "assistant", "content": content}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50},
            }
        ).encode()
        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def log_message(self, _format, *_args):
        return


def create_case(client, server_port, suffix, timeout_seconds=5):
    project = client.post("/api/projects", json={"name": "Stability {}".format(suffix)}).json()
    novel = client.post(
        "/api/novels",
        json={
            "project_id": project["id"],
            "title": "稳定性测试 {}".format(suffix),
            "story_outline": "林澈调查潮汐城午夜锁死。",
        },
    ).json()
    chapter = client.post(
        "/api/chapters",
        json={
            "novel_id": novel["id"],
            "title": "第一章",
            "content": ORIGINAL_CONTENT,
            "outline": {
                "goal": "记录午夜锁死",
                "outline_content": "林澈留在下层记录异常。",
            },
        },
    ).json()
    provider = client.post(
        "/api/model-providers",
        json={
            "name": "Stability Mock {}".format(suffix),
            "provider_type": "openai_compatible",
            "base_url": "http://127.0.0.1:{}/v1".format(server_port),
            "model": "stability-mock",
            "timeout_seconds": timeout_seconds,
        },
    ).json()
    return project, chapter, provider


def start_run(client, project, chapter, provider):
    response = client.post(
        "/api/projects/{}/chapters/{}/run".format(project["id"], chapter["id"]),
        json={"provider_id": provider["id"], "context_budget": 1200},
    )
    assert response.status_code == 202
    return response.json()["id"]


def wait_for_status(client, project_id, run_id, statuses):
    deadline = time.time() + 10
    while time.time() < deadline:
        response = client.get("/api/projects/{}/runs/{}".format(project_id, run_id))
        assert response.status_code == 200
        run = response.json()
        if run["status"] in statuses:
            return run
        time.sleep(0.03)
    raise AssertionError("Loop run did not reach {}".format(statuses))


def test_approve_updates_chapter_only_after_human_decision():
    server = ThreadingHTTPServer(("127.0.0.1", 0), StabilityMockHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with TestClient(app) as client:
            project, chapter, provider = create_case(client, server.server_port, "approve")
            run = wait_for_status(
                client,
                project["id"],
                start_run(client, project, chapter, provider),
                {"waiting"},
            )
            draft = run["versions"][0]["content_markdown"]
            assert client.get("/api/chapters/{}".format(chapter["id"])).json()["content"] == ORIGINAL_CONTENT

            approved = client.post(
                "/api/projects/{}/runs/{}/approve".format(project["id"], run["id"]),
                json={"feedback": "人工确认通过"},
            )
            assert approved.status_code == 200
            body = approved.json()
            assert body["state"] == "APPROVED"
            assert body["status"] == "approved"
            assert body["approved_version_id"] == run["current_version_id"]
            assert body["active_slot"] is None
            assert body["steps"][-1]["state"] == "APPROVED"
            assert client.get("/api/chapters/{}".format(chapter["id"])).json()["content"] == draft
    finally:
        server.shutdown()
        server.server_close()


def test_loop_run_summary_lists_are_discoverable_without_detail_payloads():
    server = ThreadingHTTPServer(("127.0.0.1", 0), StabilityMockHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with TestClient(app) as client:
            project, chapter, provider = create_case(client, server.server_port, "summary-list")
            run = wait_for_status(
                client,
                project["id"],
                start_run(client, project, chapter, provider),
                {"waiting"},
            )

            responses = [
                client.get("/api/loop-runs", params={"project_id": project["id"]}),
                client.get("/api/projects/{}/runs".format(project["id"])),
                client.get("/api/chapters/{}/loop-runs".format(chapter["id"])),
            ]
            for response in responses:
                assert response.status_code == 200
                summary = response.json()[0]
                assert summary["id"] == run["id"]
                assert summary["project_name"] == project["name"]
                assert summary["chapter_title"] == chapter["title"]
                assert summary["provider_name"] == provider["name"]
                assert summary["status"] == "waiting"
                assert "steps" not in summary
                assert "versions" not in summary
                assert "model_calls" not in summary
    finally:
        server.shutdown()
        server.server_close()


def test_reject_preserves_chapter_content():
    server = ThreadingHTTPServer(("127.0.0.1", 0), StabilityMockHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with TestClient(app) as client:
            project, chapter, provider = create_case(client, server.server_port, "reject")
            run = wait_for_status(
                client,
                project["id"],
                start_run(client, project, chapter, provider),
                {"waiting"},
            )
            rejected = client.post(
                "/api/projects/{}/runs/{}/reject".format(project["id"], run["id"]),
                json={"feedback": "剧情节奏不符合要求"},
            )
            assert rejected.status_code == 200
            assert rejected.json()["state"] == "REJECTED"
            assert rejected.json()["active_slot"] is None
            assert client.get("/api/chapters/{}".format(chapter["id"])).json()["content"] == ORIGINAL_CONTENT
    finally:
        server.shutdown()
        server.server_close()


def test_revise_appends_immutable_revision_and_preserves_old_version():
    server = ThreadingHTTPServer(("127.0.0.1", 0), StabilityMockHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with TestClient(app) as client:
            project, chapter, provider = create_case(client, server.server_port, "revise")
            initial = wait_for_status(
                client,
                project["id"],
                start_run(client, project, chapter, provider),
                {"waiting"},
            )
            first = initial["versions"][0]
            response = client.post(
                "/api/projects/{}/runs/{}/revise".format(project["id"], initial["id"]),
                json={"feedback": "补充纸质记录细节"},
            )
            assert response.status_code == 202
            revised = wait_for_status(client, project["id"], initial["id"], {"waiting", "failed"})
            assert revised["status"] == "waiting"
            assert len(revised["versions"]) == 2
            assert revised["versions"][0]["id"] == first["id"]
            assert revised["versions"][0]["content_markdown"] == first["content_markdown"]
            assert revised["versions"][1]["kind"] == "revision"
            assert revised["versions"][1]["parent_version_id"] == first["id"]
            assert "补充了锁死期间的纸质记录" in revised["versions"][1]["content_markdown"]
            assert client.get("/api/chapters/{}".format(chapter["id"])).json()["content"] == ORIGINAL_CONTENT
    finally:
        server.shutdown()
        server.server_close()


def test_empty_draft_fails_without_chapter_version():
    server = ThreadingHTTPServer(("127.0.0.1", 0), StabilityMockHandler)
    server.mode = "empty"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with TestClient(app) as client:
            project, chapter, provider = create_case(client, server.server_port, "empty")
            run = wait_for_status(
                client,
                project["id"],
                start_run(client, project, chapter, provider),
                {"failed"},
            )
            assert run["error_code"] == "EMPTY_CONTENT"
            assert run["steps"][-1]["state"] == "WRITE_DRAFT"
            assert run["steps"][-1]["status"] == "failed"
            assert run["versions"] == []
            assert run["active_slot"] is None
            assert run["raw_output_available"] is True
            assert run["recoverable_raw_output"] is False
            assert "recover_draft" not in run["recovery_actions"]
    finally:
        server.shutdown()
        server.server_close()


def test_markdown_draft_succeeds_without_json_guard():
    server = ThreadingHTTPServer(("127.0.0.1", 0), StabilityMockHandler)
    server.mode = "markdown"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with TestClient(app) as client:
            project, chapter, provider = create_case(client, server.server_port, "markdown")
            run = wait_for_status(
                client,
                project["id"],
                start_run(client, project, chapter, provider),
                {"waiting"},
            )
            assert run["state"] == "WAIT_HUMAN_APPROVAL"
            assert len(run["versions"]) == 1
            assert run["versions"][0]["content_markdown"].startswith("林澈推开下层档案室")
            assert run["error_code"] == ""
            assert run["draft_warning"] == ""
            assert run["stream_supported"] is True
            writer_calls = [call for call in run["model_calls"] if call["agent_name"] == "draft_writer"]
            assert len(writer_calls) == 1
            assert writer_calls[0]["error_code"] != "JSON_PARSE_ERROR"
    finally:
        server.shutdown()
        server.server_close()


def test_invalid_legacy_draft_json_falls_back_to_readable_text():
    server = ThreadingHTTPServer(("127.0.0.1", 0), StabilityMockHandler)
    server.mode = "invalid-draft-json"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with TestClient(app) as client:
            project, chapter, provider = create_case(client, server.server_port, "draft-fallback")
            run = wait_for_status(
                client,
                project["id"],
                start_run(client, project, chapter, provider),
                {"waiting"},
            )
            assert run["status"] == "waiting"
            assert run["draft_warning"] == "DRAFT_JSON_FALLBACK_USED"
            assert "纸质记录" in run["versions"][0]["content_markdown"]
            assert all(call["error_code"] != "JSON_PARSE_ERROR" for call in run["model_calls"])
    finally:
        server.shutdown()
        server.server_close()


def test_writer_error_text_retries_once_and_fails_as_invalid_draft_text():
    server = ThreadingHTTPServer(("127.0.0.1", 0), StabilityMockHandler)
    server.mode = "error-text"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with TestClient(app) as client:
            project, chapter, provider = create_case(client, server.server_port, "invalid-text")
            run = wait_for_status(
                client,
                project["id"],
                start_run(client, project, chapter, provider),
                {"failed"},
            )
            assert run["error_code"] == "INVALID_DRAFT_TEXT"
            assert run["failed_step"] == "WRITE_DRAFT"
            assert run["raw_output_available"] is True
            assert run["recoverable_raw_output"] is False
            assert "recover_draft" not in run["recovery_actions"]
            assert len([call for call in run["model_calls"] if call["agent_name"] == "draft_writer"]) == 2
            assert "JSON_PARSE_ERROR" not in {call["error_code"] for call in run["model_calls"]}
    finally:
        server.shutdown()
        server.server_close()


def test_recover_draft_from_old_raw_output_creates_version_without_overwriting_chapter():
    server = ThreadingHTTPServer(("127.0.0.1", 0), StabilityMockHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with TestClient(app) as client:
            project, chapter, provider = create_case(client, server.server_port, "recover")
            with SessionLocal() as db:
                run = ChapterLoopRun(
                    project_id=project["id"],
                    novel_id=chapter["novel_id"],
                    chapter_id=chapter["id"],
                    provider_id=provider["id"],
                    state="FAILED",
                    status="failed",
                    active_slot=None,
                    error_code="JSON_PARSE_ERROR",
                    error="Legacy writer expected JSON",
                )
                db.add(run)
                db.commit()
                db.refresh(run)
                step = RunStep(
                    run_id=run.id,
                    sequence=1,
                    state="WRITE_DRAFT",
                    status="failed",
                    error_code="JSON_PARSE_ERROR",
                    error="Legacy writer expected JSON",
                )
                db.add(step)
                db.commit()
                db.refresh(step)
                raw = "林澈在午夜进入下层档案室，逐页核对纸质记录，并确认锁死期间有七分钟从电子系统中消失。"
                db.add(
                    ModelCall(
                        run_id=run.id,
                        step_id=step.id,
                        provider_id=provider["id"],
                        agent_name="draft_writer",
                        prompt="legacy prompt",
                        response=raw,
                        status="failed",
                        error_code="JSON_PARSE_ERROR",
                        error="Legacy writer expected JSON",
                    )
                )
                db.commit()
                run_id = run.id

            detail = client.get("/api/projects/{}/runs/{}".format(project["id"], run_id)).json()
            assert detail["raw_output_available"] is True
            assert detail["failed_step"] == "WRITE_DRAFT"
            assert "recover_draft" in detail["recovery_actions"]
            raw_response = client.get(
                "/api/projects/{}/runs/{}/artifacts/raw-output".format(project["id"], run_id)
            )
            assert raw_response.status_code == 200
            assert "纸质记录" in raw_response.json()["content"]

            recovered_response = client.post(
                "/api/projects/{}/runs/{}/recover-draft".format(project["id"], run_id),
                json={"source": "raw_output", "note": "人工确认原始正文可用"},
            )
            assert recovered_response.status_code == 202
            recovered = wait_for_status(client, project["id"], run_id, {"waiting", "failed"})
            assert recovered["status"] == "waiting"
            assert len(recovered["versions"]) == 1
            assert "纸质记录" in recovered["versions"][0]["content_markdown"]
            assert any(step["state"] == "RECOVER_DRAFT" for step in recovered["steps"])
            assert client.get("/api/chapters/{}".format(chapter["id"])).json()["content"] == ORIGINAL_CONTENT
    finally:
        server.shutdown()
        server.server_close()


def test_schema_validation_error_fails_run_and_model_call():
    server = ThreadingHTTPServer(("127.0.0.1", 0), StabilityMockHandler)
    server.mode = "schema"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with TestClient(app) as client:
            project, chapter, provider = create_case(client, server.server_port, "schema")
            run = wait_for_status(
                client,
                project["id"],
                start_run(client, project, chapter, provider),
                {"failed"},
            )
            assert run["error_code"] == "SCHEMA_VALIDATION_ERROR"
            assert run["steps"][-1]["error_code"] == "SCHEMA_VALIDATION_ERROR"
            assert run["model_calls"][-1]["error_code"] == "SCHEMA_VALIDATION_ERROR"
            assert run["model_calls"][-1]["response"]
    finally:
        server.shutdown()
        server.server_close()


def test_model_timeout_is_logged_and_fails_run():
    server = ThreadingHTTPServer(("127.0.0.1", 0), StabilityMockHandler)
    server.mode = "timeout"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with TestClient(app) as client:
            project, chapter, provider = create_case(
                client,
                server.server_port,
                "timeout",
                timeout_seconds=5,
            )
            run = wait_for_status(
                client,
                project["id"],
                start_run(client, project, chapter, provider),
                {"failed"},
            )
            assert run["error_code"] == "MODEL_TIMEOUT"
            assert run["steps"][-1]["error_code"] == "MODEL_TIMEOUT"
            assert run["model_calls"][-1]["error_code"] == "MODEL_TIMEOUT"
            assert run["model_calls"][-1]["status"] == "failed"
    finally:
        server.shutdown()
        server.server_close()


def test_database_unique_active_slot_blocks_concurrent_runs():
    server = ThreadingHTTPServer(("127.0.0.1", 0), StabilityMockHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with TestClient(app) as client:
            project, chapter, provider = create_case(client, server.server_port, "concurrent")

            barrier = threading.Barrier(2)

            def insert_run():
                with SessionLocal() as db:
                    run = ChapterLoopRun(
                        project_id=project["id"],
                        novel_id=chapter["novel_id"],
                        chapter_id=chapter["id"],
                        provider_id=provider["id"],
                        state="LOAD_PROJECT",
                        status="pending",
                        active_slot=1,
                    )
                    db.add(run)
                    barrier.wait()
                    try:
                        db.commit()
                        return "created"
                    except IntegrityError:
                        db.rollback()
                        return "conflict"

            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(lambda _index: insert_run(), range(2)))
            assert sorted(results) == ["conflict", "created"]
    finally:
        server.shutdown()
        server.server_close()


def test_alembic_baseline_and_stability_upgrade(tmp_path, monkeypatch):
    database_path = tmp_path / "migration.db"
    monkeypatch.setenv("NOVEL_AI_DB_URL", "sqlite:///{}".format(database_path))
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "migrations"))
    config.set_main_option("sqlalchemy.url", "sqlite:///{}".format(database_path))
    command.upgrade(config, "head")

    from sqlalchemy import create_engine

    migration_engine = create_engine("sqlite:///{}".format(database_path))
    inspector = inspect(migration_engine)
    columns = {column["name"] for column in inspector.get_columns("chapter_loop_runs")}
    indexes = {index["name"] for index in inspector.get_indexes("chapter_loop_runs")}
    assert {
        "active_slot",
        "revision_feedback",
        "approved_version_id",
        "decision_feedback",
        "decided_at",
    }.issubset(columns)
    assert "uq_chapter_loop_active_slot" in indexes
