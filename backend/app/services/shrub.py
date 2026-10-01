"""灌木管理业务规则：修剪、防治、补植三条工作流的状态推进、字段校验与筛选口径。

设计要点：
- 修剪 / 防治 / 补植各是一条独立工作流，阶段只能「待处理 → 处理中 → 已完成」依次推进，
  首次点击对应动作为该灌木发起工作流（进入待处理），任何跳级提交都会被拦下并说明原因；
- 对外展示的「灌木状态」由三条工作流实时派生，清单页和详情页共用同一个序列化出口，
  保证同一片灌木两边看到的字段（如花开季节、状态）完全一致；
- 补植完成时生成补植明细，同一灌木编号重复完成只计一次；栽植面积 = 原始栽植面积
  + 各次有效补植面积，看板与统计实时按明细重算；
- 已完成补植的灌木不再接受修剪安排。
"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "shrub"
REPLANT_MODULE = "shrub_replant"
REQUIRED_FIELDS = ["灌木编号", "品种名称", "栽植面积"]
OPTIONAL_FIELDS = ["修剪周期", "高度范围", "花开季节", "管护人员"]

# 每条工作流的阶段顺序：下标 0 表示尚未发起，之后只能逐级推进，不允许跳级。
STAGE_NOT_STARTED = "未发起"
STAGE_TODO = "待处理"
STAGE_DOING = "处理中"
STAGE_DONE = "已完成"
STAGES = [STAGE_NOT_STARTED, STAGE_TODO, STAGE_DOING, STAGE_DONE]

WORKFLOW_FIELDS = {"安排修剪": "修剪", "防治处理": "防治", "补植登记": "补植"}
WORKFLOW_KEYS = {"修剪": "prune", "防治": "pest", "补植": "replant"}
NEXT_STAGE = {STAGE_NOT_STARTED: STAGE_TODO, STAGE_TODO: STAGE_DOING, STAGE_DOING: STAGE_DONE}

# 对外展示状态（与原清单、筛选项保持一致）
DISPLAY_NORMAL = "正常"
DISPLAY_PRUNE = "待修剪"
DISPLAY_PEST = "病虫害"
DISPLAY_REPLANT = "已补植"

# 老数据里的历史状态 -> (修剪阶段, 防治阶段, 补植阶段)
LEGACY_STAGES = {
    DISPLAY_NORMAL: (STAGE_DONE, STAGE_NOT_STARTED, STAGE_NOT_STARTED),
    DISPLAY_PRUNE: (STAGE_TODO, STAGE_NOT_STARTED, STAGE_NOT_STARTED),
    DISPLAY_PEST: (STAGE_DONE, STAGE_TODO, STAGE_NOT_STARTED),
    DISPLAY_REPLANT: (STAGE_DONE, STAGE_NOT_STARTED, STAGE_DONE),
}


def parse_area(value: Any) -> float:
    """把面积文本解析成数值；解析不了按 0 处理，保证汇总不会被脏数据带崩。"""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def format_area(value: float) -> str:
    """面积展示：整数不带小数点，其余保留两位。"""
    rounded = round(float(value), 2)
    return str(int(rounded)) if rounded == int(rounded) else f"{rounded:.2f}"


class ShrubService:
    # ---- 初始化与迁移 -------------------------------------------------

    def __init__(self) -> None:
        self._migrate()

    def _migrate(self) -> None:
        """把历史的单一 status 字段拆成三条工作流阶段，只迁一次。"""
        for row in store.rows(MODULE):
            if row.get("_workflow_ready"):
                continue
            prune_stage, pest_stage, replant_stage = LEGACY_STAGES.get(
                str(row.get("status") or ""),
                (STAGE_DONE, STAGE_NOT_STARTED, STAGE_NOT_STARTED),
            )
            row["_base_area"] = parse_area(row.get("栽植面积"))
            self._set_stages(row, prune_stage, pest_stage, replant_stage)
            row["_workflow_ready"] = True
            self._sync_row(row)
        # 历史遗留的补植明细也补一个基础面积快照
        for detail in store.rows(REPLANT_MODULE):
            detail.setdefault("补植面积", parse_area(detail.get("补植面积")))

    @staticmethod
    def _set_stages(row: dict[str, Any], prune: str, pest: str, replant: str) -> None:
        row["修剪进度"] = prune
        row["防治进度"] = pest
        row["补植进度"] = replant

    # ---- 派生状态 -----------------------------------------------------

    @staticmethod
    def _display_status(row: dict[str, Any]) -> str:
        """补植完成优先；其次看病虫害工作流是否仍在处理；再看修剪；都没事才算正常。"""
        if row.get("补植进度") == STAGE_DONE:
            return DISPLAY_REPLANT
        if row.get("防治进度") in (STAGE_TODO, STAGE_DOING):
            return DISPLAY_PEST
        if row.get("修剪进度") in (STAGE_TODO, STAGE_DOING):
            return DISPLAY_PRUNE
        return DISPLAY_NORMAL

    def _replant_details(self, shrub_id: int) -> list[dict[str, Any]]:
        return [d for d in store.rows(REPLANT_MODULE) if int(d.get("灌木ID", 0)) == shrub_id]

    def _current_area(self, row: dict[str, Any]) -> float:
        """栽植面积随补植明细重算：原始面积 + 该灌木全部有效补植面积。"""
        total = float(row.get("_base_area", 0.0))
        for detail in self._replant_details(int(row.get("id", 0))):
            total += parse_area(detail.get("补植面积"))
        return total

    def _sync_row(self, row: dict[str, Any]) -> dict[str, Any]:
        """把派生结果回写到行里，供全局看板的 pending/abnormal 统计复用。"""
        display = self._display_status(row)
        row["status"] = display
        row["灌木状态"] = display
        active = (STAGE_TODO, STAGE_DOING)
        row["pending"] = any(
            row.get(field) in active for field in ("修剪进度", "防治进度", "补植进度")
        )
        row["abnormal"] = display == DISPLAY_PEST
        return row

    def serialize(self, row: dict[str, Any], *, with_details: bool = False) -> dict[str, Any]:
        """清单页与详情页唯一的数据出口，任何字段两边都不会再出现口径差异。"""
        self._sync_row(row)
        item: dict[str, Any] = {
            "id": row.get("id"),
            "灌木编号": row.get("灌木编号"),
            "品种名称": row.get("品种名称"),
            "栽植面积": format_area(self._current_area(row)),
            "修剪周期": row.get("修剪周期"),
            "高度范围": row.get("高度范围"),
            "花开季节": row.get("花开季节"),
            "管护人员": row.get("管护人员"),
            "灌木状态": row.get("灌木状态"),
            "修剪进度": row.get("修剪进度", STAGE_NOT_STARTED),
            "防治进度": row.get("防治进度", STAGE_NOT_STARTED),
            "补植进度": row.get("补植进度", STAGE_NOT_STARTED),
        }
        if with_details:
            item["补植明细"] = [dict(d) for d in self._replant_details(int(row["id"]))]
        return item

    # ---- 查询 ---------------------------------------------------------

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("灌木编号", ""))]
        if status:
            rows = [row for row in rows if self._display_status(row) == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        page_rows = rows[start:start + size]
        return [self.serialize(row) for row in page_rows], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        row = store.find(MODULE, entry_id)
        if row is None:
            return None
        return self.serialize(row, with_details=True)

    def summary(self) -> dict[str, Any]:
        """养护看板小卡：各状态数量 + 随补植明细实时重算的面积。"""
        rows = store.rows(MODULE)
        counts = {DISPLAY_NORMAL: 0, DISPLAY_PRUNE: 0, DISPLAY_PEST: 0, DISPLAY_REPLANT: 0}
        total_area = 0.0
        for row in rows:
            counts[self._display_status(row)] += 1
            total_area += self._current_area(row)
        replant_area = sum(parse_area(d.get("补植面积")) for d in store.rows(REPLANT_MODULE))
        return {
            "counts": counts,
            "total_area": round(total_area, 2),
            "replant_area": round(replant_area, 2),
            "replant_count": len(store.rows(REPLANT_MODULE)),
        }

    # ---- 登记 ---------------------------------------------------------

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str] | str]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        code = str(values["灌木编号"]).strip()
        if any(str(row.get("灌木编号", "")).strip() == code for row in store.rows(MODULE)):
            return None, f"灌木编号 {code} 已存在，重复提交只算一次，请勿重复登记"
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry["灌木编号"] = code
        entry["品种名称"] = str(values["品种名称"]).strip()
        entry["_base_area"] = parse_area(values.get("栽植面积"))
        for field in OPTIONAL_FIELDS:
            value = values.get(field)
            if value is not None and str(value).strip():
                entry[field] = str(value).strip()
        # 新登记灌木三条工作流都还没发起，展示为「正常」。
        self._set_stages(entry, STAGE_NOT_STARTED, STAGE_NOT_STARTED, STAGE_NOT_STARTED)
        entry["_workflow_ready"] = True
        rows.append(entry)
        self._sync_row(entry)
        return entry, []

    # ---- 动作推进 -----------------------------------------------------

    def run_action(
        self, entry_id: int, action: str, values: dict[str, Any] | None = None
    ) -> tuple[dict[str, Any] | None, str]:
        values = values or {}
        row = store.find(MODULE, entry_id)
        if row is None:
            return None, f"灌木 {entry_id} 不存在或已归档"
        workflow = WORKFLOW_FIELDS.get(action)
        if workflow is None:
            return None, f"动作「{action}」不属于灌木管理可执行范围"

        # 已补植的灌木不再按待修剪处理：修剪工作流直接锁死。
        if workflow == "修剪" and row.get("补植进度") == STAGE_DONE:
            return None, "该灌木已完成补植，无需再安排修剪；如需修剪请先复核补植档案"

        stage_field = f"{workflow}进度"
        current = row.get(stage_field, STAGE_NOT_STARTED)

        # 已完成后的重复提交：补植按幂等成功处理（只计一次），其余动作说明原因便于重试。
        if current == STAGE_DONE:
            if workflow == "补植":
                return self.serialize(row, with_details=True), (
                    f"{row.get('灌木编号')} 已完成补植登记，重复提交只计一次"
                )
            return None, f"{workflow}工作流已完成，无需重复推进；如需重新处理请走复核流程"

        target = NEXT_STAGE.get(current)
        if target is None or STAGES.index(target) != STAGES.index(current) + 1:
            # 理论上走不到这里，留作防跳级的最后一道闸。
            return None, f"{workflow}阶段「{current}」无法直接推进，提交未生效，请重试"

        # 补植走到「已完成」时必须带合法的补植面积，缺了/非法都保持原状态，可直接重试。
        detail: dict[str, Any] | None = None
        if workflow == "补植" and target == STAGE_DONE:
            area = parse_area(values.get("补植面积"))
            raw = str(values.get("补植面积") or "").strip()
            if not raw or area <= 0:
                return None, "补植完成需登记大于 0 的「补植面积」（平方米），本次提交未生效，可修改后重试"
            detail = {
                "灌木ID": int(row["id"]),
                "灌木编号": row.get("灌木编号"),
                "品种名称": row.get("品种名称"),
                "补植面积": area,
                "补植说明": str(values.get("补植说明") or "").strip(),
            }

        row[stage_field] = target
        if detail is not None:
            # 同一灌木只保留一条补植明细：重复完成不新增，面积以首次登记为准。
            existing = self._replant_details(int(row["id"]))
            if existing:
                existing[0].update({k: v for k, v in detail.items() if v})
            else:
                detail["id"] = max(
                    (int(d.get("id", 0)) for d in store.rows(REPLANT_MODULE)), default=0
                ) + 1
                store.rows(REPLANT_MODULE).append(detail)

        self._sync_row(row)
        message = f"{row.get('灌木编号')} {workflow}已推进至「{target}」"
        if workflow == "补植" and target == STAGE_DONE:
            message += f"，栽植面积已更新为 {format_area(self._current_area(row))} 平方米"
        return self.serialize(row, with_details=True), message


# 模块加载即向养护看板注册面积指标，刷新看板时按补植明细实时重算。
_service = ShrubService()
store.register_metric(
    "灌木栽植总面积（含补植）",
    lambda: {"value": round(_service.summary()["total_area"], 2), "unit": "平方米",
             "hint": "按各灌木原始栽植面积与补植明细实时重算"},
)
store.register_metric(
    "补植累计面积",
    lambda: {"value": round(_service.summary()["replant_area"], 2), "unit": "平方米",
             "hint": f"已登记补植 {_service.summary()['replant_count']} 次"},
)
