"""灌木管理接口：维护灌木，覆盖安排修剪、防治处理、补植登记等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.shrub import ShrubService

router = APIRouter(prefix="/api/shrub", tags=["灌木管理"])

service = ShrubService()

LIST_FIELDS = ["灌木编号", "品种名称", "栽植面积", "修剪周期", "高度范围", "花开季节", "管护人员", "灌木状态"]
STATUSES = ["正常", "待修剪", "病虫害", "已补植"]


@router.get("/summary")
def summary() -> dict[str, Any]:
    """灌木养护看板：各状态数量与随补植明细实时重算的栽植面积。"""
    return service.summary()


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按灌木编号检索"),
    status: str | None = Query(default=None, description="正常、待修剪、病虫害、已补植"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按灌木编号与状态过滤灌木管理列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出灌木管理清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "shrub", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条灌木明细（含补植明细）；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"灌木 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条灌木：缺字段或灌木编号重复时说明原因而不是静默丢弃。"""
    entry, problem = service.create_entry(payload.values)
    if entry is None:
        if isinstance(problem, list):
            return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(problem)}")
        return ActionResult(ok=False, message=str(problem))
    return ActionResult(ok=True, message="灌木已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """推进修剪/防治/补植工作流；只能按 待处理→处理中→已完成 依次推进。

    跳级、重复完成、已补植再修剪等非法提交一律返回 ok=False 并说明原因，
    前端据此提示并允许重试；本次提交不会改变任何状态。
    """
    action = str(payload.values.get("action") or "").strip()
    if not action:
        return ActionResult(ok=False, message="未指定要执行的动作（安排修剪/防治处理/补植登记），提交未生效，可重试")
    entry, message = service.run_action(entry_id, action, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
