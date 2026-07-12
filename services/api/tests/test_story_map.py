import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models.auto_entities import StoryMemoryRecord
from app.models.entities import (
    Character,
    CreativeRun,
    Foreshadowing,
    PlotThread,
    TimelineEvent,
)


# ───────────────────────── 工具：造项目/小说/章节/人物 ─────────────────────────


def _project_novel(client, title="故事地图测试"):
    project = client.post("/api/projects", json={"name": title}).json()
    novel = client.post(
        "/api/novels", json={"project_id": project["id"], "title": title + "·小说"}
    ).json()
    return project, novel


def _chapter(client, novel_id, order_index, title, content="正文占位", status="committed"):
    ch = client.post(
        "/api/chapters",
        json={
            "novel_id": novel_id,
            "order_index": order_index,
            "title": title,
            "content": content,
            "outline": {"goal": "g", "outline_content": "o"},
        },
    ).json()
    if status != "outlined":
        client.patch("/api/chapters/{}".format(ch["id"]), json={"status": status})
    return ch


# ───────────────────────── T1：migration 后新列可写可读 ─────────────────────────


def test_timeline_event_story_order_roundtrip():
    with TestClient(app) as client:
        _project, novel = _project_novel(client, "story_order 往返")
        created = client.post(
            "/api/timeline-events",
            json={
                "novel_id": novel["id"],
                "title": "开端",
                "story_time": "十年前的雨夜",
                "story_order": 3,
                "character_ids": [],
            },
        )
        assert created.status_code == 201, created.text
        assert created.json()["story_order"] == 3
        # 读回
        got = client.get("/api/novels/{}/timeline-events".format(novel["id"])).json()
        assert got[0]["story_order"] == 3
        # story_order 可空：不传也能建
        created2 = client.post(
            "/api/timeline-events", json={"novel_id": novel["id"], "title": "无序号事件"}
        )
        assert created2.status_code == 201
        assert created2.json()["story_order"] is None


# ───────────────────────── T2：CRUD + 404 ─────────────────────────


def test_crud_and_404():
    with TestClient(app) as client:
        _project, novel = _project_novel(client, "CRUD")
        nid = novel["id"]
        # timeline-events
        ev = client.post("/api/timeline-events", json={"novel_id": nid, "title": "事件A"}).json()
        patched = client.patch("/api/timeline-events/{}".format(ev["id"]), json={"title": "事件A改", "character_ids": ["x"]})
        assert patched.status_code == 200 and patched.json()["title"] == "事件A改"
        assert client.delete("/api/timeline-events/{}".format(ev["id"])).status_code == 204
        assert client.patch("/api/timeline-events/missing", json={"title": "x"}).status_code == 404
        # plot-threads
        th = client.post("/api/plot-threads", json={"novel_id": nid, "name": "主线", "related_chapter_ids": []}).json()
        assert client.patch("/api/plot-threads/{}".format(th["id"]), json={"status": "resolved"}).json()["status"] == "resolved"
        assert client.delete("/api/plot-threads/{}".format(th["id"])).status_code == 204
        assert client.delete("/api/plot-threads/missing").status_code == 404
        # foreshadowing
        fo = client.post("/api/foreshadowing", json={"novel_id": nid, "description": "神秘钥匙"}).json()
        assert client.patch("/api/foreshadowing/{}".format(fo["id"]), json={"notes": "第5章回收"}).json()["notes"] == "第5章回收"
        assert client.delete("/api/foreshadowing/{}".format(fo["id"])).status_code == 204
        # 建在不存在的小说上 → 404
        assert client.post("/api/timeline-events", json={"novel_id": "nope", "title": "x"}).status_code == 404


# ───────────────────────── T3：聚合接口（归一化/presence/overdue/空小说） ─────────────────────────


