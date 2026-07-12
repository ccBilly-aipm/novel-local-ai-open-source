import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models.entities import CanonState, Chapter, ChapterOutline, Character, Novel, WorldRule


class StoryEngineeringMockHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        prompt = payload.get("messages", [{}])[0].get("content", "")

        if "FORCE_BAD_JSON" in prompt:
            content = "这不是 JSON{"
        elif "AGENT: story_framework" in prompt:
            content = json.dumps(
                {
                    "framework": {
                        "synopsis": "退信人在午夜城寻找失踪的姐姐。",
                        "story_outline": "新总纲：不应覆盖已有总纲。",
                        "style_guide": "冷峻克制",
                        "forbidden_content": "无超自然解释",
                        "confidence": 0.8,
                        "evidence": "用户想法提到午夜与失踪",
                    }
                },
                ensure_ascii=False,
            )
        elif "AGENT: story_characters" in prompt:
            content = json.dumps(
                {
                    "characters": [
                        {
                            "name": "林澈",
                            "role": "主角",
                            "description": "退信调查员",
                            "personality": "执拗",
                            "goals": "找到姐姐",
                            "arc": "从逃避到直面",
                            "confidence": 0.7,
                            "evidence": "想法核心人物",
                        },
                        {"name": "陆衡", "role": "对手"},
                    ]
                },
                ensure_ascii=False,
            )
        elif "AGENT: story_world_rules" in prompt:
            content = json.dumps(
                {
                    "world_rules": [
                        {
                            "name": "午夜锁死",
                            "category": "technology",
                            "description": "全城门禁每天午夜锁死七分钟。",
                            "priority": 80,
                            "confidence": 0.9,
                            "evidence": "想法设定",
                        }
                    ]
                },
                ensure_ascii=False,
            )
        elif "AGENT: story_chapter_plan" in prompt:
            content = json.dumps(
                {
                    "chapters": [
                        {
                            "title": "灯塔的地下室",
                            "goal": "建立悬念",
                            "outline_content": "林澈进入灯塔地下室。",
                            "required_plot_points": ["发现线索", "遭遇危险"],
                            "confidence": 0.7,
                            "evidence": "想法开端",
                        },
                        {"title": "第二章占位"},
                    ]
                },
                ensure_ascii=False,
            )
        else:
            content = json.dumps({"unexpected": True})

        body = json.dumps(
            {
                "choices": [{"message": {"role": "assistant", "content": content}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 30},
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *_args):
        return


def _start_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), StoryEngineeringMockHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, server.server_address[1]


def _bootstrap(client, port):
    project = client.post("/api/projects", json={"name": "SE 测试"}).json()
    novel = client.post(
        "/api/novels",
        json={
            "project_id": project["id"],
            "title": "未来退信",
            "story_outline": "原总纲不可被覆盖。",
        },
    ).json()
    provider = client.post(
        "/api/model-providers",
        json={
            "name": "SE Mock",
            "provider_type": "openai_compatible",
            "base_url": "http://127.0.0.1:{}/v1".format(port),
            "model": "se-mock",
            "timeout_seconds": 5,
        },
    ).json()
    return project, novel, provider


def _generate(client, novel_id, provider_id, operation, idea="一个午夜失踪的故事"):
    response = client.post(
        "/api/novels/{}/story-engineering/generate".format(novel_id),
        json={"provider_id": provider_id, "operation": operation, "idea": idea},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_forward_story_engineering_end_to_end():
    server, port = _start_server()
    try:
        with TestClient(app) as client:
            _project, novel, provider = _bootstrap(client, port)
            novel_id = novel["id"]

            # 1. framework：生成 1 条 staged 候选，且不直接落库
            framework_candidates = _generate(client, novel_id, provider["id"], "framework")
            assert len(framework_candidates) == 1
            assert framework_candidates[0]["status"] == "staged"
            assert framework_candidates[0]["record_type"] == "staged_framework"

            with SessionLocal() as db:
                fresh = db.get(Novel, novel_id)
                assert fresh.synopsis == ""  # 生成阶段不落库

            # 接受 framework：空字段写入，已有非空字段保留
            accept = client.post(
                "/api/story-engineering/candidates/{}/accept".format(framework_candidates[0]["id"])
            )
            assert accept.status_code == 200, accept.text
            assert accept.json()["applied"] is True
            with SessionLocal() as db:
                fresh = db.get(Novel, novel_id)
                assert fresh.synopsis == "退信人在午夜城寻找失踪的姐姐。"  # 空 → 写入
                assert fresh.story_outline == "原总纲不可被覆盖。"  # 非空 → 不覆盖

            # 2. characters：生成 2 条，接受第一条落库为 Character
            character_candidates = _generate(client, novel_id, provider["id"], "characters")
            assert len(character_candidates) == 2
            client.post(
                "/api/story-engineering/candidates/{}/accept".format(character_candidates[0]["id"])
            ).raise_for_status()
            with SessionLocal() as db:
                names = {c.name for c in db.query(Character).filter(Character.novel_id == novel_id)}
                assert "林澈" in names
                assert "陆衡" not in names  # 第二条未接受

            # 3. world_rules：接受后落库为 WorldRule
            rule_candidates = _generate(client, novel_id, provider["id"], "world_rules")
            client.post(
                "/api/story-engineering/candidates/{}/accept".format(rule_candidates[0]["id"])
            ).raise_for_status()
            with SessionLocal() as db:
                rules = list(db.query(WorldRule).filter(WorldRule.novel_id == novel_id))
                assert any(r.name == "午夜锁死" and r.priority == 80 for r in rules)

            # 4. chapter_plan：接受后落库为 Chapter + ChapterOutline
            plan_candidates = _generate(client, novel_id, provider["id"], "chapter_plan")
            assert len(plan_candidates) == 2
            client.post(
                "/api/story-engineering/candidates/{}/accept".format(plan_candidates[0]["id"])
            ).raise_for_status()
            with SessionLocal() as db:
                chapters = list(db.query(Chapter).filter(Chapter.novel_id == novel_id))
                assert any(ch.title == "灯塔的地下室" for ch in chapters)
                target = next(ch for ch in chapters if ch.title == "灯塔的地下室")
                outline = (
                    db.query(ChapterOutline)
                    .filter(ChapterOutline.chapter_id == target.id)
                    .first()
                )
                assert outline is not None
                assert outline.goal == "建立悬念"

            # 5. reject：拒绝第二条 chapter_plan，不落库
            reject = client.post(
                "/api/story-engineering/candidates/{}/reject".format(plan_candidates[1]["id"])
            )
            assert reject.status_code == 200, reject.text
            assert reject.json()["status"] == "rejected"
            with SessionLocal() as db:
                chapters = list(db.query(Chapter).filter(Chapter.novel_id == novel_id))
                assert all(ch.title != "第二章占位" for ch in chapters)

            # 6. 绝不污染 Canon：CanonState 由建小说时创建，但前置物料接受不得写入它
            with SessionLocal() as db:
                canon = (
                    db.query(CanonState).filter(CanonState.novel_id == novel_id).first()
                )
                assert canon is not None
                assert canon.character_states_json == "{}"
                assert canon.relationships_json == "{}"
                assert canon.key_events_json == "[]"
                assert canon.chapter_summaries_json == "[]"

            # 7. 列表只返回前置物料候选
            listed = client.get(
                "/api/novels/{}/story-engineering/candidates".format(novel_id)
            ).json()
            assert len(listed) >= 6
            assert {item["record_type"] for item in listed} <= {
                "staged_framework",
                "staged_character",
                "staged_world_rule",
                "staged_chapter_plan",
            }
    finally:
        server.shutdown()


def test_forward_invalid_json_fails_explicitly():
    server, port = _start_server()
    try:
        with TestClient(app) as client:
            _project, novel, provider = _bootstrap(client, port)
            response = client.post(
                "/api/novels/{}/story-engineering/generate".format(novel["id"]),
                json={
                    "provider_id": provider["id"],
                    "operation": "framework",
                    "idea": "FORCE_BAD_JSON",
                },
            )
            assert response.status_code == 422
            assert response.json()["detail"]["code"] in {
                "JSON_PARSE_ERROR",
                "EMPTY_MODEL_OUTPUT",
                "SCHEMA_VALIDATION_ERROR",
            }
    finally:
        server.shutdown()
