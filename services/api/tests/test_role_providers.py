import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from fastapi.testclient import TestClient

from app.main import app


class RoleMockHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        prompt = payload.get("messages", [{}])[0].get("content", "")
        if "AGENT: draft_writer" in prompt:
            content = "章节初稿正文。主角在午夜走进灯塔地下室，记录下门锁死的七分钟。"
        elif "AGENT: continuity_checker" in prompt:
            content = json.dumps({"passed": True, "severity": "none", "issues": []})
        else:
            content = json.dumps({"unexpected": True})
        body = json.dumps(
            {
                "choices": [{"message": {"role": "assistant", "content": content}}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 20},
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *_args):
        return


def _provider(client, port, name):
    return client.post(
        "/api/model-providers",
        json={
            "name": name,
            "provider_type": "openai_compatible",
            "base_url": "http://127.0.0.1:{}/v1".format(port),
            "model": "role-mock",
            "timeout_seconds": 5,
        },
    ).json()


def test_writer_and_checker_use_distinct_providers():
    server = ThreadingHTTPServer(("127.0.0.1", 0), RoleMockHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    try:
        with TestClient(app) as client:
            project = client.post("/api/projects", json={"name": "角色分模型"}).json()
            novel = client.post(
                "/api/novels", json={"project_id": project["id"], "title": "未来退信", "story_outline": "测试"}
            ).json()
            chapter = client.post(
                "/api/chapters",
                json={
                    "novel_id": novel["id"],
                    "title": "目标章节",
                    "content": "占位",
                    "outline": {"goal": "确认锁死", "outline_content": "留在下层。"},
                },
            ).json()
            main_p = _provider(client, port, "主 provider")
            writer_p = _provider(client, port, "Writer provider")
            checker_p = _provider(client, port, "Checker provider")

            start = client.post(
                "/api/projects/{}/chapters/{}/auto-run".format(project["id"], chapter["id"]),
                json={
                    "provider_id": main_p["id"],
                    "writer_provider_id": writer_p["id"],
                    "checker_provider_id": checker_p["id"],
                    "context_budget": 1600,
                    "max_revision_rounds_per_chapter": 0,
                    "update_story_memory": False,
                },
            )
            assert start.status_code == 202, start.text
            run_id = start.json()["id"]

            deadline = time.time() + 15
            run = None
            while time.time() < deadline:
                run = client.get("/api/projects/{}/runs/{}".format(project["id"], run_id)).json()
                if run["status"] in {"committed", "paused", "failed"}:
                    break
                time.sleep(0.03)
            assert run is not None and run["status"] == "committed", run

            calls = run["model_calls"]
            draft_calls = [c for c in calls if c["agent_name"] == "draft_writer"]
            checker_calls = [c for c in calls if c["agent_name"] == "continuity_checker"]
            assert draft_calls and checker_calls
            # draft_writer 走 Writer provider；continuity_checker 走 Checker provider
            assert all(c["provider_id"] == writer_p["id"] for c in draft_calls)
            assert all(c["provider_id"] == checker_p["id"] for c in checker_calls)
            # 主 provider 不应被这两类 agent 直接使用
            assert all(c["provider_id"] != main_p["id"] for c in draft_calls + checker_calls)

            # auto_policy 应记录两个角色 provider
            assert run["auto_policy"]["writer_provider_id"] == writer_p["id"]
            assert run["auto_policy"]["checker_provider_id"] == checker_p["id"]
    finally:
        server.shutdown()
        server.server_close()


def test_role_providers_fallback_to_main_when_unset():
    server = ThreadingHTTPServer(("127.0.0.1", 0), RoleMockHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    try:
        with TestClient(app) as client:
            project = client.post("/api/projects", json={"name": "回退"}).json()
            novel = client.post(
                "/api/novels", json={"project_id": project["id"], "title": "回退小说"}
            ).json()
            chapter = client.post(
                "/api/chapters",
                json={"novel_id": novel["id"], "title": "章", "content": "x", "outline": {"goal": "g", "outline_content": "o"}},
            ).json()
            main_p = _provider(client, port, "唯一 provider")
            start = client.post(
                "/api/projects/{}/chapters/{}/auto-run".format(project["id"], chapter["id"]),
                json={"provider_id": main_p["id"], "context_budget": 1600, "max_revision_rounds_per_chapter": 0, "update_story_memory": False},
            )
            assert start.status_code == 202
            run_id = start.json()["id"]
            deadline = time.time() + 15
            run = None
            while time.time() < deadline:
                run = client.get("/api/projects/{}/runs/{}".format(project["id"], run_id)).json()
                if run["status"] in {"committed", "paused", "failed"}:
                    break
                time.sleep(0.03)
            assert run is not None and run["status"] == "committed", run
            # 未设角色 provider：所有 agent 回退到主 provider
            assert all(c["provider_id"] == main_p["id"] for c in run["model_calls"] if c["provider_id"])
    finally:
        server.shutdown()
        server.server_close()
