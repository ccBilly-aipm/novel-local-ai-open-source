import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models.entities import CanonState
from app.services.context_builder import build_context


NEW_STATE = "位于灯塔地下室，握有缓存指令"


class StateMemoryMockHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        prompt = payload.get("messages", [{}])[0].get("content", "")

        if "AGENT: draft_writer" in prompt:
            content = (
                "章节初稿正文。林澈在午夜进入灯塔地下室，记录电子门锁死的七分钟，"
                "并在维护区找到来自上层的缓存指令，把时间写入纸质日志。"
            )
        elif "AGENT: continuity_checker" in prompt:
            content = json.dumps({"passed": True, "severity": "none", "issues": []})
        elif "AGENT: state_extractor" in prompt:
            content = json.dumps(
                {
                    "character_states": [
                        {
                            "character_name": "林澈",
                            "new_state": NEW_STATE,
                            "confidence": 0.85,
                            "evidence": "正文结尾林澈仍在灯塔地下室",
                        }
                    ]
                },
                ensure_ascii=False,
            )
        else:
            content = json.dumps({"unexpected": True})

        body = json.dumps(
            {
                "choices": [{"message": {"role": "assistant", "content": content}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 60},
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *_args):
        return


def _run_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), StateMemoryMockHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _create_case(client, port):
    project = client.post("/api/projects", json={"name": "状态推进测试"}).json()
    novel = client.post(
        "/api/novels",
        json={
            "project_id": project["id"],
            "title": "未来退信",
            "story_outline": "林澈调查潮汐城午夜锁死。",
        },
    ).json()
    character = client.post(
        "/api/characters",
        json={
            "novel_id": novel["id"],
            "name": "林澈",
            "role": "主角",
            "description": "退信调查员",
        },
    ).json()
    chapter = client.post(
        "/api/chapters",
        json={
            "novel_id": novel["id"],
            "title": "灯塔的地下室",
            "content": "",
            "outline": {"goal": "确认午夜锁死规律", "outline_content": "进入灯塔地下室。"},
        },
    ).json()
    provider = client.post(
        "/api/model-providers",
        json={
            "name": "State Mock",
            "provider_type": "openai_compatible",
            "base_url": "http://127.0.0.1:{}/v1".format(port),
            "model": "state-mock",
            "timeout_seconds": 5,
        },
    ).json()
    return project, novel, character, chapter, provider


def _wait_committed(client, project_id, run_id):
    deadline = time.time() + 15
    while time.time() < deadline:
        run = client.get("/api/projects/{}/runs/{}".format(project_id, run_id)).json()
        if run["status"] in {"committed", "paused", "failed"}:
            return run
        time.sleep(0.03)
    raise AssertionError("auto run 未在期限内提交")


def test_state_change_staged_then_advances_canon_on_accept():
    server = _run_server()
    try:
        with TestClient(app) as client:
            project, novel, character, chapter, provider = _create_case(client, server.server_port)
            novel_id = novel["id"]

            start = client.post(
                "/api/projects/{}/chapters/{}/auto-run".format(project["id"], chapter["id"]),
                json={"provider_id": provider["id"], "context_budget": 1600},
            )
            assert start.status_code == 202, start.text
            run = _wait_committed(client, project["id"], start.json()["id"])
            assert run["status"] == "committed"

            # 提交后应产生 staged 的状态变更候选
            candidates = client.get(
                "/api/novels/{}/story-engineering/candidates".format(novel_id),
                params={"record_type": "staged_state_change"},
            ).json()
            assert len(candidates) >= 1
            candidate = candidates[0]
            assert candidate["status"] == "staged"

            # 接受前：Canon 未被写入（staging 不自动落 Canon）
            with SessionLocal() as db:
                canon = db.query(CanonState).filter(CanonState.novel_id == novel_id).first()
                assert canon.character_states_json == "{}"
                ctx_before = build_context(db, chapter["id"], 6000)
            assert NEW_STATE not in ctx_before["rendered_context"]

            # 接受候选 → 推进 CanonState
            accept = client.post(
                "/api/story-engineering/candidates/{}/accept".format(candidate["id"])
            )
            assert accept.status_code == 200, accept.text
            assert accept.json()["applied"] is True

            with SessionLocal() as db:
                canon = db.query(CanonState).filter(CanonState.novel_id == novel_id).first()
                states = json.loads(canon.character_states_json)
                assert states.get(character["id"]) == NEW_STATE
                # 读端 context_builder 反映最新状态
                ctx_after = build_context(db, chapter["id"], 6000)
            assert NEW_STATE in ctx_after["rendered_context"]
    finally:
        server.shutdown()
        server.server_close()


def test_state_change_reject_does_not_touch_canon():
    server = _run_server()
    try:
        with TestClient(app) as client:
            project, novel, _character, chapter, provider = _create_case(client, server.server_port)
            novel_id = novel["id"]
            start = client.post(
                "/api/projects/{}/chapters/{}/auto-run".format(project["id"], chapter["id"]),
                json={"provider_id": provider["id"], "context_budget": 1600},
            )
            assert start.status_code == 202, start.text
            _wait_committed(client, project["id"], start.json()["id"])

            candidates = client.get(
                "/api/novels/{}/story-engineering/candidates".format(novel_id),
                params={"record_type": "staged_state_change"},
            ).json()
            assert len(candidates) >= 1

            reject = client.post(
                "/api/story-engineering/candidates/{}/reject".format(candidates[0]["id"])
            )
            assert reject.status_code == 200, reject.text
            assert reject.json()["status"] == "rejected"

            with SessionLocal() as db:
                canon = db.query(CanonState).filter(CanonState.novel_id == novel_id).first()
                assert canon.character_states_json == "{}"
    finally:
        server.shutdown()
        server.server_close()
