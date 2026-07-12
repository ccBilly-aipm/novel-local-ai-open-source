import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from fastapi.testclient import TestClient

from app.main import app
from app.agents.base import output_was_truncated
from app.routers import model_providers as model_provider_router
from app.models.entities import ModelProvider
from app.pipelines.chapter_pipeline import extract_partial_string_field
from app.services.local_model_inventory import apply_configured_provider_status, make_model


class MockModelHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        prompt = payload.get("messages", [{}])[0].get("content", "")
        if "请总结下面章节" in prompt:
            content = json.dumps(
                {
                    "summary": "主角完成了第一次本地生成。",
                    "key_events": ["完成生成"],
                    "unresolved_conflicts": ["下一章如何继续"],
                    "foreshadowing": ["桌上的旧钥匙"],
                },
                ensure_ascii=False,
            )
        elif "谨慎的小说审稿人" in prompt:
            content = json.dumps(
                {
                    "score": 82,
                    "goal_alignment": "符合目标",
                    "character_consistency": "无冲突",
                    "timeline_consistency": "无冲突",
                    "repetition": "无明显重复",
                    "missing_plot_points": "",
                    "style_issues": "",
                    "suggestions": ["补充一个感官细节"],
                },
                ensure_ascii=False,
            )
        else:
            content = "门在雨夜里打开，主角把那把旧钥匙握进掌心。"
        body = json.dumps(
            {
                "choices": [{"message": {"role": "assistant", "content": content}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20},
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *_args):
        return


def wait_for_idle(client, chapter_id):
    deadline = time.time() + 10
    while time.time() < deadline:
        tasks = client.get("/api/writing-tasks", params={"chapter_id": chapter_id}).json()
        if tasks and all(item["status"] in {"completed", "failed", "paused"} for item in tasks):
            return tasks
        time.sleep(0.05)
    raise AssertionError("writing tasks did not finish")


def test_extract_summary_from_truncated_json():
    partial = '{"summary":"可保留的摘要","key_events":["事件一"'
    assert extract_partial_string_field(partial, "summary") == "可保留的摘要"


def test_local_model_inventory():
    with TestClient(app) as client:
        response = client.get("/api/model-providers/local-inventory")
        assert response.status_code == 200
        inventory = response.json()
        assert "hardware" in inventory
        assert "models" in inventory
        assert "usage_profiles" in inventory


def test_local_model_provider_sync_is_explicit_and_safe(monkeypatch):
    monkeypatch.setattr(model_provider_router, "sync_local_model_providers", lambda _db: [])
    with TestClient(app) as client:
        response = client.post("/api/model-providers/sync-local")
        assert response.status_code == 200
        assert isinstance(response.json(), list)


def test_output_limit_finish_reason_triggers_draft_fallback():
    assert output_was_truncated({"finish_reason": "length"}) is True
    assert output_was_truncated({"choices": [{"finish_reason": "max_tokens"}]}) is True
    assert output_was_truncated({"done_reason": "stop"}) is False


def test_configured_provider_does_not_match_incomplete_cache():
    provider = ModelProvider(
        name="本机 llama.cpp",
        provider_type="llama_cpp",
        base_url="http://127.0.0.1:18081/v1",
        model="qwen2.5-coder-0.5b-q4km",
        enabled=True,
        last_test_status="ok",
    )
    incomplete_cache = make_model(
        model_id="hf:incomplete",
        name="unsloth/Qwen2.5-Coder-0.5B-Instruct-GGUF",
        source="Hugging Face",
        model_format="cache",
        size_bytes=0,
        path="/tmp/incomplete",
        state="incomplete",
    )

    additions = apply_configured_provider_status([provider], [incomplete_cache])

    assert incomplete_cache["current"] is False
    assert len(additions) == 1
    assert additions[0]["source"] == "llama.cpp"
    assert additions[0]["current"] is True
    assert additions[0]["usable"] is True


def test_model_provider_can_be_deleted():
    with TestClient(app) as client:
        provider = client.post(
            "/api/model-providers",
            json={
                "name": "Disposable provider",
                "provider_type": "openai_compatible",
                "base_url": "http://127.0.0.1:9999/v1",
                "model": "test-model",
            },
        ).json()

        response = client.delete("/api/model-providers/{}".format(provider["id"]))

        assert response.status_code == 204
        providers = client.get("/api/model-providers").json()
        assert all(item["id"] != provider["id"] for item in providers)


def test_crud_context_generation_review_and_export():
    server = ThreadingHTTPServer(("127.0.0.1", 0), MockModelHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        with TestClient(app) as client:
            project = client.post("/api/projects", json={"name": "测试项目"}).json()
            novel = client.post(
                "/api/novels",
                json={
                    "project_id": project["id"],
                    "title": "雨夜钥匙",
                    "story_outline": "主角寻找一扇被遗忘的门。",
                    "style_guide": "克制，具体。",
                },
            ).json()
            character = client.post(
                "/api/characters",
                json={
                    "novel_id": novel["id"],
                    "name": "林舟",
                    "role": "主角",
                    "description": "谨慎的档案员",
                    "current_state": {"位置": "旧宅"},
                },
            ).json()
            client.post(
                "/api/world-rules",
                json={
                    "novel_id": novel["id"],
                    "name": "钥匙规则",
                    "description": "旧钥匙只能开一次门。",
                    "priority": 90,
                },
            )
            chapter = client.post(
                "/api/chapters",
                json={
                    "novel_id": novel["id"],
                    "title": "第一章 门",
                    "outline": {
                        "goal": "主角取得旧钥匙",
                        "outline_content": "在雨夜进入旧宅。",
                        "character_ids": [character["id"]],
                    },
                },
            ).json()
            preview = client.get(
                "/api/chapters/{}/context-preview".format(chapter["id"]),
                params={"budget": 1200},
            ).json()
            assert "主角取得旧钥匙" in preview["rendered_context"]
            assert preview["estimated_tokens"] <= 1300

            provider = client.post(
                "/api/model-providers",
                json={
                    "name": "Mock OpenAI",
                    "provider_type": "openai_compatible",
                    "base_url": "http://127.0.0.1:{}/v1".format(server.server_port),
                    "model": "mock",
                },
            ).json()
            test_result = client.post(
                "/api/model-providers/{}/test".format(provider["id"])
            ).json()
            assert test_result["ok"] is True

            creative = client.post(
                "/api/creative-runs",
                json={
                    "novel_id": novel["id"],
                    "provider_id": provider["id"],
                    "operation": "story_outline",
                    "idea": "一个档案员发现自己的记忆被修改。",
                    "reference_text": "结局必须回到那把旧钥匙。",
                    "options": {"max_tokens": 200},
                },
            ).json()
            assert creative["status"] == "completed"
            assert creative["response"]
            history = client.get(
                "/api/creative-runs",
                params={"novel_id": novel["id"]},
            ).json()
            assert history[0]["id"] == creative["id"]

            response = client.post(
                "/api/chapters/{}/generate".format(chapter["id"]),
                json={"provider_id": provider["id"], "context_budget": 1200},
            )
            assert response.status_code == 202
            tasks = wait_for_idle(client, chapter["id"])
            assert len(tasks) == 2
            refreshed = client.get("/api/chapters/{}".format(chapter["id"])).json()
            assert "旧钥匙" in refreshed["content"]
            assert refreshed["summary"] == "主角完成了第一次本地生成。"

            review_task = client.post(
                "/api/chapters/{}/review".format(chapter["id"]),
                json={"provider_id": provider["id"], "context_budget": 1200},
            )
            assert review_task.status_code == 202
            wait_for_idle(client, chapter["id"])
            reviews = client.get("/api/chapters/{}/reviews".format(chapter["id"])).json()
            assert reviews[0]["score"] == 82

            runs = client.get(
                "/api/chapters/{}/generation-runs".format(chapter["id"])
            ).json()
            assert len(runs) >= 3
            assert all(run["prompt"] for run in runs)

            exported = client.get("/api/novels/{}/export/markdown".format(novel["id"]))
            assert exported.status_code == 200
            assert "# 雨夜钥匙" in exported.text
            assert "## 第一章 门" in exported.text
    finally:
        server.shutdown()
        server.server_close()
