import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from fastapi.testclient import TestClient

from app.main import app


ORIGINAL_CONTENT = "人工正式正文：自动写入前必须先保存备份。"
UNRELATED_FULL_TEXT = "UNRELATED_FULL_TEXT_MUST_NOT_ENTER_CONTEXT_" * 40


class AutoPipelineMockHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        prompt = payload.get("messages", [{}])[0].get("content", "")
        mode = getattr(self.server, "mode", "pass")

        if "AGENT: revision_writer" in prompt:
            content = (
                "修订后的章节正文。林澈留在下层维护区，按照连续性报告补充了纸质日志，"
                "并明确没有进入上层行政区。午夜七分钟锁死结束后，他才读取缓存指令。"
            )
        elif "AGENT: draft_writer" in prompt:
            content = (
                "章节初稿正文。林澈在午夜检查潮汐心脏，记录电子门锁死的七分钟。"
                "他在下层维护区发现一条来自上层的缓存指令，并把时间写入纸质日志。"
            )
        elif "AGENT: continuity_checker" in prompt:
            self.server.check_count = getattr(self.server, "check_count", 0) + 1
            if mode == "blocker":
                report = {
                    "passed": False,
                    "severity": "blocker",
                    "issues": [
                        {
                            "issue_id": "blocker-1",
                            "type": "canon",
                            "severity": "blocker",
                            "evidence": "正文改变了不可变世界规则",
                            "problem": "世界观硬冲突",
                            "suggested_fix": "需要人工重写设定相关段落",
                            "auto_fixable": False,
                            "affected_sections": ["结尾"],
                            "must_pause": True,
                        }
                    ],
                }
            elif mode in {
                "major_once",
                "major_unfixable_once",
                "timeline_pause_once",
            } and self.server.check_count == 1:
                report = {
                    "passed": False,
                    "severity": "major",
                    "issues": [
                        {
                            "issue_id": "major-1",
                            "type": "timeline" if mode == "timeline_pause_once" else "character",
                            "severity": "major",
                            "evidence": "人物权限边界不清楚",
                            "problem": "需要明确人物仍在下层",
                            "suggested_fix": "补充人物位置和纸质日志细节",
                            "auto_fixable": mode == "major_once",
                            "affected_sections": ["中段"],
                            "must_pause": mode == "timeline_pause_once",
                        }
                    ],
                }
            else:
                report = {"passed": True, "severity": "none", "issues": []}
            content = json.dumps(report, ensure_ascii=False)
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


def create_case(client, port, suffix):
    project = client.post("/api/projects", json={"name": "MVP3 {}".format(suffix)}).json()
    novel = client.post(
        "/api/novels",
        json={
            "project_id": project["id"],
            "title": "自动生产线 {}".format(suffix),
            "story_outline": "林澈调查潮汐城午夜锁死。",
        },
    ).json()
    chapter = client.post(
        "/api/chapters",
        json={
            "novel_id": novel["id"],
            "title": "目标章节",
            "content": ORIGINAL_CONTENT,
            "outline": {
                "goal": "确认午夜锁死规律",
                "outline_content": "留在下层记录七分钟异常。",
            },
        },
    ).json()
    provider = client.post(
        "/api/model-providers",
        json={
            "name": "MVP3 Mock {}".format(suffix),
            "provider_type": "openai_compatible",
            "base_url": "http://127.0.0.1:{}/v1".format(port),
            "model": "mvp3-mock",
            "timeout_seconds": 5,
        },
    ).json()
    return project, novel, chapter, provider


def start_auto(client, project, chapter, provider, mode, references=None):
    response = client.post(
        "/api/projects/{}/chapters/{}/auto-run".format(project["id"], chapter["id"]),
        json={
            "provider_id": provider["id"],
            "context_budget": 1600,
            "mode": mode,
            "max_revision_rounds_per_chapter": 2,
            "references": references or [],
        },
    )
    assert response.status_code == 202, response.text
    return response.json()["id"]


def wait_for_status(client, project_id, run_id, statuses):
    deadline = time.time() + 12
    while time.time() < deadline:
        response = client.get("/api/projects/{}/runs/{}".format(project_id, run_id))
        assert response.status_code == 200
        run = response.json()
        if run["status"] in statuses:
            return run
        time.sleep(0.03)
    raise AssertionError("Auto run did not reach {}".format(statuses))


