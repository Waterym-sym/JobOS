# 设计参考（vendored references）

本目录的四份 `*.md` 是外部产品 DESIGN.md 的**只读参考副本**，用于合成 JobOS 自己的视觉真相（根目录 [`../../../DESIGN.md`](../../../DESIGN.md)）。**它们不是 JobOS 的设计规范，禁止直接让代理按某一份照抄。**

| 文件 | 原产品 | 在 JobOS 合成中取什么 |
|---|---|---|
| [linear.md](linear.md) | Linear（linear.app） | 整体骨架：极简高密度、精确间距、键盘优先、侧边导航秩序 |
| [notion.md](notion.md) | Notion | A4 编辑器与知识库：软表面、slash 菜单、内容/排版分流 |
| [claude.md](claude.md) | Claude（Anthropic） | AI 工作区：草稿态语言、证据/溯源表面、人与 AI 视觉阶层 |
| [vercel.md](vercel.md) | Vercel | 开发者页面：等宽数据、状态行、批次/风控/契约只读面板 |

## 来源与许可

- 来源仓库：[VoltAgent/awesome-design-md](https://github.com/VoltAgent/awesome-design-md)（commit：vendoring 时 main 分支，2026-09-15）
- 许可：MIT，全文见 [LICENSE-VoltAgent.txt](LICENSE-VoltAgent.txt)。原仓库声明：这些文件是对公开网站可见 CSS 值的分析性整理，"as is" 提供，不主张拥有任何站点的视觉身份。
- 原文件路径：`design-md/linear.app/DESIGN.md`、`design-md/notion/DESIGN.md`、`design-md/claude/DESIGN.md`、`design-md/vercel/DESIGN.md`。
- 本目录文件**不手工修改内容**（仅文件重命名）；升级时整体替换并更新本说明日期。各产品商标/视觉身份归原方所有，JobOS 仅借鉴模式，不复制品牌资产（logo、插画、专有字体文件）。

## 代理使用规约

1. 开发任何 page/component 前先读根 `DESIGN.md`；只有根 DESIGN.md 明确指向某参考时才读本目录对应文件。
2. 参考文件解决「这个模式成熟产品怎么处理」；具体 token 以根 DESIGN.md 为唯一真源，冲突时以根 DESIGN.md 为准。
3. 禁止把四份参考的 token（颜色/字体/圆角）混搭拼接；合成决策已经在根 DESIGN.md §1/§9 完成。
