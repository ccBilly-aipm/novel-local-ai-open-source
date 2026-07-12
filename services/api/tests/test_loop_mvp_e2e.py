import json
import re
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db import SessionLocal
from app.main import app
from app.models.loop_entities import ChapterLoopRun, ChapterVersion, ModelCall, RunStep


EVIDENCE_PATH = Path("/tmp/novel_loop_mvp_evidence.json")
ORIGINAL_CONTENT = "人工占位正文：Loop 初稿不得覆盖这里。"


class TidalCityMockHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        prompt = payload.get("messages", [{}])[0].get("content", "")
        chapter_match = re.search(r"章节 ID：([^\n]+)", prompt)
        chapter_id = chapter_match.group(1).strip() if chapter_match else ""

        if "AGENT: draft_writer" in prompt:
            if getattr(self.server, "draft_delay", 0):
                time.sleep(self.server.draft_delay)
            content = json.dumps(
                {
                    "chapter_id": chapter_id,
                    "draft_markdown": (
                        "23:58，林澈留在潮汐城下层维护区检查潮汐心脏的冷却回路。"
                        "午夜整点，警报灯熄灭，所有电子门同时锁死。"
                        "他没有上层通行权限，只能在原地用纸笔记录脉冲变化。"
                        "00:07，电子门恢复。林澈从离线维护终端的缓存里发现一条"
                        "来自上层行政区的加密指令，但没有见到许岚，也不知道上层的调查计划。"
                    ),
                    "scene_breakdown": [
                        {"scene": "下层维护区", "result": "记录 00:00 到 00:07 锁死异常"},
                        {"scene": "离线维护终端", "result": "发现上层加密指令"},
                    ],
                    "self_notes": [],
                },
                ensure_ascii=False,
            )
        elif "AGENT: continuity_checker" in prompt:
            if getattr(self.server, "invalid_continuity", False):
                content = '{"passed": true, "severity": "none", "issues": ['
            else:
                content = json.dumps(
                    {
                        "passed": True,
                        "severity": "none",
                        "issues": [],
                    },
                    ensure_ascii=False,
                )
        else:
            content = json.dumps({"unexpected": True})

        body = json.dumps(
            {
                "choices": [{"message": {"role": "assistant", "content": content}}],
                "usage": {"prompt_tokens": 420, "completion_tokens": 180},
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *_args):
        return


def wait_for_terminal(client, project_id, run_id):
    deadline = time.time() + 15
    while time.time() < deadline:
        response = client.get("/api/projects/{}/runs/{}".format(project_id, run_id))
        assert response.status_code == 200
        run = response.json()
        if run["status"] in {"waiting", "failed"}:
            return run
        time.sleep(0.05)
    raise AssertionError("Loop run did not reach a terminal review state")


def create_tidal_city_sample(client, server_port, suffix):
    project = client.post(
        "/api/projects",
        json={
            "name": "Loop Agent MVP Test Novel {}".format(suffix),
            "description": "潮汐城单章 Loop 验收样本",
        },
    ).json()
    novel = client.post(
        "/api/novels",
        json={
            "project_id": project["id"],
            "title": "潮汐城午夜异常 {}".format(suffix),
            "synopsis": "下层维护员调查潮汐心脏午夜失控。",
            "story_outline": (
                "故事发生在近未来的封闭海上城市潮汐城。城市分为上层行政区、"
                "中层居民区和下层维护区，核心能源来自潮汐心脏。"
            ),
            "style_guide": "近未来悬疑；具体、克制；重视时间与空间边界。",
            "forbidden_content": "不得让人物无权限跨层，不得提前共享未获得的信息。",
        },
    ).json()

    lin_che = client.post(
        "/api/characters",
        json={
            "novel_id": novel["id"],
            "name": "林澈",
            "role": "下层维护员",
            "description": "查清潮汐心脏失控原因；害怕被上层当成破坏者处理。",
            "goals": "查清潮汐心脏每天午夜短暂失控的原因。",
            "current_state": {
                "location": "下层维护区",
                "knowledge_boundary": "知道午夜失控现象，但不知道上层调查计划",
            },
            "notes": "禁止无铺垫进入上层行政区；禁止提前知道许岚的调查内容。",
        },
    ).json()
    xu_lan = client.post(
        "/api/characters",
        json={
            "novel_id": novel["id"],
            "name": "许岚",
            "role": "上层安全调查员",
            "description": "找出系统异常来源；害怕能源系统被人为破坏。",
            "goals": "调查城市能源系统异常。",
            "current_state": {
                "location": "上层行政区",
                "knowledge_boundary": "知道系统异常，但不知道林澈发现午夜规律",
            },
            "notes": "第一章不能完全信任林澈；不能提前知道林澈手里的维护日志。",
        },
    ).json()

    rules = []
    for name, description in [
        ("电子门锁死窗口", "潮汐心脏失控时，所有电子门会在 00:00 到 00:07 锁死。"),
        ("林澈权限边界", "林澈没有上层行政区通行权限。"),
        ("许岚知识边界", "许岚不能在第一章提前知道林澈的发现。"),
        ("潮汐心脏定义", "潮汐心脏是潮汐城的核心能源，不是普通机器。"),
    ]:
        rules.append(
            client.post(
                "/api/world-rules",
                json={
                    "novel_id": novel["id"],
                    "name": name,
                    "description": description,
                    "priority": 100,
                },
            ).json()
        )

    chapter = client.post(
        "/api/chapters",
        json={
            "novel_id": novel["id"],
            "title": "第一章 午夜锁死",
            "content": ORIGINAL_CONTENT,
            "outline": {
                "goal": (
                    "林澈在下层维护区发现 00:00 到 00:07 的电子门锁死异常；"
                    "不能离开下层，也不能遇见许岚；结尾发现来自上层的加密指令。"
                ),
                "outline_content": (
                    "林澈午夜检查潮汐心脏，记录七分钟锁死窗口。"
                    "门恢复后，他在缓存里发现上层加密指令。"
                ),
                "character_ids": [lin_che["id"]],
                "required_plot_points": [
                    "00:00 到 00:07 电子门锁死",
                    "林澈留在下层",
                    "许岚不出现且不知情",
                    "章末发现上层加密指令",
                ],
            },
        },
    ).json()

    provider = client.post(
        "/api/model-providers",
        json={
            "name": "Tidal City Mock {}".format(suffix),
            "provider_type": "openai_compatible",
            "base_url": "http://127.0.0.1:{}/v1".format(server_port),
            "model": "tidal-city-mock",
            "timeout_seconds": 10,
        },
    ).json()
    return {
        "project": project,
        "novel": novel,
        "characters": [lin_che, xu_lan],
        "rules": rules,
        "chapter": chapter,
        "provider": provider,
    }


def database_counts(run_id):
    with SessionLocal() as db:
        return {
            "loop_runs": db.scalar(
                select(func.count()).select_from(ChapterLoopRun).where(ChapterLoopRun.id == run_id)
            ),
            "steps": db.scalar(
                select(func.count()).select_from(RunStep).where(RunStep.run_id == run_id)
            ),
            "model_calls": db.scalar(
                select(func.count()).select_from(ModelCall).where(ModelCall.run_id == run_id)
            ),
            "versions": db.scalar(
                select(func.count()).select_from(ChapterVersion).where(ChapterVersion.run_id == run_id)
            ),
        }


def compact_run(run):
    report = json.loads(run["continuity_report_json"]) if run["continuity_report_json"] else {}
    return {
        "run_id": run["id"],
        "state": run["state"],
        "status": run["status"],
        "error_code": run["error_code"],
        "error": run["error"],
        "current_version_id": run["current_version_id"],
        "created_at": run["created_at"],
        "started_at": run["started_at"],
        "finished_at": run["finished_at"],
        "context_characters": len(run["assembled_context"]),
        "continuity_report": report,
        "steps": [
            {
                "sequence": step["sequence"],
                "state": step["state"],
                "status": step["status"],
                "error_code": step["error_code"],
                "started_at": step["started_at"],
                "finished_at": step["finished_at"],
                "output_json": json.loads(step["output_json"] or "{}"),
            }
            for step in run["steps"]
        ],
        "model_calls": [
            {
                "agent_name": call["agent_name"],
                "status": call["status"],
                "error_code": call["error_code"],
                "duration_ms": call["duration_ms"],
                "input_tokens": call["input_tokens"],
                "output_tokens": call["output_tokens"],
                "parsed_json_valid": bool(call["parsed_json"]),
                "response_preview": call["response"][:160],
            }
            for call in run["model_calls"]
        ],
        "versions": [
            {
                "id": version["id"],
                "version_number": version["version_number"],
                "kind": version["kind"],
                "content_hash": version["content_hash"],
                "character_count": len(version["content_markdown"]),
                "content_preview": version["content_markdown"][:180],
            }
            for version in run["versions"]
        ],
    }


def test_loop_mvp_two_round_e2e():
    server = ThreadingHTTPServer(("127.0.0.1", 0), TidalCityMockHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    evidence = {
        "test_date": datetime.now().astimezone().isoformat(),
        "provider": {
            "type": "mock OpenAI-compatible HTTP server",
            "port": server.server_port,
            "real_local_model_required": False,
        },
    }

    try:
        with TestClient(app) as client:
            sample = create_tidal_city_sample(client, server.server_port, "Round 1")
            chapter_before = client.get(
                "/api/chapters/{}".format(sample["chapter"]["id"])
            ).json()
            create_response = client.post(
                "/api/projects/{}/chapters/{}/run".format(
                    sample["project"]["id"],
                    sample["chapter"]["id"],
                ),
                json={
                    "provider_id": sample["provider"]["id"],
                    "context_budget": 2400,
                    "options": {"max_tokens": 1200},
                },
            )
            assert create_response.status_code == 202
            round1 = wait_for_terminal(
                client,
                sample["project"]["id"],
                create_response.json()["id"],
            )
            chapter_after = client.get(
                "/api/chapters/{}".format(sample["chapter"]["id"])
            ).json()

            assert round1["state"] == "WAIT_HUMAN_APPROVAL"
            assert round1["status"] == "waiting"
            assert json.loads(round1["continuity_report_json"]) == {
                "passed": True,
                "severity": "none",
                "issues": [],
            }
            assert len(round1["steps"]) == 5
            assert len(round1["model_calls"]) == 2
            assert len(round1["versions"]) == 1
            assert chapter_before["content"] == ORIGINAL_CONTENT
            assert chapter_after["content"] == ORIGINAL_CONTENT
            assert "00:07" in round1["versions"][0]["content_markdown"]
            assert "上层行政区的加密指令" in round1["versions"][0]["content_markdown"]

            evidence["round1"] = {
                "input": {
                    "project": sample["project"],
                    "novel": sample["novel"],
                    "characters": sample["characters"],
                    "rules": sample["rules"],
                    "chapter": sample["chapter"],
                    "provider": sample["provider"],
                },
                "create_status_code": create_response.status_code,
                "create_response": {
                    "id": create_response.json()["id"],
                    "state": create_response.json()["state"],
                    "status": create_response.json()["status"],
                },
                "run": compact_run(round1),
                "database_counts": database_counts(round1["id"]),
                "chapter_content_before": chapter_before["content"],
                "chapter_content_after": chapter_after["content"],
                "chapter_content_unchanged": chapter_before["content"] == chapter_after["content"],
            }

            server.draft_delay = 0.8
            duplicate_sample = create_tidal_city_sample(client, server.server_port, "Round 2 Conflict")
            first_response = client.post(
                "/api/projects/{}/chapters/{}/run".format(
                    duplicate_sample["project"]["id"],
                    duplicate_sample["chapter"]["id"],
                ),
                json={"provider_id": duplicate_sample["provider"]["id"], "context_budget": 2400},
            )
            assert first_response.status_code == 202
            duplicate_response = client.post(
                "/api/projects/{}/chapters/{}/run".format(
                    duplicate_sample["project"]["id"],
                    duplicate_sample["chapter"]["id"],
                ),
                json={"provider_id": duplicate_sample["provider"]["id"], "context_budget": 2400},
            )
            assert duplicate_response.status_code == 409
            conflict_run = wait_for_terminal(
                client,
                duplicate_sample["project"]["id"],
                first_response.json()["id"],
            )
            with SessionLocal() as db:
                active_case_run_count = db.scalar(
                    select(func.count())
                    .select_from(ChapterLoopRun)
                    .where(ChapterLoopRun.chapter_id == duplicate_sample["chapter"]["id"])
                )
            assert active_case_run_count == 1

            server.draft_delay = 0
            server.invalid_continuity = True
            invalid_sample = create_tidal_city_sample(client, server.server_port, "Round 2 JSON")
            invalid_response = client.post(
                "/api/projects/{}/chapters/{}/run".format(
                    invalid_sample["project"]["id"],
                    invalid_sample["chapter"]["id"],
                ),
                json={"provider_id": invalid_sample["provider"]["id"], "context_budget": 2400},
            )
            assert invalid_response.status_code == 202
            invalid_run = wait_for_terminal(
                client,
                invalid_sample["project"]["id"],
                invalid_response.json()["id"],
            )
            invalid_chapter_after = client.get(
                "/api/chapters/{}".format(invalid_sample["chapter"]["id"])
            ).json()

            assert invalid_run["state"] == "FAILED"
            assert invalid_run["status"] == "failed"
            assert invalid_run["error_code"] == "JSON_PARSE_ERROR"
            assert invalid_run["steps"][-1]["state"] == "CHECK_CONTINUITY"
            assert invalid_run["steps"][-1]["status"] == "failed"
            assert invalid_run["model_calls"][-1]["status"] == "failed"
            assert invalid_run["model_calls"][-1]["error_code"] == "JSON_PARSE_ERROR"
            assert invalid_run["model_calls"][-2]["response"].startswith('{"passed": true')
            assert invalid_run["model_calls"][-1]["agent_name"] == "continuity_checker_json_repair"
            assert invalid_run["continuity_report_json"] == ""
            assert invalid_chapter_after["content"] == ORIGINAL_CONTENT

            evidence["round2"] = {
                "scenario_a_duplicate_active_run": {
                    "first_status_code": first_response.status_code,
                    "first_run": compact_run(conflict_run),
                    "duplicate_status_code": duplicate_response.status_code,
                    "duplicate_response": duplicate_response.json(),
                    "chapter_run_count": active_case_run_count,
                },
                "scenario_b_invalid_json": {
                    "create_status_code": invalid_response.status_code,
                    "run": compact_run(invalid_run),
                    "database_counts": database_counts(invalid_run["id"]),
                    "chapter_content_after": invalid_chapter_after["content"],
                    "chapter_content_unchanged": invalid_chapter_after["content"] == ORIGINAL_CONTENT,
                    "dedicated_check_report_table": False,
                    "report_storage": [
                        "chapter_loop_runs.continuity_report_json",
                        "run_steps.output_json",
                        "model_calls.parsed_json",
                    ],
                },
            }
    finally:
        server.shutdown()
        server.server_close()

    EVIDENCE_PATH.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("LOOP_MVP_EVIDENCE={}".format(EVIDENCE_PATH))
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