def run_server(mode):
    server = ThreadingHTTPServer(("127.0.0.1", 0), AutoPipelineMockHandler)
    server.mode = mode
    server.check_count = 0
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_manual_review_mode_still_waits_and_preserves_content():
    server = run_server("pass")
    try:
        with TestClient(app) as client:
            project, _novel, chapter, provider = create_case(client, server.server_port, "manual")
            run = wait_for_status(
                client,
                project["id"],
                start_auto(client, project, chapter, provider, "manual_review"),
                {"waiting", "failed"},
            )
            assert run["status"] == "waiting"
            assert run["state"] == "WAIT_HUMAN_APPROVAL"
            assert run["auto_policy"]["mode"] == "manual_review"
            assert client.get("/api/chapters/{}".format(chapter["id"])).json()["content"] == ORIGINAL_CONTENT
    finally:
        server.shutdown()
        server.server_close()


def test_auto_run_defaults_to_ai_review_revision_and_commit():
    server = run_server("major_once")
    try:
        with TestClient(app) as client:
            project, _novel, chapter, provider = create_case(
                client, server.server_port, "default-auto-commit"
            )
            response = client.post(
                "/api/projects/{}/chapters/{}/auto-run".format(
                    project["id"], chapter["id"]
                ),
                json={
                    "provider_id": provider["id"],
                    "context_budget": 1600,
                    "max_revision_rounds_per_chapter": 3,
                },
            )
            assert response.status_code == 202, response.text
            run = wait_for_status(
                client,
                project["id"],
                response.json()["id"],
                {"committed", "paused", "failed"},
            )
            assert run["status"] == "committed"
            assert run["auto_policy"]["mode"] == "ai_auto_commit"
            assert len(run["revision_plans"]) == 1
            assert len(run["versions"]) >= 2
    finally:
        server.shutdown()
        server.server_close()


def test_waiting_manual_run_can_enable_ai_review_and_auto_commit():
    server = run_server("major_once")
    try:
        with TestClient(app) as client:
            project, _novel, chapter, provider = create_case(
                client, server.server_port, "ai-takeover"
            )
            waiting = wait_for_status(
                client,
                project["id"],
                start_auto(client, project, chapter, provider, "manual_review"),
                {"waiting", "failed"},
            )
            assert waiting["status"] == "waiting"
            assert waiting["continuity_report_json"]

            response = client.post(
                "/api/projects/{}/runs/{}/auto-continue".format(
                    project["id"], waiting["id"]
                ),
                json={
                    "note": "让 AI 按连续性报告定向修订",
                    "additional_revision_rounds": 3,
                },
            )
            assert response.status_code == 202, response.text
            assert response.json()["state"] == "BUILD_REVISION_PLAN"
            assert response.json()["auto_policy"]["mode"] == "ai_auto_commit"

            finished = wait_for_status(
                client,
                project["id"],
                waiting["id"],
                {"committed", "paused", "failed"},
            )
            assert finished["status"] == "committed"
            assert len(finished["revision_plans"]) == 1
            assert len(finished["versions"]) >= 2
            assert any(
                step["state"] == "AI_REVIEW_ENABLED"
                for step in finished["steps"]
            )
            assert client.get(
                "/api/chapters/{}".format(chapter["id"])
            ).json()["content"] != ORIGINAL_CONTENT
    finally:
        server.shutdown()
        server.server_close()


def test_ai_takeover_refuses_blocker_report():
    server = run_server("blocker")
    try:
        with TestClient(app) as client:
            project, _novel, chapter, provider = create_case(
                client, server.server_port, "takeover-blocker"
            )
            waiting = wait_for_status(
                client,
                project["id"],
                start_auto(client, project, chapter, provider, "manual_review"),
                {"waiting", "failed"},
            )
            response = client.post(
                "/api/projects/{}/runs/{}/auto-continue".format(
                    project["id"], waiting["id"]
                ),
                json={"note": "尝试 AI 接管", "additional_revision_rounds": 3},
            )
            assert response.status_code == 409
            assert response.json()["detail"]["code"] == "BLOCKER_REQUIRES_HUMAN"
            assert client.get(
                "/api/chapters/{}".format(chapter["id"])
            ).json()["content"] == ORIGINAL_CONTENT
    finally:
        server.shutdown()
        server.server_close()


