from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ActivityItem(BaseModel):
    """统一活动记录项：聚合 章节 Loop / 多章生产线 / 拆解任务 / 创作中心调用。"""

    kind: str  # loop | multi_chapter | deconstruction | creative
    id: str
    project_id: Optional[str] = None
    novel_id: Optional[str] = None
    chapter_id: Optional[str] = None
    title: str
    subtitle: str = ""
    status: str
    state: str = ""
    error_code: str = ""
    created_at: datetime
    updated_at: datetime
