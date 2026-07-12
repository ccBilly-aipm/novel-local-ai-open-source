import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models.loop_entities import ChapterVersion
from app.schemas.loop import ContinuityCheckerOutput
from app.services.json_guard import JsonGuard, JsonGuardError


class LoopMockModelHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        prompt = payload.get("messages", [{}])[0].get("content", "")
        chapter_match = re.search(r"章节 ID：([^\n]+)", prompt)
        chapter_id = chapter_match.group(1).strip() if chapter_match else ""

        if "AGENT: draft_writer" in prompt:
            content = json.dumps(
                {
                    "chapter_id": chapter_id,
                    "draft_markdown": "雨夜里，林舟推开旧宅的门，把那把只能使用一次的钥匙握进掌心。",
                    "scene_breakdown": [{"scene": "旧宅门厅", "result": "取得钥匙"}],
                    "self_notes": [],
                },
                ensure_ascii=False,
            )
        elif "AGENT: continuity_checker" in prompt:
            if getattr(self.server, "invalid_continuity", False):
                content = "这不是合法 JSON"
            else:
                content = json.dumps(
                    {
                        "passed": False,
                        "severity": "major",
                        "issues": [
                            {
                                "type": "item",
                                "severity": "major",
                                "evidence": "规则说钥匙只能使用一次，初稿尚未说明本次是否已经使用。",
                                "problem": "钥匙的使用状态不明确。",
                                "suggested_fix": "明确本章只取得钥匙，尚未开门。",
                            }
                        ],
                    },
                    ensure_ascii=False,
                )
        else:
            content = json.dumps({"unexpected": True})

        body = json.dumps(
            {
                "choices": [{"message": {"role": "assistant", "content": content}}],
                "usage": {"prompt_tokens": 120, "completion_tokens": 80},
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *_args):
        return


def wait_for_loop(client, project_id, run_id):
    deadline = time.time() + 10
    while time.time() < deadline:
        response = client.get("/api/projects/{}/runs/{}".format(project_id, run_id))
        assert response.status_code == 200
        run = response.json()
        if run["status"] in {"waiting", "failed"}:
            return run
        time.sleep(0.05)
    raise AssertionError("Loop run did not reach a waiting or failed state")


def create_loop_case(client, server_port, suffix):
    project = client.post("/api/projects", json={"name": "Loop {}".format(suffix)}).json()
    novel = client.post(
        "/api/novels",
        json={
            "project_id": project["id"],
            "title": "不可变草稿 {}".format(suffix),
            "story_outline": "林舟寻找一把只能使用一次的钥匙。",
            "style_guide": "克制、具体。",
        },
    ).json()
    chapter = client.post(
        "/api/chapters",
        json={
            "novel_id": novel["id"],
            "title": "第一章 旧宅",
            "content": "这是用户原有正文，不允许 Loop 自动覆盖。",
            "outline": {
                "goal": "林舟取得旧钥匙",
                "outline_content": "林舟在雨夜进入旧宅，但本章不使用钥匙开门。",
            },
        },
    ).json()
    client.post(
        "/api/world-rules",
        json={
            "novel_id": novel["id"],
            "name": "一次性钥匙",
            "description": "旧钥匙只能使用一次。",
            "priority": 100,
        },
    )
    provider = client.post(
        "/api/model-providers",
        json={
            "name": "Loop Mock {}".format(suffix),
            "provider_type": "openai_compatible",
            "base_url": "http://127.0.0.1:{}/v1".format(server_port),
            "model": "loop-mock",
        },
    ).json()
    return project, novel, chapter, provider


def test_json_guard_rejects_schema_invalid_json():
    with pytest.raises(JsonGuardError) as error:
        JsonGuard().parse_and_validate(
            '{"passed": true, "severity": "none", "unexpected": true}',
            ContinuityCheckerOutput,
        )
    assert error.value.code == "SCHEMA_VALIDATION_ERROR"


def test_single_chapter_loop_stops_at_human_gate_and_preserves_content():
    server = ThreadingHTTPServer(("127.0.0.1", 0), LoopMockModelHandler)
    server.invalid_continuity = False
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        with TestClient(app) as client:
            project, _novel, chapter, provider = create_loop_case(
                client,
                server.server_port,
                "success",
            )
            created = client.post(
                "/api/projects/{}/chapters/{}/run".format(project["id"], chapter["id"]),
                json={
                    "provider_id": provider["id"],
                    "context_budget": 1400,
                    "options": {"max_tokens": 600},
                },
            )
            assert created.status_code == 202
            run = wait_for_loop(client, project["id"], created.json()["id"])

            assert run["state"] == "WAIT_HUMAN_APPROVAL"
            assert run["status"] == "waiting"
            assert [step["state"] for step in run["steps"]] == [
                "LOAD_PROJECT",
                "ASSEMBLE_CONTEXT",
                "WRITE_DRAFT",
                "CHECK_CONTINUITY",
                "WAIT_HUMAN_APPROVAL",
            ]
            assert all(step["status"] == "completed" for step in run["steps"])
            assert [call["agent_name"] for call in run["model_calls"]] == [
                "draft_writer",
                "continuity_checker",
            ]
            assert all(call["status"] == "completed" for call in run["model_calls"])
            assert len(run["versions"]) == 1
            assert run["versions"][0]["kind"] == "draft"
            assert run["current_version_id"] == run["versions"][0]["id"]
            assert json.loads(run["continuity_report_json"])["passed"] is False

            refreshed = client.get("/api/chapters/{}".format(chapter["id"])).json()
            assert refreshed["content"] == "这是用户原有正文，不允许 Loop 自动覆盖。"

            with SessionLocal() as db:
                version = db.get(ChapterVersion, run["versions"][0]["id"])
                version.content_markdown = "试图覆盖不可变版本"
                with pytest.raises(ValueError, match="immutable"):
                    db.commit()
                db.rollback()
    finally:
        server.shutdown()
        server.server_close()


def test_invalid_continuity_json_fails_run_and_keeps_model_log():
    server = ThreadingHTTPServer(("127.0.0.1", 0), LoopMockModelHandler)
    server.invalid_continuity = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        with TestClient(app) as client:
            project, _novel, chapter, provider = create_loop_case(
                client,
                server.server_port,
                "invalid-json",
            )
            created = client.post(
                "/api/projects/{}/chapters/{}/run".format(project["id"], chapter["id"]),
                json={"provider_id": provider["id"], "context_budget": 1400},
            )
            assert created.status_code == 202
            run = wait_for_loop(client, project["id"], created.json()["id"])

            assert run["state"] == "FAILED"
            assert run["status"] == "failed"
            assert run["error_code"] == "JSON_PARSE_ERROR"
            assert [step["state"] for step in run["steps"]] == [
                "LOAD_PROJECT",
                "ASSEMBLE_CONTEXT",
                "WRITE_DRAFT",
                "CHECK_CONTINUITY",
            ]
            assert run["steps"][-1]["status"] == "failed"
            assert run["steps"][-1]["error_code"] == "JSON_PARSE_ERROR"
            assert len(run["versions"]) == 1
            assert len(run["model_calls"]) == 3
            assert run["model_calls"][-1]["agent_name"] == "continuity_checker_json_repair"
            assert run["model_calls"][-1]["status"] == "failed"
            assert run["model_calls"][-1]["error_code"] == "JSON_PARSE_ERROR"
            assert run["model_calls"][1]["response"] == "这不是合法 JSON"

            refreshed = client.get("/api/chapters/{}".format(chapter["id"])).json()
            assert refreshed["content"] == "这是用户原有正文，不允许 Loop 自动覆盖。"
    finally:
        server.shutdown()
        server.server_close()