def test_story_map_aggregation():
    with TestClient(app) as client:
        _project, novel = _project_novel(client, "聚合")
        nid = novel["id"]
        # 3 章
        c1 = _chapter(client, nid, 1, "第一章", content="甲" * 120)
        c2 = _chapter(client, nid, 2, "第二章", content="乙" * 80)
        c3 = _chapter(client, nid, 3, "第三章", content="丙" * 200)

        # 2 人物：一个 relationships_json 用字符串值，一个用对象值
        zhou = client.post(
            "/api/characters",
            json={
                "novel_id": nid,
                "name": "周明",
                "role": "主角",
                "arc": "从逃避到直面",
                "relationships": {"林秋": "同事", "苏婷": {"type": "romance", "description": "暗生情愫"}, "查无此人": "神秘对手"},
            },
        ).json()
        linqiu = client.post("/api/characters", json={"novel_id": nid, "name": "林秋", "role": "配角"}).json()
        # 苏婷建成人物 → 对象值关系应归一化成 romance 边（匹配到）；查无此人不建 → unmatched
        client.post("/api/characters", json={"novel_id": nid, "name": "苏婷", "role": "配角"})

        # 事件：周明出现在 c1、c2；林秋在 c3
        client.post("/api/timeline-events", json={"novel_id": nid, "title": "E1", "chapter_id": c1["id"], "character_ids": [zhou["id"]]})
        client.post("/api/timeline-events", json={"novel_id": nid, "title": "E2", "chapter_id": c2["id"], "character_ids": [zhou["id"]]})
        client.post("/api/timeline-events", json={"novel_id": nid, "title": "E3", "chapter_id": c3["id"], "character_ids": [linqiu["id"]]})

        # 情节线
        client.post("/api/plot-threads", json={"novel_id": nid, "name": "记忆线", "related_chapter_ids": [c1["id"], c3["id"]]})
        # 伏笔：埋在 c1（距最新已提交章 c3 = 2 章，未超期）
        client.post("/api/foreshadowing", json={"novel_id": nid, "description": "旧照片", "planted_chapter_id": c1["id"]})

        sm = client.get("/api/novels/{}/story-map".format(nid)).json()

        # chapters：word_count / summary 截断
        assert len(sm["chapters"]) == 3
        assert sm["chapters"][0]["word_count"] == 120
        # characters：presence 聚合去重升序
        by_name = {c["name"]: c for c in sm["characters"]}
        assert by_name["周明"]["presence_chapters"] == [1, 2]
        assert by_name["林秋"]["presence_chapters"] == [3]
        # relationships 归一化：字符串→other、对象→romance；匹配不到的进 unmatched
        rels = {(r["source_id"], r["type"]) for r in sm["relationships"]}
        assert (zhou["id"], "other") in rels  # 林秋（字符串）
        assert (zhou["id"], "romance") in rels  # 苏婷（对象值）→ romance 边
        unmatched_names = {u["target_name"] for u in sm["unmatched"]}
        assert "查无此人" in unmatched_names  # 未建成人物 → unmatched
        assert "苏婷" not in unmatched_names  # 已建成人物 → 进 edges 而非 unmatched
        # timeline_events：character_ids 已解析为数组
        assert all(isinstance(e["character_ids"], list) for e in sm["timeline_events"])
        # plot_threads related_chapter_ids 已解析
        assert sm["plot_threads"][0]["related_chapter_ids"] == [c1["id"], c3["id"]]
        # foreshadow_counts：1 open, 0 resolved, 0 overdue（gap=2 未超 20）
        assert sm["stats"]["foreshadow_counts"] == {"open": 1, "resolved": 0, "overdue": 0}


def test_story_map_overdue_foreshadowing():
    with TestClient(app) as client:
        _project, novel = _project_novel(client, "超期伏笔")
        nid = novel["id"]
        c1 = _chapter(client, nid, 1, "第一章")
        # 造到第 25 章（committed），使 c1 埋设的伏笔 gap=24 > 20 → overdue
        for i in range(2, 26):
            _chapter(client, nid, i, "第{}章".format(i))
        client.post("/api/foreshadowing", json={"novel_id": nid, "description": "远期伏笔", "planted_chapter_id": c1["id"]})
        sm = client.get("/api/novels/{}/story-map".format(nid)).json()
        assert sm["stats"]["foreshadow_counts"]["overdue"] == 1


def test_story_map_empty_novel_returns_200():
    with TestClient(app) as client:
        _project, novel = _project_novel(client, "空小说")
        sm = client.get("/api/novels/{}/story-map".format(novel["id"]))
        assert sm.status_code == 200
        body = sm.json()
        for key in ("chapters", "characters", "timeline_events", "plot_threads", "foreshadowing", "relationships", "unmatched"):
            assert body[key] == []
        assert body["stats"]["foreshadow_counts"] == {"open": 0, "resolved": 0, "overdue": 0}
    # 不存在的小说 → 404
    with TestClient(app) as client:
        assert client.get("/api/novels/nope/story-map").status_code == 404


# ───────────────────────── T4：提取 service（假 adapter） ─────────────────────────


