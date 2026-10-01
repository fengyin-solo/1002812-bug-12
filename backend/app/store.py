"""内存数据仓库：给每个业务模块准备一份可筛选、可流转的示例数据。

真实项目里这里会换成数据库访问层；当前实现只依赖标准库，保证克隆下来就能起。
"""
from __future__ import annotations

from typing import Any

from app.seed import SEED_ROWS


class Store:
    def __init__(self) -> None:
        self._tables: dict[str, list[dict[str, Any]]] = {
            name: [dict(row) for row in rows] for name, rows in SEED_ROWS.items()
        }

    def module_names(self) -> list[str]:
        return sorted(self._tables)

    def rows(self, module: str) -> list[dict[str, Any]]:
        return self._tables.setdefault(module, [])

    def find(self, module: str, entry_id: int) -> dict[str, Any] | None:
        for row in self.rows(module):
            if int(row.get("id", 0)) == entry_id:
                return row
        return None

    def overview(self) -> dict[str, object]:
        modules: list[dict[str, object]] = []
        for name in self.module_names():
            rows = self.rows(name)
            modules.append({
                "name": name,
                "created": len(rows),
                "pending": sum(1 for row in rows if row.get("pending")),
                "abnormal": sum(1 for row in rows if row.get("abnormal")),
            })
        cards = [
            {"label": "业务模块", "value": len(modules)},
            {"label": "今日新增", "value": sum(int(item["created"]) for item in modules)},
            {"label": "待处理", "value": sum(int(item["pending"]) for item in modules)},
            {"label": "异常量", "value": sum(int(item["abnormal"]) for item in modules)},
        ]
        # 灌木在养面积与补植面积始终由补植明细现场重算，刷新看板即可看到最新结果。
        shrub_stats = self.shrub_summary()
        cards.append({"label": "灌木在养面积(㎡)", "value": shrub_stats["在养面积"]})
        cards.append({"label": "累计补植面积(㎡)", "value": shrub_stats["补植面积合计"]})
        return {"cards": cards, "modules": modules, "shrub": shrub_stats}

    def shrub_summary(self) -> dict[str, object]:
        """委托灌木服务按补植明细重算面积；惰性导入避免服务层与仓库层循环依赖。"""
        from app.services.shrub import ShrubService

        return ShrubService().stats()


store = Store()
