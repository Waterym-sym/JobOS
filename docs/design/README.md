# 设计文档（Design）

本目录承载 JobOS 控制台的设计过程与外部参考；**视觉真源不在这里，在仓库根 [`../../DESIGN.md`](../../DESIGN.md)**（代理自动发现的约定位置）。

| 路径 | 角色 |
|---|---|
| [`../../DESIGN.md`](../../DESIGN.md) | **唯一视觉/交互真源 v0.2**：主题、色板与语义角色、字阶、组件规范、布局、深度、Do/Don't、响应式、Agent Prompt Guide |
| [references/](references/README.md) | 外部产品 DESIGN.md 只读参考副本（Linear / Notion / Claude / Vercel，MIT，带来源声明） |
| [frontend-design-draft-v0.1.md](frontend-design-draft-v0.1.md) | v0.1 草案，**已归档**，被根 DESIGN.md v0.2 替代；保留作演进留痕 |

## 前端任务的标准动线

```text
架构师索引库（§1 一分钟入口 → DESIGN.md）
  → 根 DESIGN.md（token/组件/红线，必查）
  → 01 篇页面地图 + 契约 DTO（业务口径）
  → references/（仅当 DESIGN.md §9.2 指向某参考时翻）
  → taste skill pre-flight（anti-slop 十项检查）
  → AGENTS.md（红线：无自动外发、草稿不投影、红线字段不写入）
```

变更规则：改视觉 token/组件语义先改根 DESIGN.md（本人评审），再改代码；组件里不允许出现 DESIGN.md 之外的颜色与形状。