class _ExtractMockHandler(BaseHTTPRequestHandler):
    """按 prompt 决定返回合法或非法 JSON。"""

    mode = "valid"  # valid | invalid

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(length)
        if _ExtractMockHandler.mode == "invalid":
            content = "这不是 JSON，只是一段自然语言，故意让 JsonGuard 失败。"
        else:
            content = json.dumps(
                {
                    "events": [
                        {"title": "地下室的七分钟", "story_time": "午夜", "story_order": 1,
                         "description": "主角走进灯塔地下室", "character_names": ["周明", "陌生人"],
                         "confidence": 0.9, "evidence": "他推开门"}
                    ],
                    "relationships": [
                        {"source_name": "周明", "target_name": "林秋", "type": "ally",
                         "description": "并肩调查", "confidence": 0.8, "evidence": "两人对视"}
                    ],
                    "threads": [
                        {"name": "灯塔谜团", "description": "围绕地下室的谜", "status": "open",
                         "confidence": 0.85, "evidence": "门锁死了"}
                    ],
                    "foreshadowing": [
                        {"description": "墙上的裂缝", "action": "planted",
                         "confidence": 0.7, "evidence": "裂缝渗水"}
                    ],
                },
                ensure_ascii=False,
            )
        body = json.dumps(
            {"choices": [{"message": {"role": "assistant", "content": content}}],
             "usage": {"prompt_tokens": 30, "completion_tokens": 40}}
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _f, *_a):
        return


def _start_extract_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ExtractMockHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _mock_provider(client, port, name="Extract Mock"):
    return client.post(
        "/api/model-providers",
        json={
            "name": name,
            "provider_type": "openai_compatible",
            "base_url": "http://127.0.0.1:{}/v1".format(port),
            "model": "extract-mock",
            "timeout_seconds": 5,
        },
    ).json()


def _wait_run(client, novel_id, run_id, timeout=25):
    deadline = time.time() + timeout
    while time.time() < deadline:
        run = client.get("/api/novels/{}/story-map/extract-runs/{}".format(novel_id, run_id)).json()
        if run["status"] in {"completed", "failed"}:
            return run
        time.sleep(0.05)
    raise AssertionError("提取任务未在期限内完成")


def test_extract_valid_json_stages_candidates():
    _ExtractMockHandler.mode = "valid"
    server = _start_extract_server()
    try:
        with TestClient(app) as client:
            _project, novel = _project_novel(client, "提取-合法")
            nid = novel["id"]
            _chapter(client, nid, 1, "灯塔章", content="他推开门，走进地下室。" * 20)
            provider = _mock_provider(client, server.server_address[1])

            started = client.post(
                "/api/novels/{}/story-map/extract".format(nid),
                json={"provider_id": provider["id"]},
            )
            assert started.status_code == 202, started.text
            run = _wait_run(client, nid, started.json()["id"])
            assert run["status"] == "completed", run
            assert run["total_chapters"] == 1
            assert run["candidate_count"] == 4  # event/rel/thread/foreshadow 各一

            candidates = client.get("/api/novels/{}/story-engineering/candidates".format(nid)).json()
            by_type = {}
            for c in candidates:
                by_type.setdefault(c["record_type"], []).append(c)
            assert len(by_type.get("staged_storymap_event", [])) == 1
            assert len(by_type.get("staged_storymap_relationship", [])) == 1
            assert len(by_type.get("staged_storymap_thread", [])) == 1
            assert len(by_type.get("staged_storymap_foreshadow", [])) == 1

            # 审计：CreativeRun 有 storymap_extract 记录
            with SessionLocal() as db:
                assert db.query(CreativeRun).filter(
                    CreativeRun.operation == "storymap_extract", CreativeRun.status == "completed"
                ).count() >= 1
    finally:
        server.shutdown()
        server.server_close()


def test_extract_invalid_json_marks_partial_failure():
    _ExtractMockHandler.mode = "invalid"
    server = _start_extract_server()
    try:
        with TestClient(app) as client:
            _project, novel = _project_novel(client, "提取-非法")
            nid = novel["id"]
            _chapter(client, nid, 1, "坏JSON章", content="正文" * 30)
            provider = _mock_provider(client, server.server_address[1])
            started = client.post(
                "/api/novels/{}/story-map/extract".format(nid),
                json={"provider_id": provider["id"]},
            )
            run = _wait_run(client, nid, started.json()["id"])
            # 单章失败：run 本身 completed 但 error_code=PARTIAL，无候选落库
            assert run["status"] == "completed", run
            assert run["error_code"] == "PARTIAL"
            assert run["candidate_count"] == 0
            # 失败的 CreativeRun 有记录（不静默吞）
            with SessionLocal() as db:
                assert db.query(CreativeRun).filter(
                    CreativeRun.operation == "storymap_extract", CreativeRun.status == "failed"
                ).count() >= 1
    finally:
        server.shutdown()
        server.server_close()


# ───────────────────────── T4.4：accept 各新 record_type ─────────────────────────


