"""灌木管理接口：维护灌木，覆盖安排修剪、防治处理、补植登记等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.shrub import DISPLAY_STATUSES, ShrubService

router = APIRouter(prefix="/api/shrub", tags=["灌木管理"])

service = ShrubService()

LIST_FIELDS = ["灌木编号", "品种名称", "栽植面积", "修剪周期", "高度范围", "花开季节", "管护人员", "灌木状态"]
STATUSES = DISPLAY_STATUSES


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按灌木编号检索"),
    status: str | None = Query(default=None, description="正常、待修剪、病虫害、待补植、补植中、已补植"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按灌木编号与状态过滤灌木管理列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


# 注意：/export、/stats 这类固定路径必须声明在 /{entry_id} 之前，
# 否则会被当成 entry_id 匹配，导致导出/看板接口取错处理函数。
@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出灌木管理清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "shrub", "total": total, "items": items}


@router.get("/stats")
def shrub_stats() -> dict[str, Any]:
    """养护看板：灌木面积等指标每次都按补植明细现场重算。"""
    return service.stats()


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条灌木明细；不存在时给出可读的错误说明。

    与列表共用同一份服务层输出，保证花开季节、栽植面积等字段两入口完全一致。
    """
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"灌木 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条灌木，缺字段、面积非法或编号重复时说明原因而不是静默丢弃。"""
    entry, message = service.create_entry(payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条灌木执行安排修剪、防治处理、补植登记。

    每条作业线只能按 待处理 → 处理中 → 已完成 依次推进；跳级、重复提交或
    补植明细不合法都会返回 ok=false 与具体原因，状态不变，前端可据此重试。
    """
    values = dict(payload.values or {})
    action = str(values.pop("action", "") or "").strip()
    entry, message = service.run_action(entry_id, action, values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
