from app.services.context_builder import estimate_tokens
from app.services.novel_chunker import chunk_text


def test_empty_returns_no_chunks():
    assert chunk_text("") == []
    assert chunk_text("   ") == []


def test_short_text_single_chunk():
    assert chunk_text("一段很短的正文。", max_tokens=2000) == ["一段很短的正文。"]


def test_long_text_splits_by_chapter():
    text = (
        "第一章\n" + "甲" * 1500
        + "\n\n第二章\n" + "乙" * 1500
        + "\n\n第三章\n" + "丙" * 1500
    )
    chunks = chunk_text(text, max_tokens=1000, overlap=80)
    assert len(chunks) >= 3
    # 每块不超过 max_tokens + overlap 容差
    assert all(estimate_tokens(c) <= 1000 + 200 for c in chunks)
    # 内容覆盖：三章的字都还在
    joined = "".join(chunks)
    assert "甲" in joined and "乙" in joined and "丙" in joined


def test_long_unit_without_chapter_marker_hard_splits():
    text = "丁" * 5000  # 无章节标记、无空行的超长单段
    chunks = chunk_text(text, max_tokens=1000)
    assert len(chunks) >= 5
    assert all(estimate_tokens(c) <= 1000 + 200 for c in chunks)
