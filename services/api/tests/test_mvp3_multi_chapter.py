import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models.auto_entities import MultiChapterRun


ORIGINAL = "原始人工正文，任何自动写入和恢复操作都必须保留备份。"


class MultiChapterMockHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        prompt = payload.get("messages", [{}])[0].get("content", "")
        mode = getattr(self.server, "mode", "pass")

        if "AGENT: draft_writer" in prompt:
            self.server.draft_count = getattr(self.server, "draft_count", 0) + 1
            content = (
                "自动生产章节正文第 {} 次。林澈按照章节计划留在下层维护区，"
                "记录午夜锁死窗口，并在结尾保留下一章需要继续调查的线索。"
            ).format(self.server.draft_count)
        elif "AGENT: revision_writer" in prompt:
            content = "自动修订后的完整章节正文。人物位置、时间线和世界规则已经按计划校正。"
        elif "AGENT: continuity_checker" in prompt:
            if mode == "blocker":
                report = {
                    "passed": False,
                    "severity": "blocker",
                    "issues": [
                        {
                            "issue_id": "blocker",
                            "type": "canon",
                            "severity": "blocker",
                            "evidence": "世界规则冲突",
                            "problem": "不可自动修复的世界观硬冲突",
                            "suggested_fix": "人工调整章节计划",
                            "auto_fixable": False,
                            "affected_sections": ["全文"],
                            "must_pause": True,
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


def serve(mode="pass"):
    server = ThreadingHTTPServer(("127.0.0.1", 0), MultiChapterMockHandler)
    server.mode = mode
    server.draft_count = 0
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def create_case(client, port, suffix, chapter_count=3, missing_plan_index=None):
    project = client.post("/api/projects", json={"name": "Phase3 {}".format(suffix)}).json()
    novel = client.post(
        "/api/novels",
        json={
            "project_id": project["id"],
            "title": "多章生产 {}".format(suffix),
            "story_outline": "林澈连续调查潮汐城午夜锁死。",
        },
    ).json()
    chapters = []
    for index in range(chapter_count):
        missing = missing_plan_index == index
        chapters.append(
            client.post(
                "/api/chapters",
                json={
                    "novel_id": novel["id"],
                    "title": "第 {} 章".format(index + 1),
                    "content": ORIGINAL if index == 0 else "",
                    "outline": {
                        "goal": "" if missing else "推进第 {} 章调查".format(index + 1),
                        "outline_content": "" if missing else "按顺序记录线索并留下后续钩子。",
                    },
                },
            ).json()
        )
    provider = client.post(
        "/api/model-providers",
        json={
            "name": "Phase3 Mock {}".format(suffix),
            "provider_type": "openai_compatible",
            "base_url": "http://127.0.0.1:{}/v1".format(port),
            "model": "phase3-mock",
            "timeout_seconds": 5,
        },
    ).json()
    return project, novel, chapters, provider


def create_multi(client, project, chapter, provider, mode="ai_auto_commit", count=3):
    response = client.post(
        "/api/projects/{}/multi-chapter-runs".format(project["id"]),
        json={
            "provider_id": provider["id"],
            "start_chapter_id": chapter["id"],
            "chapter_count": count,
            "mode": mode,
            "context_budget": 1600,
            "checkpoint_every": 3,
            "permission_confirmed": mode == "full_autonomous",
        },
    )
    assert response.status_code == 202, response.text
    return response.json()


def wait_multi(client, project_id, run_id, statuses, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = client.get(
            "/api/projects/{}/multi-chapter-runs/{}".format(project_id, run_id)
        )
        assert response.status_code == 200
        run = response.json()
        if run["status"] in statuses:
            return run
        time.sleep(0.04)
    raise AssertionError("Multi Chapter Run did not reach {}".format(statuses))


def wait_loop(client, project_id, run_id, statuses, timeout=12):
    deadline = time.time() + timeout
    while time.time() < deadline:
        run = client.get("/api/projects/{}/runs/{}".format(project_id, run_id)).json()
        if run["status"] in statuses:
            return run
        time.sleep(0.04)
    raise AssertionError("Child Loop did not reach {}".format(statuses))


def test_three_chapters_auto_commit_and_create_checkpoint():
    server = serve()
    try:
        with TestClient(app) as client:
            project, _novel, chapters, provider = create_case(
                client, server.server_port, "three"
            )
            parent = create_multi(client, project, chapters[0], provider)
            finished = wait_multi(
                client,
                project["id"],
                parent["id"],
                {"completed", "paused", "failed"},
            )
            assert finished["status"] == "completed"
            assert finished["current_index"] == 3
            assert len(json.loads(finished["completed_chapter_ids_json"])) == 3
            assert len(json.loads(finished["loop_run_ids_json"])) == 3
            for chapter in chapters:
                updated = client.get("/api/chapters/{}".format(chapter["id"])).json()
                assert updated["content"].startswith("自动生产章节正文")
                assert updated["summary"]
            checkpoints = client.get(
                "/api/projects/{}/checkpoints".format(project["id"])
            ).json()
            assert len(checkpoints) == 1
            assert len(json.loads(checkpoints[0]["evidence_json"])) == 3
    finally:
        server.shutdown()
        server.server_close()


def test_missing_chapter_plan_uses_deterministic_fallback_and_continues():
    server = serve()
    try:
        with TestClient(app) as client:
            project, _novel, chapters, provider = create_case(
                client,
                server.server_port,
                "missing-plan",
                missing_plan_index=1,
            )
            parent = create_multi(client, project, chapters[0], provider)
            finished = wait_multi(
                client,
                project["id"],
                parent["id"],
                {"completed", "paused", "failed"},
            )
            assert finished["status"] == "completed"
            updated = client.get("/api/chapters/{}".format(chapters[1]["id"])).json()
            assert updated["content"].startswith("自动生产章节正文")
            assert updated["outline"]["goal"]
            assert "[AUTO_CHAPTER_PLAN]" in updated["outline"]["style_notes"]
    finally:
        server.shutdown()
        server.server_close()


def test_manual_multi_run_continues_after_human_approval_and_resume():
    server = serve()
    try:
        with TestClient(app) as client:
            project, _novel, chapters, provider = create_case(
                client, server.server_port, "manual", chapter_count=1
            )
            parent = create_multi(
                client, project, chapters[0], provider, mode="manual_review", count=1
            )
            waiting = wait_multi(
                client, project["id"], parent["id"], {"waiting_human", "failed"}
            )
            assert waiting["status"] == "waiting_human"
            child_id = waiting["current_loop_run_id"]
            child = wait_loop(client, project["id"], child_id, {"waiting"})
            approved = client.post(
                "/api/projects/{}/runs/{}/approve".format(project["id"], child_id),
                json={"feedback": "批准后继续生产线"},
            )
            assert approved.status_code == 200
            resumed = client.post(
                "/api/projects/{}/multi-chapter-runs/{}/resume".format(
                    project["id"], parent["id"]
                ),
                json={"note": "人工审批完成"},
            )
            assert resumed.status_code == 202
            finished = wait_multi(client, project["id"], parent["id"], {"completed", "failed"})
            assert finished["status"] == "completed"
            assert finished["current_index"] == 1
            assert approved.json()["approved_version_id"] == child["current_version_id"]
    finally:
        server.shutdown()
        server.server_close()


def test_ai_takeover_converts_waiting_manual_pipeline_and_continues():
    server = serve()
    try:
        with TestClient(app) as client:
            project, _novel, chapters, provider = create_case(
                client, server.server_port, "takeover-pipeline", chapter_count=2
            )
            parent = create_multi(
                client, project, chapters[0], provider, mode="manual_review", count=2
            )
            waiting = wait_multi(
                client, project["id"], parent["id"], {"waiting_human", "failed"}
            )
            child_id = waiting["current_loop_run_id"]
            response = client.post(
                "/api/projects/{}/runs/{}/auto-continue".format(
                    project["id"], child_id
                ),
                json={
                    "note": "AI 接管当前及后续章节",
                    "additional_revision_rounds": 3,
                },
            )
            assert response.status_code == 202, response.text
            assert response.json()["auto_policy"]["mode"] == "ai_auto_commit"

            finished = wait_multi(
                client,
                project["id"],
                parent["id"],
                {"completed", "paused", "failed"},
            )
            assert finished["status"] == "completed"
            assert finished["mode"] == "ai_auto_commit"
            assert finished["current_index"] == 2
            for chapter in chapters:
                assert client.get(
                    "/api/chapters/{}".format(chapter["id"])
                ).json()["content"] != ORIGINAL
    finally:
        server.shutdown()
        server.server_close()


def test_waiting_parent_resume_returns_approval_guidance():
    server = serve()
    try:
        with TestClient(app) as client:
            project, _novel, chapters, provider = create_case(
                client, server.server_port, "waiting-guidance", chapter_count=1
            )
            parent = create_multi(
                client, project, chapters[0], provider, mode="manual_review", count=1
            )
            waiting = wait_multi(
                client, project["id"], parent["id"], {"waiting_human", "failed"}
            )
            assert waiting["status"] == "waiting_human"

            response = client.post(
                "/api/projects/{}/multi-chapter-runs/{}/resume".format(
                    project["id"], parent["id"]
                ),
                json={"note": "误点恢复", "additional_revision_rounds": 1},
            )

            assert response.status_code == 409
            detail = response.json()["detail"]
            assert detail["code"] == "CHAPTER_AWAITING_APPROVAL"
            assert detail["active_run_id"] == parent["id"]
            assert detail["current_loop_run_id"] == waiting["current_loop_run_id"]
            assert detail["recovery_action"] == "open_child_run"
    finally:
        server.shutdown()
        server.server_close()


def test_paused_parent_resume_reports_current_active_pipeline():
    server = serve()
    try:
        with TestClient(app) as client:
            project, novel, chapters, provider = create_case(
                client, server.server_port, "active-parent-conflict", chapter_count=1
            )
            active = create_multi(
                client, project, chapters[0], provider, mode="manual_review", count=1
            )
            wait_multi(client, project["id"], active["id"], {"waiting_human", "failed"})

            with SessionLocal() as db:
                paused = MultiChapterRun(
                    project_id=project["id"],
                    novel_id=novel["id"],
                    start_chapter_id=chapters[0]["id"],
                    provider_id=provider["id"],
                    mode="ai_auto_commit",
                    chapter_count=1,
                    chapter_ids_json=json.dumps([chapters[0]["id"]]),
                    policy_json="{}",
                    references_json="[]",
                    options_json="{}",
                    status="paused",
                    active_slot=0,
                    pause_reason="Historical paused pipeline",
                )
                db.add(paused)
                db.commit()
                paused_id = paused.id

            response = client.post(
                "/api/projects/{}/multi-chapter-runs/{}/resume".format(
                    project["id"], paused_id
                ),
                json={"note": "恢复历史任务", "additional_revision_rounds": 1},
            )

            assert response.status_code == 409
            detail = response.json()["detail"]
            assert detail["code"] == "ACTIVE_MULTI_CHAPTER_RUN_EXISTS"
            assert detail["active_run_id"] == active["id"]
            assert detail["active_run_status"] == "waiting_human"
            with SessionLocal() as db:
                unchanged = db.get(MultiChapterRun, paused_id)
                assert unchanged.status == "paused"
                assert unchanged.active_slot == 0
    finally:
        server.shutdown()
        server.server_close()


def test_blocked_child_can_resume_after_user_fixes_conditions():
    server = serve("blocker")
    try:
        with TestClient(app) as client:
            project, _novel, chapters, provider = create_case(
                client, server.server_port, "resume", chapter_count=1
            )
            parent = create_multi(client, project, chapters[0], provider, count=1)
            paused = wait_multi(client, project["id"], parent["id"], {"paused", "failed"})
            assert paused["status"] == "paused"
            assert client.get("/api/chapters/{}".format(chapters[0]["id"])).json()["content"] == ORIGINAL
            server.mode = "pass"
            response = client.post(
                "/api/projects/{}/multi-chapter-runs/{}/resume".format(
                    project["id"], parent["id"]
                ),
                json={"note": "已人工确认可重试"},
            )
            assert response.status_code == 202
            finished = wait_multi(
                client, project["id"], parent["id"], {"completed", "paused", "failed"}
            )
            assert finished["status"] == "completed"
            assert client.get("/api/chapters/{}".format(chapters[0]["id"])).json()["content"] != ORIGINAL
    finally:
        server.shutdown()
        server.server_close()


def test_resuming_child_run_also_resumes_its_paused_parent_pipeline():
    server = serve("blocker")
    try:
        with TestClient(app) as client:
            project, _novel, chapters, provider = create_case(
                client, server.server_port, "child-resumes-parent", chapter_count=1
            )
            parent = create_multi(client, project, chapters[0], provider, count=1)
            paused = wait_multi(
                client, project["id"], parent["id"], {"paused", "failed"}
            )
            assert paused["status"] == "paused"
            child_id = paused["current_loop_run_id"]

            server.mode = "pass"
            response = client.post(
                "/api/projects/{}/runs/{}/resume".format(
                    project["id"], child_id
                ),
                json={"note": "从章节详情恢复并继续生产线"},
            )
            assert response.status_code == 202, response.text

            finished = wait_multi(
                client,
                project["id"],
                parent["id"],
                {"completed", "paused", "failed"},
            )
            assert finished["status"] == "completed"
            assert finished["current_index"] == 1
    finally:
        server.shutdown()
        server.server_close()


def test_restore_version_backs_up_current_content_and_writes_audit():
    server = serve()
    try:
        with TestClient(app) as client:
            project, _novel, chapters, provider = create_case(
                client, server.server_port, "restore", chapter_count=1
            )
            parent = create_multi(client, project, chapters[0], provider, count=1)
            finished = wait_multi(client, project["id"], parent["id"], {"completed", "failed"})
            assert finished["status"] == "completed"
            child_id = json.loads(finished["loop_run_ids_json"])[0]
            child = client.get(
                "/api/projects/{}/runs/{}".format(project["id"], child_id)
            ).json()
            original_backup = next(
                version for version in child["versions"]
                if version["kind"] == "pre_auto_commit_backup"
            )
            response = client.post(
                "/api/projects/{}/chapters/{}/versions/{}/restore".format(
                    project["id"], chapters[0]["id"], original_backup["id"]
                ),
                json={"note": "恢复自动写入前正文"},
            )
            assert response.status_code == 200
            restored = client.get("/api/chapters/{}".format(chapters[0]["id"])).json()
            assert restored["content"] == ORIGINAL
            versions = client.get(
                "/api/chapters/{}/versions".format(chapters[0]["id"])
            ).json()
            assert any(version["kind"] == "pre_restore_backup" for version in versions)
            detail = client.get(
                "/api/projects/{}/runs/{}".format(project["id"], child_id)
            ).json()
            assert detail["steps"][-1]["state"] == "VERSION_RESTORED"
    finally:
        server.shutdown()
        server.server_close()


def test_only_one_active_multi_chapter_run_per_novel():
    server = serve()
    try:
        with TestClient(app) as client:
            project, _novel, chapters, provider = create_case(
                client, server.server_port, "unique", chapter_count=3
            )
            first = create_multi(
                client, project, chapters[0], provider, mode="manual_review", count=1
            )
            wait_multi(client, project["id"], first["id"], {"waiting_human", "failed"})
            duplicate = client.post(
                "/api/projects/{}/multi-chapter-runs".format(project["id"]),
                json={
                    "provider_id": provider["id"],
                    "start_chapter_id": chapters[1]["id"],
                    "chapter_count": 1,
                    "mode": "manual_review",
                },
            )
            assert duplicate.status_code == 409
    finally:
        server.shutdown()
        server.server_close()


def test_waiting_multi_run_can_be_stopped_without_changing_chapter_content():
    server = serve()
    try:
        with TestClient(app) as client:
            project, _novel, chapters, provider = create_case(
                client, server.server_port, "stop", chapter_count=1
            )
            parent = create_multi(
                client, project, chapters[0], provider, mode="manual_review", count=1
            )
            waiting = wait_multi(
                client, project["id"], parent["id"], {"waiting_human", "failed"}
            )
            assert waiting["status"] == "waiting_human"
            response = client.post(
                "/api/projects/{}/multi-chapter-runs/{}/stop".format(
                    project["id"], parent["id"]
                ),
                json={"note": "用户终止"},
            )
            assert response.status_code == 202
            assert response.json()["status"] == "stopped"
            assert client.get(
                "/api/chapters/{}".format(chapters[0]["id"])
            ).json()["content"] == ORIGINAL
    finally:
        server.shutdown()
        server.server_close()


def test_positive_integer_count_creates_missing_chapters_and_plans():
    server = serve()
    try:
        with TestClient(app) as client:
            project, novel, chapters, provider = create_case(
                client, server.server_port, "integer-count", chapter_count=1
            )
            response = client.post(
                "/api/projects/{}/multi-chapter-runs".format(project["id"]),
                json={
                    "provider_id": provider["id"],
                    "start_chapter_id": chapters[0]["id"],
                    "chapter_count": 4,
                    "mode": "ai_auto_commit",
                    "context_budget": 1600,
                },
            )
            assert response.status_code == 202, response.text
            finished = wait_multi(
                client,
                project["id"],
                response.json()["id"],
                {"completed", "paused", "failed"},
            )
            assert finished["status"] == "completed"
            all_chapters = client.get(
                "/api/novels/{}/chapters".format(novel["id"])
            ).json()
            assert len(all_chapters) == 4
            assert [chapter["order_index"] for chapter in all_chapters] == [1, 2, 3, 4]
            assert all(chapter["outline"]["goal"] for chapter in all_chapters)
            assert all(chapter["content"] for chapter in all_chapters)
    finally:
        server.shutdown()
        server.server_close()


def test_unreachable_selected_provider_falls_back_to_reachable_local_provider():
    server = serve()
    try:
        with TestClient(app) as client:
            project, _novel, chapters, reachable = create_case(
                client, server.server_port, "provider-fallback", chapter_count=1
            )
            unavailable = client.post(
                "/api/model-providers",
                json={
                    "name": "Offline custom provider",
                    "provider_type": "openai_compatible",
                    "base_url": "http://127.0.0.1:9/v1",
                    "model": "offline",
                    "timeout_seconds": 5,
                },
            ).json()
            parent = create_multi(
                client,
                project,
                chapters[0],
                unavailable,
                mode="ai_auto_commit",
                count=1,
            )
            finished = wait_multi(
                client,
                project["id"],
                parent["id"],
                {"completed", "paused", "failed"},
            )
            assert finished["status"] == "completed"
            assert finished["provider_id"] == reachable["id"]
            policy = json.loads(finished["policy_json"])
            assert policy["requested_provider_id"] == unavailable["id"]
            assert policy["resolved_provider_id"] == reachable["id"]
            assert any(
                "fallback provider selected" in item
                for item in policy["provider_attempts"]
            )
    finally:
        server.shutdown()
        server.server_close()