def _stage(db, project_id, novel_id, chapter_id, record_type, payload):
    from app.services.common import dumps as _dumps

    rec = StoryMemoryRecord(
        project_id=project_id,
        novel_id=novel_id,
        chapter_id=chapter_id,
        source_id="test-run",
        record_type=record_type,
        status="staged",
        content_json=_dumps(payload),
        metadata_json=_dumps({"chapter_id": chapter_id}),
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec.id


def test_accept_storymap_event_resolves_character_names():
    with TestClient(app) as client:
        project, novel = _project_novel(client, "接受-事件")
        nid = novel["id"]
        c1 = _chapter(client, nid, 1, "章一")
        zhou = client.post("/api/characters", json={"novel_id": nid, "name": "周明"}).json()
        with SessionLocal() as db:
            cid = _stage(db, project["id"], nid, c1["id"], "staged_storymap_event", {
                "title": "对峙", "story_time": "黄昏", "story_order": 2,
                "description": "正面冲突", "character_names": ["周明", "无名氏"],
            })
        resp = client.post("/api/story-engineering/candidates/{}/accept".format(cid))
        assert resp.status_code == 200, resp.text
        with SessionLocal() as db:
            ev = db.query(TimelineEvent).filter(TimelineEvent.novel_id == nid).one()
            assert ev.chapter_id == c1["id"]
            assert ev.story_order == 2
            # 周明匹配到 id 写入 character_ids_json；无名氏保留在描述尾部
            assert zhou["id"] in json.loads(ev.character_ids_json)
            assert "无名氏" in ev.description


def test_accept_storymap_relationship_and_thread_merge():
    with TestClient(app) as client:
        project, novel = _project_novel(client, "接受-关系与线")
        nid = novel["id"]
        c1 = _chapter(client, nid, 1, "章一")
        c2 = _chapter(client, nid, 2, "章二")
        client.post("/api/characters", json={"novel_id": nid, "name": "周明"})
        client.post("/api/characters", json={"novel_id": nid, "name": "林秋"})
        # 关系
        with SessionLocal() as db:
            rid = _stage(db, project["id"], nid, c1["id"], "staged_storymap_relationship", {
                "source_name": "周明", "target_name": "林秋", "type": "ally", "description": "并肩",
            })
        assert client.post("/api/story-engineering/candidates/{}/accept".format(rid)).status_code == 200
        with SessionLocal() as db:
            zhou = db.query(Character).filter(Character.novel_id == nid, Character.name == "周明").one()
            rel = json.loads(zhou.relationships_json)
            assert rel["林秋"]["type"] == "ally"

        # thread：先建一条同名线（锚 c1），再接受同名线候选（锚 c2）→ 合并追加 c2
        client.post("/api/plot-threads", json={"novel_id": nid, "name": "灯塔谜团", "related_chapter_ids": [c1["id"]]})
        with SessionLocal() as db:
            tid = _stage(db, project["id"], nid, c2["id"], "staged_storymap_thread", {
                "name": "灯塔谜团", "description": "推进", "status": "open",
            })
        assert client.post("/api/story-engineering/candidates/{}/accept".format(tid)).status_code == 200
        with SessionLocal() as db:
            th = db.query(PlotThread).filter(PlotThread.novel_id == nid, PlotThread.name == "灯塔谜团").one()
            related = json.loads(th.related_chapter_ids_json)
            assert c1["id"] in related and c2["id"] in related  # 合并、去重、追加


def test_accept_storymap_foreshadow_plant_and_resolve():
    with TestClient(app) as client:
        project, novel = _project_novel(client, "接受-伏笔")
        nid = novel["id"]
        c1 = _chapter(client, nid, 1, "章一")
        c5 = _chapter(client, nid, 5, "章五")
        # planted
        with SessionLocal() as db:
            pid = _stage(db, project["id"], nid, c1["id"], "staged_storymap_foreshadow", {
                "description": "墙上的裂缝", "action": "planted",
            })
        assert client.post("/api/story-engineering/candidates/{}/accept".format(pid)).status_code == 200
        # resolved：description 包含匹配到已有伏笔 → 置回收
        with SessionLocal() as db:
            rid = _stage(db, project["id"], nid, c5["id"], "staged_storymap_foreshadow", {
                "description": "墙上的裂缝最终渗透", "action": "resolved",
            })
        assert client.post("/api/story-engineering/candidates/{}/accept".format(rid)).status_code == 200
        with SessionLocal() as db:
            rows = db.query(Foreshadowing).filter(Foreshadowing.novel_id == nid).all()
            assert len(rows) == 1  # 未新建，命中已有
            assert rows[0].status == "resolved"
            assert rows[0].resolved_chapter_id == c5["id"]
