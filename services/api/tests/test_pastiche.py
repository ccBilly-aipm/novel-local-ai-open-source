import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models.entities import Novel


class PasticheMockHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        prompt = payload.get("messages", [{}])[0].get("content", "")

        if "AGENT: story_pastiche" in prompt:
            content = json.dumps(
                {
                    "framework": {
                        "synopsis": "一名调音师在声音里发现被抹去的城市。",
                        "story_outline": "三幕：发现异响—追查源头—揭示真相。",
                        "style_guide": "冷峻短句，克制叙述",
                        "forbidden_content": "无超自然解释",
                        "confidence": 0.8,
                        "evidence": "保留了参考的冷峻文风与三幕结构，人物与情节全新原创",
                    }
                },
                ensure_ascii=False,
            )
        else:
            content = json.dumps({"unexpected": True})

        body = json.dumps(
            {
                "choices": [{"message": {"role": "assistant", "content": content}}],
                "usage": {"prompt_tokens": 40, "completion_tokens": 30},
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *_args):
        return


def test_pastiche_generates_new_framework_and_accepts():
    server = ThreadingHTTPServer(("127.0.0.1", 0), PasticheMockHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with TestClient(app) as client:
            project = client.post("/api/projects", json={"name": "仿写测试"}).json()
            novel = client.post(
                "/api/novels",
                json={
                    "project_id": project["id"],
                    "title": "仿写新作",
                    "style_guide": "冷峻短句，克制叙述",  # 模拟已采纳的拆解文风
                },
            ).json()
            provider = client.post(
                "/api/model-providers",
                json={
                    "name": "Pastiche Mock",
                    "provider_type": "openai_compatible",
                    "base_url": "http://127.0.0.1:{}/v1".format(server.server_address[1]),
                    "model": "pastiche-mock",
                    "timeout_seconds": 5,
                },
            ).json()

            created = client.post(
                "/api/novels/{}/story-engineering/generate".format(novel["id"]),
                json={
                    "provider_id": provider["id"],
                    "operation": "pastiche",
                    "idea": "一个关于声音的悬疑故事",
                },
            )
            assert created.status_code == 200, created.text
            candidates = created.json()
            assert len(candidates) == 1
            assert candidates[0]["record_type"] == "staged_framework"

            accept = client.post(
                "/api/story-engineering/candidates/{}/accept".format(candidates[0]["id"])
            )
            assert accept.status_code == 200, accept.text

            with SessionLocal() as db:
                fresh = db.get(Novel, novel["id"])
                assert "调音师" in fresh.synopsis  # 新作简介写入（原 synopsis 为空）
    finally:
        server.shutdown()
        server.server_close()
