"""提示词全量纳管：所有提示词都注册进 DB（可在提示词页编辑），运行时 DB 优先、文件兜底。"""
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models.entities import PromptTemplate
from app.services.prompt_store import PROMPT_REGISTRY, load_prompt


def test_all_prompts_seeded_and_listed():
    with TestClient(app) as client:
        rows = client.get("/api/prompt-templates").json()
        keys = {r["key"] for r in rows}
        # 注册表里的每个 key（旧版 / Loop / 拆解 / 故事工程）都应出现在提示词页
        for key in PROMPT_REGISTRY:
            assert key in keys, "提示词页缺少 {}".format(key)
        # 关键的新设计提示词也在
        for key in ("decon_critique", "decon_refine", "se_pastiche", "loop_draft_writer"):
            assert key in keys


def test_load_prompt_db_overrides_file():
    with TestClient(app) as client:
        rows = client.get("/api/prompt-templates").json()
        target = next(r for r in rows if r["key"] == "decon_critique")
        # 改写模板正文
        resp = client.patch(
            "/api/prompt-templates/{}".format(target["id"]),
            json={"template_text": "AGENT: decon_critique\n这是被页面改写过的提示词 SENTINEL_XYZ"},
        )
        assert resp.status_code == 200, resp.text
        # 运行时 load_prompt 应拿到 DB 里改写后的文本（而非文件原文）
        with SessionLocal() as db:
            text = load_prompt(db, "decon_critique")
            assert "SENTINEL_XYZ" in text


def test_load_prompt_file_fallback_when_no_db_row():
    # 没有 DB 行时回退到文件（这里用一个真实 key，但先删掉它的 DB 行模拟未种入场景）
    with TestClient(app):
        with SessionLocal() as db:
            row = db.query(PromptTemplate).filter(PromptTemplate.key == "se_framework").first()
            if row is not None:
                db.delete(row)
                db.commit()
            text = load_prompt(db, "se_framework")
            assert text.strip()  # 从文件读到了非空内容
