---
target: docs/superpowers/specs/2026-08-15-ui-v2-console-design.md
total_score: 19
max_score: 40
na_heuristics: 
p0_count: 2
p1_count: 2
timestamp: 2026-08-15T03-16-21Z
slug: perpowers-specs-2026-08-15-ui-v2-console-design-md
---
Method: dual-agent (A: agent_fecff053 · B: agent_7587f7a)
Target: docs/superpowers/specs/2026-08-15-ui-v2-console-design.md (markdown spec, no implementation)

## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 3 | 进度/日志/徽标保留 + pending-gate 恢复，但无跨页运行中任务指示、无 SSE 连接状态面 |
| 2 | Match System / Real World | 2 | 伏笔=裸 id/描述/状态表格；bible 产物（概念/世界观/人物/大纲）是否结构化呈现未承诺 |
| 3 | User Control and Freedom | 2 | 取消/反馈重生成/gate 恢复在，但「无法重做单个设定阶段」原样搬运；强行放行不可逆且无确认设计 |
| 4 | Consistency and Standards | 3 | AntD 5 惯例统一，但 Sider 混排全局项（项目列表）与项目域 7 页 |
| 5 | Error Prevention | 2 | 空反馈拦截好；任务运行中离开页面、双击开始生成、demo 反馈无效警示均未设计 |
| 6 | Recognition Rather Than Recall | 2 | premise 输入（产品前门）在 8 页表格中无位置；章节 chips 是裸数字无标题 |
| 7 | Flexibility and Efficiency of Use | 1 | 零加速器：无「从第 N 章续写」一键恢复（后端幂等续跑是招牌特性）、无评分聚合视图 |
| 8 | Aesthetic and Minimalist Design | 2 | AntD 默认皮 + 8 项扁平 Sider；阅读型产品无排版立场 |
| 9 | Error Recovery | 2 | 409/422 通知在，但生成中断线期间错过事件/gate/job_end 的对账行为未指定 |
| 10 | Help and Documentation | 0 | 无任何 onboarding、demo/live 解释、空状态教学文案 |
| **Total** | | **19/40** | **Acceptable（需显著改进）** |

## Design Specificity Verdict

**LLM 评审**：这是一份「端点到页面的转写」，不是产品设计——8 个菜单项与现有 /api 路由 1:1 对应，任何 CRUD 后台换个名词即可复用；产品真正的差异点（人在 gate 上阅读和裁决生成文本、分钟级长等待、反馈触发付费重生成）没有得到一行设计投入。设定产物的呈现方式（结构化 vs 旧版 4000 字符 pre 转储）未承诺。全局 GateModal + 刷新恢复是唯一真正扎根产品的决策。

**确定性扫描**：目标与旧版 index.html 检测均 0 findings（注意：HTML 解析模块缺失，regex 降级模式，属 undercount 非清白证明）。spec 与仓库事实核对全部通过（所有依赖端点存在、端口/挂载/gitignore 描述准确）；唯一未点名端点是 GET /api/mode（徽标功能隐含使用）；dist 挂载与 /legacy 属未来实现（符合预期）。

## Overall Impression

工程骨架扎实（API 全通、验收清单工作流化），但设计层是模板搬运。最大机会：把设计预算从导航铬件转移到「读与裁决」——这才是产品价值时刻。

## What's Working

1. pending-gate 恢复（GET /api/jobs/{id}）——修复旧 UI 刷新丢 gate 的最严重缺陷。
2. Gate 做成 SSE 驱动的全局 Modal——审批与页面解耦，隐含支持边生成边阅读。
3. 对等验收清单按真实故事流走（新建→设定含反馈→生成含取消→读→评分→伏笔→导出），是正确的 parity 定义。

## Priority Issues

1. **[P0] premise 生成无家可归**：8 页路由表没有创意输入入口（旧版前门），与「全功能对等」矛盾。修法：premise 作为 Setup Steps 的 Step 0，或概览页 概念=无 时给 CTA 卡。→ $impeccable shape
2. **[P0] 无跨页运行中任务存在感**：10 分钟生成期间离开 /generate 即失去全部状态。修法：Header 常驻任务条（项目/当前阶段/N/M 章/等待审批/取消）渲染于所有 /p/:name 路由。→ $impeccable shape
3. **[P1] SSE 中途断线未指定**：自动重连≠状态对账。修法：重连后先从 status+jobs 拉取对账再信任本地状态，断线时显示连接丢失横幅。→ $impeccable harden
4. **[P1] Gate modal 无风险分级**：「带反馈重生成」触发整段付费重跑、反馈历史不可见；「强行放行」不可逆无确认。修法：常规/高风险两种 modal 变体 + 历史反馈条 + 强行放行二次确认。→ $impeccable shape / $impeccable harden
5. **[P2] 8 项扁平 Sider 混作用域**：项目列表与 7 个项目域页面同级。修法：项目切换只在 Header 选择器；Sider 6-7 项分组为 创作（设定/生成/阅读）与 审阅/输出（评分/伏笔/导出）。→ $impeccable layout

## Persona Red Flags

**Alex（效率用户）**：无一键「从第 N 章续写」；N 章输入不反馈已存在/将写章节；评分页无跨章趋势聚合；无法重做单设定阶段（README 记录为手动 bible 手术，新 Setup 页未解决）；导出显示文件系统路径——在 spec 自己设计的 Tauri/浏览器未来里无用。

**Sam（无障碍）**：零 a11y 承诺。全局 modal 弹出需 live-region 播报与焦点管理；可折叠 Sider 键盘故事、终端式事件日志（快速滚动区无暂停/结构化替代）、评分仅用徽标颜色示意——均未指定。

**Jordan（新手）**：demo 是默认模式但只有一个徽标、无解释（旧版至少有「演示模式：反馈不会改变生成内容」日志，新 spec 静默丢弃）；8 个等权菜单不暗示顺序（设定→生成→阅读）；概览布尔卡（概念/世界观/大纲有无）对新人是行话；第一个动作（输入创意）无落点（见 P0-1）。

## Minor Observations

- 空状态（0 项目/0 章/0 评分/0 伏笔）均未设计（旧版有「暂无评分记录…」）。
- 长章节渲染无立场；50 章=50 个 chips，无虚拟化/分页承诺。
- chapter_skipped(reason) 在协议中存在但无页面在运行后呈现跳过历史。
- Header 选择器与项目列表页功能重复，一致性未约定。
- 409 拒绝无「跳到运行中任务」CTA，是死路错误。
- 测试计划只覆盖 GateModal/SSE，8 个 parity 页面无 Router/页面级测试。
- 文案零承诺：既不保留旧版中文阶段/gate 文案（真实资产），也不指定新文案。

## Questions to Consider

1. 如果产品的核心价值时刻是「人在 gate 上裁决生成的文本」，为什么设计预算全花在导航铬件上、对产物/章节/评语如何被阅读零投入——「左章列表右正文」就是小说工具的全部阅读体验吗？
2. 重构动机是旧 UI 信息密度到顶——但新 IA 是同样的面板每路由一个、同时可见性更低（旧版一屏可见生成+阅读+评分+伏笔）。具体解决了什么密度问题？
3. GateModal 在 Alex 读第 3 章时弹出会说什么？若无章号、无分数、无内容链接，这个 spec 最好的主意会变成最危险的界面。
