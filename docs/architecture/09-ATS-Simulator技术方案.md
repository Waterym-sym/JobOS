# 09 ATS Simulator 技术方案

> 版本：v1.1（新增 BOSS 在线载荷检查；与第 22 篇模板渠道体系对齐）

## 定位

ATS Simulator 是简历**可解析性、结构与 JD 相关性**的透明工程检查器，不是企业 ATS 逆向，也不预测录用概率。v1.1 检查对象有三类：**ATS 附件导出件、BOSS 在线载荷、招呼语合规（交接 10/11）**。输出问题定位和安全优化建议，不引导堆砌或虚构。

```text
ATSScore = .30 Parseability + .25 KeywordCoverage + .20 Structure
         + .15 ChronologyConsistency + .10 ContactCompleteness
```

## 检查器

| 维度 | 附件检查 | 在线载荷检查（v1.1 新增） |
|---|---|---|
| Parseability | PDF 文本层、复制顺序、字体嵌入、非扫描主体、DOCX XML、核心信息不在图片/页眉页脚 | 四模块（个人优势/工作内容/项目描述/技能）纯文本可提交、无异常字符、换行合规 |
| Keyword Coverage | must-have 规范词/同义词在**支持性 Claim** 中自然出现 | 技能模块与 JD 技能交集可解释；工作/项目模块含岗位关键词且均有证据 |
| Structure | 标准标题、单栏 ATS 模板、倒序经历、清晰 section | 模块映射正确（内容不错位到技能栏）；模块条数与平台限制 |
| Chronology | 日期格式、起止关系、重叠说明、年限可复算 | 不包含/不修改公司名、职位、起止时间、学历（红线字段由扩展忽略） |
| Contact | 选定地区下姓名、邮箱、电话/链接完整 | 在线简历联系方式以 BOSS 站内资料为准，载荷不重复注入 |

字数与长度：四模块各自校验 BOSS 字数上限（按扩展实测配置化），超限给出必须删减的定位建议；Inference 内容不得进入在线载荷。

## 模板渠道边界（与专题 22 联动）

- `channel=ats` 模板族（单栏、标准字体、无头像/图形正文）必须通过解析矩阵才能进入投递包。
- `channel=showcase` 模板族只用于展示渠道；在 ATS 场景选用时系统**强提示并阻止进入 ATS 导出队列**；ATS 报告对 showcase 导出件直接标记 `wrong_channel`（不给可解析分数，避免误用）。
- 模板升级/切换后重跑同一解析矩阵；解析结果与 `template_id/version、renderer_version` 绑定。
- DOCX 复杂版式降级到 ATS 单栏时，报告注明「版式重建」并校验字段完整。

## 双路径解析与输出

PDF 走文本提取 + 页面布局两条路径；DOCX 走 XML 语义结构 + 转 PDF 后文本路径；Markdown 走 AST。结果不一致即报 `parse_order_risk`。每项问题输出 `severity、section、claim/template_element、evidence、suggestion、auto_fixable`。

目标：ATS 模板族导出解析成功率 ≥ 98%，关键字段完整率 ≥ 95%；在线载荷校验通过率（合法字符、字数、模块映射）100%，红线字段零写入。

## 解析实现细节

PDF：文本层存在性、抽取字符数、阅读顺序、字体/图片比例、疑似 OCR 错误、文本框碎片化、中文字体子集嵌入。DOCX：段落、表格、页眉页脚、文本框、隐藏文本、样式、XML 有效性。在线载荷：提交前在扩展侧预检（专题 21 第 7 节）+ 服务端按同一规则复检。导出后由**独立解析器**重读，不信任 renderer 内存模型；PDF/DOCX/MD 字段抽取不一致报 high 并提示使用 ATS 单栏模板。

## 规则库与建议边界

按地区、语言、模板版本配置：常见 section 标题、日期、电话/邮箱、中英文分词、技能同义词、在线模块字数表。建议分 `must_fix`（不可解析、时间冲突、红线字段、超字数）、`should_fix`（标题不标准、关键词无证据上下文）、`optional`（篇幅、展示优化）。自动修复只调模板布局/标题/已确认 Claim 排序；内容修复一律创建草稿。不能建议夸大、添加未证实技能或 JD 中不存在的要求。

## 结果对象

`ats_report`：`version_id, channel, parser_versions, template{id,version}, score_breakdown, findings[], extracted_profile, keyword_coverage, parse_order, online_payload_checks, greeting_checks_ref, generated_at`。finding 含 `id,severity,dimension,location,evidence,suggestion,auto_fixable`。

## 测试集

中英双语模板矩阵：单栏、多栏、表格、图片文本、扫描件、长简历、不同字体/日期、降级 DOCX；以及 BOSS 四模块字数/字符边界、红线字段用例。每次 renderer/解析器升级对同一 corpus 比较字段准确率、阅读顺序与误报率；新增槽位映射与渠道隔离断言（showcase 不可入 ATS）；不以分数提升牺牲人工阅读体验。