def test_ai_auto_revise_creates_plan_and_new_version_then_waits():
    server = run_server("major_once")
    try:
        with TestClient(app) as client:
            project, _novel, chapter, provider = create_case(client, server.server_port, "revise")
            run = wait_for_status(
                client,
                project["id"],
                start_auto(client, project, chapter, provider, "ai_auto_revise"),
                {"waiting", "paused", "failed"},
            )
            assert run["status"] == "waiting"
            assert len(run["revision_plans"]) == 1
            assert len(run["versions"]) == 2
            assert run["versions"][1]["kind"] == "revision"
            assert run["versions"][1]["parent_version_id"] == run["versions"][0]["id"]
            assert run["auto_policy"]["revision_rounds"] == 1
            assert client.get("/api/chapters/{}".format(chapter["id"])).json()["content"] == ORIGINAL_CONTENT
    finally:
        server.shutdown()
        server.server_close()


def test_ai_auto_revise_attempts_checker_non_fixable_major_issue():
    server = run_server("major_unfixable_once")
    try:
        with TestClient(app) as client:
            project, _novel, chapter, provider = create_case(
                client, server.server_port, "forced-revise"
            )
            run = wait_for_status(
                client,
                project["id"],
                start_auto(client, project, chapter, provider, "ai_auto_revise"),
                {"waiting", "paused", "failed"},
            )
            assert run["status"] == "waiting"
            assert run["auto_policy"]["revision_rounds"] == 1
            assert len(run["revision_plans"]) == 1
            fixes = json.loads(run["revision_plans"][0]["fixes_json"])
            assert fixes[0]["checker_auto_fixable"] is False
            assert len(run["versions"]) == 2
            assert run["versions"][1]["kind"] == "revision"
            assert run["versions"][1]["parent_version_id"] == run["versions"][0]["id"]
    finally:
        server.shutdown()
        server.server_close()


def test_timeline_major_marked_must_pause_is_still_revised_when_text_fix_exists():
    server = run_server("timeline_pause_once")
    try:
        with TestClient(app) as client:
            project, _novel, chapter, provider = create_case(
                client, server.server_port, "timeline-directed-revision"
            )
            run = wait_for_status(
                client,
                project["id"],
                start_auto(client, project, chapter, provider, "ai_auto_commit"),
                {"committed", "paused", "failed"},
            )
            assert run["status"] == "committed"
            assert run["auto_policy"]["revision_rounds"] == 1
            assert len(run["revision_plans"]) == 1
            fixes = json.loads(run["revision_plans"][0]["fixes_json"])
            assert fixes[0]["must_pause"] is True
            assert len(run["versions"]) >= 2
    finally:
        server.shutdown()
        server.server_close()


def test_resume_paused_auto_run_continues_with_revision_not_new_draft():
    server = run_server("major_unfixable_once")
    try:
        with TestClient(app) as client:
            project, _novel, chapter, provider = create_case(
                client, server.server_port, "resume-revision"
            )
            response = client.post(
                "/api/projects/{}/chapters/{}/auto-run".format(
                    project["id"], chapter["id"]
                ),
                json={
                    "provider_id": provider["id"],
                    "context_budget": 1600,
                    "mode": "ai_auto_revise",
                    "max_revision_rounds_per_chapter": 0,
                },
            )
            assert response.status_code == 202
            paused = wait_for_status(
                client,
                project["id"],
                response.json()["id"],
                {"paused", "failed"},
            )
            assert paused["status"] == "paused"
            assert len(paused["versions"]) == 1

            server.mode = "pass"
            resumed = client.post(
                "/api/projects/{}/runs/{}/resume".format(
                    project["id"], paused["id"]
                ),
                json={
                    "note": "继续自动修订",
                    "additional_revision_rounds": 2,
                },
            )
            assert resumed.status_code == 202
            assert resumed.json()["state"] == "BUILD_REVISION_PLAN"
            assert resumed.json()["auto_policy"]["max_revision_rounds_per_chapter"] == 2
            finished = wait_for_status(
                client,
                project["id"],
                paused["id"],
                {"waiting", "paused", "failed"},
            )
            assert finished["status"] == "waiting"
            assert len(finished["versions"]) == 2
            assert finished["versions"][1]["kind"] == "revision"
            writer_agents = [
                call["agent_name"]
                for call in finished["model_calls"]
                if call["status"] == "completed"
            ]
            assert writer_agents.count("draft_writer") == 1
            assert writer_agents.count("revision_writer") == 1
    finally:
        server.shutdown()
        server.server_close()


