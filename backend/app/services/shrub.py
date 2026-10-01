"""灌木管理业务规则：修剪、防治、补植三条作业线的状态流转都收在这里。

设计要点：
- 修剪 / 防治 / 补植各自独立，只能沿 待处理 → 处理中 → 已完成 依次推进，
  服务端按当前阶段的下标判断，任何跳级提交都会被拦下并说明原因。
- 补植登记会落一条补植明细；灌木的有效栽植面积 = 原始栽植面积 + 补植明细合计，
  每次读列表 / 详情 / 看板时都按明细重算，不另存一份会过期的汇总。
- 同一灌木编号只允许一条补植明细：处理中再次提交只更新同一条明细，
  已完成后再提交直接拒绝，因此重复提交不会重复计面积。
- 清单页与详情页都经过 _present 输出同一份权威字段，避免两入口口径不一致。
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import store

MODULE = "shrub"
REQUIRED_FIELDS = ["灌木编号", "品种名称", "栽植面积"]
BUSINESS_FIELDS = ["灌木编号", "品种名称", "栽植面积", "修剪周期", "高度范围", "花开季节", "管护人员"]

# 每条作业线统一的三段式生命周期
STAGES = ["待处理", "处理中", "已完成"]
# 动作名 → 作业线；动作名保持页面上的叫法不变
WORKFLOWS = {"安排修剪": "修剪", "防治处理": "防治", "补植登记": "补植"}
# 作业线 → 条目里记录当前阶段的字段
STAGE_FIELDS = {"修剪": "修剪状态", "防治": "防治状态", "补植": "补植状态"}

# 清单 / 看板上对外可见的灌木综合状态
DISPLAY_STATUSES = ["正常", "待修剪", "病虫害", "待补植", "补植中", "已补植"]


def _to_float(value: Any) -> float | None:
    """把面积入参解析成非负浮点数；解析不出来时返回 None，由调用方说明原因。"""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        text = str(value).strip().replace(",", "")
        # 允许录入时带单位，例如 "45.5 ㎡"
        for suffix in ("㎡", "平方米", "m2", "m²"):
            if text.endswith(suffix):
                text = text[: -len(suffix)].strip()
                break
        try:
            number = float(text)
        except ValueError:
            return None
    return number if number >= 0 else None


def _fmt_area(number: float) -> str:
    """面积统一展示口径：整数不带小数，非整数保留两位。"""
    text = f"{number:.2f}".rstrip("0").rstrip(".")
    return f"{text} ㎡"


class ShrubService:
    # ---------- 读取 ----------
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = [self._present(row) for row in store.rows(MODULE)]
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("灌木编号", ""))]
        if status:
            rows = [row for row in rows if row.get("灌木状态") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return self._present(entry) if entry is not None else None

    def stats(self) -> dict[str, Any]:
        """养护看板用的灌木指标：面积始终按补植明细现场重算。"""
        rows = [self._present(row) for row in store.rows(MODULE)]
        effective_area = round(sum(float(row["有效栽植面积"]) for row in rows), 2)
        replant_area = round(sum(float(row["补植面积合计"]) for row in rows), 2)
        return {
            "灌木总数": len(rows),
            "待修剪": sum(1 for row in rows if row["灌木状态"] == "待修剪"),
            "病虫害": sum(1 for row in rows if row["灌木状态"] == "病虫害"),
            "已补植": sum(1 for row in rows if row["灌木状态"] == "已补植"),
            "在养面积": effective_area,
            "补植面积合计": replant_area,
        }

    # ---------- 登记 ----------
    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}"

        code = str(values.get("灌木编号")).strip()
        if any(str(row.get("灌木编号", "")).strip() == code for row in store.rows(MODULE)):
            return None, f"灌木编号 {code} 已存在，同一灌木编号重复提交只登记一次"

        area = _to_float(values.get("栽植面积"))
        if area is None:
            return None, f"栽植面积「{values.get('栽植面积')}」不是合法的非负数值，请修正后重试"

        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in BUSINESS_FIELDS:
            if field == "栽植面积":
                continue
            entry[field] = values.get(field)
        entry["原始栽植面积"] = area
        # 三条作业线统一从「待处理」起步；是否真的发生病虫害由 has_pest 把关，
        # 因此防治在待处理但无病虫时，综合状态不会被标成病虫害。
        entry["修剪状态"] = STAGES[0]
        entry["防治状态"] = STAGES[0]
        entry["补植状态"] = STAGES[0]
        entry["has_pest"] = False
        entry["补植明细"] = []
        rows.append(entry)
        self._recompute(entry)
        return self._present(entry), "灌木已登记"

    # ---------- 动作流转 ----------
    def run_action(
        self,
        entry_id: int,
        action: str,
        values: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"灌木 {entry_id} 不存在或已归档"
        workflow = WORKFLOWS.get(action)
        if workflow is None:
            return None, f"动作「{action}」不属于灌木管理可执行范围"
        values = values or {}

        try:
            if workflow == "修剪":
                message = self._advance_prune(entry)
            elif workflow == "防治":
                message = self._advance_pest(entry)
            else:
                message = self._advance_replant(entry, values)
        except ReplantError as exc:
            # 明细校验失败：状态未改动，把原因回给前端，补齐后可直接重试
            return None, str(exc)

        if message is None:
            return None, self._refuse_reason(workflow, entry)
        self._recompute(entry)
        return self._present(entry), message

    def _advance_prune(self, entry: dict[str, Any]) -> str | None:
        """修剪：待处理 → 处理中 → 已完成；已补植的灌木不再纳入修剪。"""
        if entry.get("补植状态") == STAGES[-1] and entry.get("补植明细"):
            return None  # 已完成补植，不再按待修剪处理
        stage = entry.get("修剪状态", STAGES[0])
        if stage == STAGES[0]:
            entry["修剪状态"] = STAGES[1]
            return "修剪任务已安排，当前进入处理中"
        if stage == STAGES[1]:
            entry["修剪状态"] = STAGES[2]
            return "修剪已完成"
        return None  # 已完成再提交属于跳级/重复，拒绝并允许稍后重试其它动作

    def _advance_pest(self, entry: dict[str, Any]) -> str | None:
        """防治：待处理 → 处理中 → 已完成；完成时清除病虫害标记。"""
        if not entry.get("has_pest"):
            return None  # 没有在处理的病虫害，防治动作无的放矢
        stage = entry.get("防治状态", STAGES[-1])
        if stage == STAGES[0]:
            entry["防治状态"] = STAGES[1]
            return "防治已安排，当前进入处理中"
        if stage == STAGES[1]:
            entry["防治状态"] = STAGES[2]
            entry["has_pest"] = False  # 防治闭环，病虫害标记随之消除
            return "防治处理完成，病虫害标记已清除"
        return None

    def _advance_replant(self, entry: dict[str, Any], values: dict[str, Any]) -> str | None:
        """补植：待处理（登记明细）→ 处理中 → 已完成。

        同一灌木只维护一条补植明细：处理中重复提交只会补齐/更正这条明细，
        已完成后再提交一律拒绝，保证同一灌木编号重复提交只算一次。
        """
        stage = entry.get("补植状态", STAGES[-1])
        details: list[dict[str, Any]] = entry.setdefault("补植明细", [])

        if stage == STAGES[-1]:
            return None  # 已补植，拒绝重复补植
        if stage == STAGES[0]:
            area = _to_float(values.get("补植面积"))
            if area is None or area <= 0:
                # 明细不完整不能硬落库：返回失败原因，前端可补齐后重试
                raise ReplantError("补植面积必须为大于 0 的数值，请填写后重试")
            detail = {
                "补植面积": area,
                "补植数量": values.get("补植数量") or "",
                "补植日期": str(values.get("补植日期") or "").strip() or date.today().isoformat(),
                "状态": STAGES[1],
            }
            if details:
                details[0].update(detail)  # 同一灌木重复登记只更新，不新增
            else:
                details.append(detail)
            entry["补植状态"] = STAGES[1]
            return f"补植已登记（补植 {_fmt_area(area)}），当前进入处理中"
        if stage == STAGES[1]:
            if not details:
                return None
            # 处理中再次提交面积：只补齐/更正同一条明细，仍算同一次补植，不新增、不推进。
            if "补植面积" in values:
                area = _to_float(values.get("补植面积"))
                if area is None or area <= 0:
                    raise ReplantError("补植面积必须为大于 0 的数值，请填写后重试")
                details[0]["补植面积"] = area
                if values.get("补植数量"):
                    details[0]["补植数量"] = values.get("补植数量")
                self._recompute(entry)
                return f"补植明细已更新（补植 {_fmt_area(area)}），仍为处理中，未重复计次"
            # 不携带面积即确认完工，处理中 → 已完成。
            details[0]["状态"] = STAGES[2]
            entry["补植状态"] = STAGES[2]
            return "补植已完成，栽植面积已按补植明细重算"
        return None

    def _refuse_reason(self, workflow: str, entry: dict[str, Any]) -> str:
        stage_field = STAGE_FIELDS[workflow]
        stage = entry.get(stage_field, STAGES[-1])
        code = entry.get("灌木编号", "?")
        if workflow == "修剪" and entry.get("补植状态") == STAGES[-1] and entry.get("补植明细"):
            return f"灌木 {code} 已完成补植，不再按待修剪处理"
        if workflow == "防治" and not entry.get("has_pest"):
            return f"灌木 {code} 当前没有在处理的病虫害，无需防治"
        if workflow == "补植" and stage == STAGES[-1]:
            return f"灌木 {code} 已完成补植，同一灌木编号不允许重复补植"
        if stage == STAGES[-1]:
            return f"{code} 的{workflow}作业已完成，不能重复提交或跳级推进"
        return f"{code} 的{workflow}作业当前为「{stage}」，只能推进到下一阶段，不允许跳级"

    # ---------- 派生口径 ----------
    def _recompute(self, entry: dict[str, Any]) -> None:
        """按补植明细重算面积，并统一刷新综合状态 / 待处理 / 异常标记。"""
        base = entry.get("原始栽植面积")
        if not isinstance(base, (int, float)):
            parsed = _to_float(entry.get("栽植面积"))
            base = parsed if parsed is not None else 0.0
            entry["原始栽植面积"] = base

        details = entry.setdefault("补植明细", [])
        replant_total = 0.0
        for detail in details:
            parsed = _to_float(detail.get("补植面积"))
            if parsed is not None:
                detail["补植面积"] = parsed
                replant_total += parsed
        effective = float(base) + replant_total

        entry["补植面积合计"] = round(replant_total, 2)
        entry["有效栽植面积"] = round(effective, 2)
        entry["栽植面积"] = _fmt_area(effective)

        prune_stage = entry.get("修剪状态", STAGES[0])
        pest_stage = entry.get("防治状态", STAGES[-1])
        replant_stage = entry.get("补植状态", STAGES[-1])
        has_pest = bool(entry.get("has_pest"))

        if replant_stage == STAGES[-1] and details:
            status = "已补植"
        elif replant_stage == STAGES[1]:
            status = "补植中"
        elif replant_stage == STAGES[0]:
            status = "待补植"
        elif has_pest and pest_stage != STAGES[-1]:
            status = "病虫害"
        elif prune_stage == STAGES[0]:
            status = "待修剪"
        else:
            status = "正常"

        entry["灌木状态"] = status
        entry["status"] = status
        entry["pending"] = (
            prune_stage != STAGES[-1]
            or (has_pest and pest_stage != STAGES[-1])
            or replant_stage != STAGES[-1]
        )
        entry["abnormal"] = has_pest and pest_stage != STAGES[-1]

    def _present(self, entry: dict[str, Any]) -> dict[str, Any]:
        """清单页 / 详情页 / 看板共用的唯一出口，保证字段口径一致。"""
        self._recompute(entry)
        view = dict(entry)
        view["补植明细"] = [dict(detail) for detail in entry.get("补植明细", [])]
        return view


class ReplantError(Exception):
    """补植明细校验失败：携带可读原因，交给路由层回给前端重试。"""
