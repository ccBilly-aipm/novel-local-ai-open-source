import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from fastapi.testclient import TestClient

from app.main import app


class ActivityMockHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(length)
        # 创作中心(自由文本)只需一段文本即可 completed；loop/decon 是异步，本测试不等它们
        body = json.dumps(
            {
                "choices": [{"message": {"role": "assistant", "content": "测试生成内容"}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 5},
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *_args):
        return


def test_activity_aggregates_loop_creative_deconstruction():
    server = ThreadingHTTPServer(("127.0.0.1", 0), ActivityMockHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    try:
        with TestClient(app) as client:
            project = client.post("/api/projects", json={"name": "活动记录"}).json()
            novel = client.post(
                "/api/novels", json={"project_id": project["id"], "title": "未来退信"}
            ).json()
            chapter = client.post(
                "/api/chapters",
                json={
                    "novel_id": novel["id"],
                    "title": "第 1 章",
                    "content": "x",
                    "outline": {"goal": "g", "outline_content": "o"},
                },
            ).json()
            provider = client.post(
                "/api/model-providers",
                json={
                    "name": "Activity Mock",
                    "provider_type": "openai_compatible",
                    "base_url": "http://127.0.0.1:{}/v1".format(port),
                    "model": "activity-mock",
                    "timeout_seconds": 5,
                },
            ).json()

            # 创作中心(同步，立即 completed)
            client.post(
                "/api/creative-runs",
                json={
                    "novel_id": novel["id"],
                    "provider_id": provider["id"],
                    "operation": "story_outline",
                    "idea": "海港邮差收到退信",
                },
            ).raise_for_status()
            # 拆解任务(异步，立即建 pending run)
            client.post(
                "/api/novels/{}/deconstruction-runs".format(novel["id"]),
                json={"provider_id": provider["id"], "source_text": "正文", "dimensions": ["characters"]},
            ).raise_for_status()
            # 章节 Loop run(异步，立即建 pending run)
            client.post(
                "/api/projects/{}/chapters/{}/run".format(project["id"], chapter["id"]),
                json={"provider_id": provider["id"], "context_budget": 1600},
            ).raise_for_status()

            activity = client.get("/api/activity").json()
            kinds = {item["kind"] for item in activity}
            assert "creative" in kinds
            assert "deconstruction" in kinds
            assert "loop" in kinds

            # 字段归一化：每条有标题、状态、时间
            for item in activity:
                assert item["title"]
                assert item["status"]
                assert item["created_at"] and item["updated_at"]

            # 按 updated_at 倒序
            times = [item["updated_at"] for item in activity]
            assert times == sorted(times, reverse=True)

            # loop 项带章节信息可用于归组
            loop_items = [i for i in activity if i["kind"] == "loop"]
            assert loop_items and loop_items[0]["chapter_id"] == chapter["id"]
            # creative 项带 project_id(从 novel 反查)用于跳转
            creative_items = [i for i in activity if i["kind"] == "creative"]
            assert creative_items and creative_items[0]["project_id"] == project["id"]
    finally:
        server.shutdown()
        server.server_close()