def test_ai_auto_commit_backs_up_content_writes_summary_memory_and_audit():
    server = run_server("major_once")
    try:
        with TestClient(app) as client:
            project, _novel, chapter, provider = create_case(client, server.server_port, "commit")
            run = wait_for_status(
                client,
                project["id"],
                start_auto(client, project, chapter, provider, "ai_auto_commit"),
                {"committed", "paused", "failed"},
            )
            assert run["status"] == "committed"
            assert run["state"] == "MEMORY_UPDATED"
            assert run["approved_version_id"] == run["current_version_id"]
            assert any(version["kind"] == "pre_auto_commit_backup" for version in run["versions"])
            assert any(step["state"] == "AUTO_COMMITTING" for step in run["steps"])
            assert any(step["state"] == "COMMITTED" for step in run["steps"])
            assert any(step["state"] == "UPDATING_STORY_MEMORY" for step in run["steps"])

            updated = client.get("/api/chapters/{}".format(chapter["id"])).json()
            assert updated["content"] == next(
                version["content_markdown"]
                for version in run["versions"]
                if version["id"] == run["approved_version_id"]
            )
            assert updated["summary"]
            memory = client.get("/api/projects/{}/story-memory".format(project["id"])).json()
            assert len(memory) == 1
            assert memory[0]["record_type"] == "chapter_summary"
            assert memory[0]["source_id"] == run["approved_version_id"]
            assert chapter["id"] in memory[0]["evidence_json"]
    finally:
        server.shutdown()
        server.server_close()


def test_blocker_pauses_and_never_auto_commits():
    server = run_server("blocker")
    try:
        with TestClient(app) as client:
            project, _novel, chapter, provider = create_case(client, server.server_port, "blocker")
            run = wait_for_status(
                client,
                project["id"],
                start_auto(client, project, chapter, provider, "ai_auto_commit"),
                {"paused", "failed", "committed"},
            )
            assert run["status"] == "paused"
            assert run["state"] == "PAUSED"
            assert run["approved_version_id"] is None
            assert run["auto_policy"]["pause_reason"]
            assert client.get("/api/chapters/{}".format(chapter["id"])).json()["content"] == ORIGINAL_CONTENT
    finally:
        server.shutdown()
        server.server_close()


def test_chapter_and_version_references_use_reference_pack_without_all_full_text():
    server = run_server("pass")
    try:
        with TestClient(app) as client:
            project, novel, target, provider = create_case(client, server.server_port, "references")
            source = client.post(
                "/api/chapters",
                json={
                    "novel_id": novel["id"],
                    "title": "参考章节",
                    "content": "SELECTED_REFERENCE_CHAPTER_CONTENT",
                    "outline": {"goal": "", "outline_content": ""},
                },
            ).json()
            client.post(
                "/api/chapters",
                json={
                    "novel_id": novel["id"],
                    "title": "无关章节",
                    "content": UNRELATED_FULL_TEXT,
                    "outline": {"goal": "", "outline_content": ""},
                },
            )
            run = wait_for_status(
                client,
                project["id"],
                start_auto(
                    client,
                    project,
                    target,
                    provider,
                    "manual_review",
                    references=[
                        {
                            "type": "chapter",
                            "source_id": source["id"],
                            "reason": "参考叙事节奏",
                        }
                    ],
                ),
                {"waiting", "failed"},
            )
            assert run["status"] == "waiting"
            assert run["auto_policy"]["reference_pack_id"]
            assert "SELECTED_REFERENCE_CHAPTER_CONTENT" in run["assembled_context"]
            assert "参考叙事节奏" in run["assembled_context"]
            assert "UNRELATED_FULL_TEXT_MUST_NOT_ENTER_CONTEXT" not in run["assembled_context"]
            pack = client.get(
                "/api/projects/{}/reference-packs/{}".format(
                    project["id"],
                    run["auto_policy"]["reference_pack_id"],
                )
            ).json()
            assert json.loads(pack["items_json"])[0]["reference_id"] == source["id"]
            version_pack = client.post(
                "/api/projects/{}/reference-packs".format(project["id"]),
                json={
                    "novel_id": novel["id"],
                    "chapter_id": target["id"],
                    "references": [
                        {
                            "type": "chapter_version",
                            "source_id": run["current_version_id"],
                            "reason": "参考已生成版本",
                        }
                    ],
                },
            )
            assert version_pack.status_code == 201
            version_item = json.loads(version_pack.json()["items_json"])[0]
            assert version_item["type"] == "chapter_version"
            assert version_item["source_version_id"] == run["current_version_id"]
    finally:
        server.shutdown()
        server.server_close()
