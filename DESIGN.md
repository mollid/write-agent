---
version: alpha
name: "小说创作平台 · 管理后台"
description: >
  亮色、克制、数据优先的管理后台设计系统：近灰白画布上浮纯白卡片，
  单一品牌强调色（紫 #8848F9），层次靠轻阴影与 1px 分隔线，禁渐变/霓虹。
colors:
  primary: "#8848F9"
  primary-tint: "#F1E4FB"
  canvas: "#FAFAFA"
  surface: "#FFFFFF"
  ink: "#0A0A0A"
  graphite: "#202020"
  steel: "#7F7F7F"
  faded-ink: "rgba(10, 10, 10, 0.6)"
  line: "#E5E5E5"
  border: "#E0DFDF"
  border-input: "#E2E2E2"
  icon: "#171717"
  positive: "#00A63E"
  negative: "#F4165F"
typography:
  display:
    fontFamily: Inter
    fontSize: 30px
    fontWeight: 700
    lineHeight: 36px
  display-s:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: 700
    lineHeight: 32px
  title-l:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: 600
    lineHeight: 28px
  title:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: 600
    lineHeight: 24px
  subtitle:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: 400
    lineHeight: 24px
  body:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: 400
    lineHeight: 20px
  body-m:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: 500
    lineHeight: 20px
  caption:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: 400
    lineHeight: 16px
rounded:
  control: 6px
  card: 12px
  pill: 999px
spacing:
  base: 4px
  xs: 8px
  sm: 12px
  md: 16px
  lg: 24px
  xl: 32px
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "#FFFFFF"
    rounded: "{rounded.control}"
    height: 36px
    padding: 12px
  button-primary-hover:
    backgroundColor: "#7A3CE6"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.graphite}"
    rounded: "{rounded.control}"
    height: 36px
  badge-active:
    backgroundColor: "{colors.primary}"
    textColor: "#FFFFFF"
  badge-inactive:
    backgroundColor: "{colors.primary-tint}"
    textColor: "{colors.graphite}"
  badge-positive:
    backgroundColor: "{colors.positive}"
    textColor: "#FFFFFF"
  badge-negative:
    backgroundColor: "{colors.negative}"
    textColor: "#FFFFFF"
  badge-pending:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.graphite}"
  card:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.card}"
    padding: 24px
  input:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.control}"
    height: 36px
  switch:
    height: 18px
    width: 32px
  progress:
    backgroundColor: "{colors.primary}"
  progress-track:
    backgroundColor: "rgba(136, 72, 249, 0.2)"
  avatar:
    backgroundColor: "{colors.primary-tint}"
    size: 32px
  table-header:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.graphite}"
    height: 40px
  table-row-hover:
    backgroundColor: "{colors.canvas}"
  heading:
    textColor: "{colors.ink}"
    typography: "{typography.display}"
  text-secondary:
    textColor: "{colors.steel}"
    typography: "{typography.caption}"
  sidebar-group-title:
    textColor: "{colors.faded-ink}"
    typography: "{typography.caption}"
  icon:
    textColor: "{colors.icon}"
    size: 16px
  divider:
    backgroundColor: "{colors.line}"
    height: 1px
  secondary-outline:
    backgroundColor: "{colors.border}"
    height: 1px
  input-border:
    backgroundColor: "{colors.border-input}"
    height: 1px
---

# Design System — 小说创作平台 · 管理后台

> **来源**：`design/react/`（Pixso 导出的 React/CSS，6 个静态页面，全部 token 均从导出代码实测提取）
> **用途**：后续 Web UI 页面的唯一设计规范（single source of truth）。新页面先读本文，再写代码。
> **说明**：导出为静态稿，未设计 hover/active/focus 等交互态；文中标注 **⟡推导** 的条目是基于既有 token 推导的补充规范，实现时保持克制。

## Overview

一个**亮色、克制、数据优先**的管理后台：近灰白的画布上浮着纯白卡片，层次只靠一枚极轻的阴影和 1px 分隔线；全部注意力交给**唯一的紫色强调**与数据本身。

- **密度 Density：6/10**（表格 + KPI + 筛选器，信息紧凑但不拥挤）
- **变化 Variance：2/10**（严格的左导航 + 顶栏 + 卡片栅格，完全可预期的结构化布局）
- **动效 Motion：1/10**（静态克制；只允许极短的过渡，见「动效与交互」附则）
- 关键词：临床感、扁平、单强调色、白色浮层、1px 线条、无装饰图形。

这一极简、专业的气质服务于「作者 → 创作 → 交付」全流程——读稿者（作者/编辑/管理员）需要快速定位状态与数据，而非被视觉元素分心。

## Colors

整套 UI **只有一个品牌强调色（紫）**，红/绿仅作语义状态色。所有颜色实测自导出 CSS（按出现频次与用途归类）。颜色 token（见 YAML front matter）采用语义命名：`primary`=品牌紫、`canvas`=画布灰、`surface`=纯白面、`ink`=墨黑、`positive`/`negative`=语义状态色。

### 中性色（Zinc 系）

| 名称 | 值 | 角色 |
|---|---|---|
| 画布灰 Canvas | `#FAFAFA` | 页面/侧栏背景（`colors.canvas`） |
| 纯净面 Pure Surface | `#FFFFFF` | 卡片、顶栏、表单、内容白板（`colors.surface`） |
| 墨黑 Ink | `#0A0A0A` | 页面标题、导航项、图标文字（近黑，非纯黑）（`colors.ink`） |
| 正文石墨 Graphite | `#202020` | 正文、表格单元格、卡片标题（`colors.graphite`） |
| 弱墨灰 Faded Ink | `rgba(10,10,10,0.6)` | 侧栏分组标题（核心业务/系统管理）、次级说明（`colors.faded-ink`） |
| 中灰 Steel | `#7F7F7F` | 辅助文本、占位符（搜索…）、页面副标题（`colors.steel`） |
| 浅线灰 Line | `#E5E5E5` | 表格行分隔线、次级分隔（`colors.line`） |
| 边框灰 Border | `#E0DFDF` / `#E2E2E2` | 输入框边框、待处理徽章描边、关闭态开关轨道（`colors.border` / `colors.border-input`） |
| 图标黑 Icon Ink | `#171717` | 16px 线性图标（`colors.icon`） |

### 品牌强调（唯一 accent）

| 名称 | 值 | 角色 |
|---|---|---|
| 品牌紫 Brand Purple | `#8848F9` | 主按钮、激活徽章（进行中/已完成/运行中）、进度条填充、激活态（`colors.primary`） |
| 紫浅底 Purple Tint | `#F1E4FB` | 停用徽章底色（已停止/已暂停）、头像底、图标容器（`colors.primary-tint`） |
| 紫轨道 Purple Track | `rgba(136,72,249,0.20)` | 进度条轨道（`colors.primary` 20% 透明度） |

### 语义状态色

| 名称 | 值 | 角色 |
|---|---|---|
| 正向绿 Positive | `#00A63E` | KPI 正增量（+2/+5）、成功/激活状态（`colors.positive`） |
| 负向红 Negative | `#F4165F` | 失败/异常徽章、KPI 负增量（-5%）、危险操作（`colors.negative`） |

### 颜色禁令

- **禁止渐变**：任何按钮、卡片、标题不做 gradient。
- **禁止霓虹光晕**：不出现 `box-shadow` 彩色外发光、霓虹描边。
- **禁止纯黑 `#000000`**：文本一律用 Ink `#0A0A0A` / Graphite `#202020`。
- **禁止第二个强调色**：青、橙、蓝等一律不引入；红绿只作语义状态。
- **整站只用上表颜色**：新增颜色必须先登记角色，不允许临时的相近色（如 `#8848FA`）。

## Typography

设计源内嵌 **Inter** 四个字重（400/500/600/700）。落地时保持 Inter（`font-family: Inter, -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif`），不更换字体、不引入衬线体。

| 层级 | 字号/行高 | 字重 | 颜色 | 用途 |
|---|---|---|---|---|
| Display | 30px / 36px | 700 Bold | Ink | 顶栏页面标题、KPI 大数字 |
| Display-S | 24px / 32px | 700 Bold | Ink | 次级大数字（如 68%） |
| Title-L | 18px / 28px | 600 SemiBold | Ink | 侧栏品牌名「小说创作平台」 |
| Title | 16px / 24px | 600 SemiBold | Graphite | 卡片标题（最近任务 / Agent 状态分布） |
| Subtitle | 16px / 24px | 400 Regular | Steel | 页面副标题（系统概览与关键指标监控） |
| Body | 14px / 20px | 400 Regular | Graphite | 正文、表格单元格、导航项、按钮 |
| Body-M | 14px / 20px | 500 Medium | Graphite | 表头、筛选 tab、激活导航 |
| Caption | 12px / 16px | 400/500 | 视语义 | 徽章、分组标题（弱墨灰）、KPI 标签与增量、时间戳 |

排印规则：

- 层级靠**字重 + 颜色**区分，不靠拉大字号；除 Display 外正文区不出现 >18px 的字。
- 数字对齐：所有表格数值、进度百分比、统计数用 `font-variant-numeric: tabular-nums` ⟡推导。
- 中英混排沿用设计源样式：分组标题可带英文小注（概览 Dashboard），正文中文为主、专有名词（Agent、Dashboard）保留英文。
- 文本不使用全部大写（ALL CAPS）作为样式 ⟡推导。

## Layout

设计画布 **1920px 宽**，桌面优先的管理后台布局：

```
┌──────────┬──────────────────────────────────────┐
│          │ 顶栏 64px：页面标题(30px Bold) · 头像区 │
│  侧栏     ├──────────────────────────────────────┤
│  255px   │  内容区：24px 内距                     │
│          │  ┌──── 白卡(12px圆角) ─────┐ ×N        │
│          │  └─────────────────────────┘           │
└──────────┴──────────────────────────────────────┘
```

- **侧栏 255px**：背景画布灰 `#FAFAFA`，与内容区无描边分隔（靠内容白板/卡片对比）。品牌名 18px SemiBold 居顶；分组标题 12px Medium 弱墨灰；导航项高 60px、14px Regular + 16px 图标。
- **顶栏 64px**：白底，底部 1px `#E0DFDF` 分隔线 ⟡推导；左侧页面标题 30px Bold，右侧管理员头像 + 姓名/邮箱。
- **内容区**：主列宽 1664px（1920 − 255 侧栏 − 边距），四周 24px 内距；内容白板（1664−48=1616px）为白色承载卡片。
- **卡片栅格**：KPI 一行 4 张等宽；项目卡片网格 2–3 列；图表区 1:2 非对称（环形图窄、趋势图宽）。
- **间距体系**：4 / 8 / 12 / 16 / 24（4px 网格）；区块间 24px，卡片内元素 8–16px。
- 表单页（系统设置）：左侧分类导航（垂直）+ 右侧表单卡，保存按钮吸在表单底部右侧。
- **响应式 ⟡推导**（导出仅 1920 桌面稿，按下列规则降级）：
  - ≥1440px：按上述原样。
  - 1024–1440px：内容区自适应收缩，KPI 4→2 列，卡片网格 3→2 列。
  - <768px：侧栏折叠为抽屉/图标栏（80px），所有多栏塌成单列，顶栏标题降为 20px；禁止横向滚动。
  - 表格在窄屏横向滚动，但操作列固定。

## Elevation & Depth

深度只靠**轻阴影 + 1px 分隔线 + 白板对比**表达，不引入重阴影或彩色投影。

- 卡片阴影**只有一层**：`0 1px 2px -1px rgba(0,0,0,0.10), 0 1px 3px 0 rgba(0,0,0,0.10)`（= Tailwind `shadow-sm`），由此产生「近灰白画布上浮起纯白卡片」的层次。
- 内容白板/卡片对比制造主层次；卡片内再以 1px `#E5E5E5` 分隔线（而非嵌套卡片）区分区块。
- **禁止**渐变、霓虹光晕、彩色外发光、更重的阴影来做层级——层级（importance）永远靠颜色深浅与 1px 线，而非空间悬浮深度。

## Shapes

形状语言定义为**单一圆角体系 + 全圆角胶囊**，不混用新圆角。

- **控件与输入**：6px 圆角（按钮、输入框、筛选小芯片）→ `rounded.control`。
- **卡片与内容容器**：12px 圆角 → `rounded.card`。
- **胶囊元素**：全圆角 `999px` → `rounded.pill`（状态徽章、开关、进度条、迷你操作按钮）。
- **头像/图标容器**：32px 正圆（非方形），紫浅底 `#F1E4FB`。
- **禁令**：不出现 8 / 16 / 20px 等新圆角；同一视图内不混合圆角与直角（不可见 0px 硬角落，除非为线条分隔线）。

## Components

所有数值均为导出实测。间距走 **4px 基准网格**（4 / 8 / 12 / 16 / 24）。组件 token 见 YAML front matter `components` 段。

### 按钮 Button

| 变体 | 规格 | 样式 |
|---|---|---|
| 主按钮 Primary | 高 36px，左右内距 12px（实测 112×36） | 底色 `{colors.primary}`，白字 14px Body，圆角 **6px**，无边框无阴影 |
| 次按钮 Secondary | 高 36px | 白底 + 1px `#E0DFDF` 描边，Graphite 字，圆角 6px |
| 迷你操作 Mini | 高 22px 左右，内距 4×8px（表格/卡片内「查看/编辑」） | 全圆角胶囊；实底紫或紫浅底+紫字 ⟡推导 |

- 主按钮每屏**只出现一个**（新建项目 / 保存设置 / 添加用户）；同区域的其余动作降级为次按钮或表格内文字/迷你按钮。
- 交互态 ⟡推导：hover 主按钮 `#7A3CE6`（加深约 8%），active 下沉 `translateY(1px)`；焦点环 `0 0 0 2px rgba(136,72,249,0.35)`；次按钮 hover 底色 `#FAFAFA`。

### 卡片 Card

- 白底 `{colors.surface}`，圆角 **12px**（`{rounded.card}`），阴影仅 `shadow-sm`（见 Elevation & Depth），不加边框。
- 内距 **24px**（`{spacing.lg}`），卡片内垂直间距 24px；不加大阴影、不加边框来叠层次。
- KPI 卡结构：图标容器（32px 圆角方形，紫浅底）+ 标签（12px Caption）→ 数字（30px Bold Ink）→ 增量（12px，正 `{colors.positive}` / 负 `{colors.negative}`）。
- 图表/表格卡结构：卡片标题（16px SemiBold）+ 说明（12px Steel）→ 内容区。
- 高密度场景优先用 1px 分隔线（`{colors.line}`）替代嵌套卡片。

### 表格 Table

- 表头：高 **40px**，14px Medium，Graphite，白底（`{colors.surface}`，无表头底色、无斑马纹）。
- 数据行：以 **1px `{colors.line}` 底部分隔线**分行；单元格 14px/20px Regular；行高约 56–64px ⟡推导。
- 数值列（进度、版本号、时间）右对齐或等宽数字；操作列右对齐，放「查看/编辑」迷你按钮或文字链。
- 行 hover ⟡推导：底色 `{colors.canvas}`（不使用紫色 hover）。
- 表格永远放在白卡内，筛选工具条（搜索 + 下拉 + 按钮）置于卡片上方、与卡片同宽。

### 状态徽章 Badge（胶囊形，`{rounded.pill}`，高约 22px，内距 4×8px，字 12px）

| 状态 | 底色 | 字色 | 实例 |
|---|---|---|---|
| 进行中 / 运行中 / 已完成 | `{colors.primary}` 实底 | `#FFFFFF` | 任务、Agent |
| 失败 / 异常 | `{colors.negative}` 实底 | `#FFFFFF` | 任务、Agent |
| 待处理 | 白底 + 1px `#E0DFDF` 描边 | Graphite | 任务 |
| 已停止 / 已暂停 | `{colors.primary-tint}` | Graphite | Agent、项目 |
| 激活 / 成功 | Positive 体系（实底或 10% 底 ⟡推导） | 白 / Positive | 用户 |

- 徽章为**纯色胶囊 + 文字**，不带图标、不加阴影。
- 状态色语义全站一致：紫=活跃/正向进行，红=失败/异常，灰=待定，浅紫=停用，绿=确认成功。

### 输入与选择 Input / Select

- 高 **36px**，圆角 **6px**，白底，1px `{colors.border-input}` 描边；占位符 14px Steel（搜索用户名或邮箱…）。
- 焦点 ⟡推导：描边变 `{colors.primary}` + 外扩 `0 0 0 2px rgba(136,72,249,0.20)`。
- 标签在输入框上方（系统设置页样式）：12–14px，Graphite；说明文字在下方 12px Steel。
- 工具条布局：搜索框占主宽（实测 1082px），筛选下拉与动作按钮居右，间距 12px。

### 开关 Toggle

- 轨道 **32×18px** 全圆角；关闭 `{colors.border-input}`，开启 `{colors.primary}`；白色圆钮。
- 用于设置页成对的「标签 + 说明 + 开关」行，行间距 16–24px。

### 进度条 Progress

- 胶囊形（全圆角，`{rounded.pill}`），高 6–8px ⟡推导；轨道 `{colors.primary}` 20% 透明、填充 `{colors.primary}`；百分比数字用等宽数字。

### 筛选 Tab / Chips（任务中心）

- 胶囊改 **6px 圆角** 小芯片：内距 4×8px，字 14px Medium，间距 6px。
- 激活 ⟡推导：紫底白字或紫字+1px 紫描边；未激活：白底 Graphite 字 + 1px `{colors.border}`。

### 头像与图标容器 Avatar

- 32px 正圆，紫浅底 `{colors.primary-tint}`，内置首字/线性图标（紫或 `{colors.icon}`）；顶栏右侧配「管理员 + 邮箱」两行文本。
- 侧栏导航图标 16px，`{colors.icon}`。

### 图表 Chart

- 环形图（Agent 状态分布）：主段 `{colors.primary}`，其余段用中性灰（`{colors.line}`/`{colors.border}`），异常段 `{colors.negative}`；中心放大数字。
- 柱状图（7 天趋势）：柱体 `{colors.primary}`（可 80% 透明度做次周对比），坐标文字 12px Steel，无网格线或仅 1px 浅线。
- 图表不引入第三方配色；图例文字 12px。

## Do's and Don'ts

**Do**

- Do 只用一个品牌强调色（紫）作为全站唯一 accent；红绿仅限语义状态。
- Do 用**字重 + 颜色**建立层级，而非靠拉大字号或加投影。
- Do 主按钮每屏至多一个；同区其余动作降级为次按钮或文字/迷你按钮。
- Do 保持 WCAG AA 对比度（正文与背景 4.5:1 以上），键盘可达并提供可见焦点环。
- Do 所有数值/百分比/时间用等宽数字（`tabular-nums`）。
- Do 动效只动画 `transform` 与 `opacity`，时长 150–200ms、`ease-out`；加载态用骨架屏而非圆形 spinner。
- Do 占位/文案用真实语义示例（如「星际迷航：新纪元」），不用 Lorem Ipsum / Acme / John Doe。
- Do 管理后台保持左对齐、结构化；不做居中 Hero 式排版。

**Don't**

- Don't 使用渐变、霓虹/发光、彩色投影 —— 层次只靠 shadow-sm 和 1px 线。
- Don't 使用纯黑 `#000`、任何超出白底非白字的按钮字色。
- Don't 引入第二个强调色（无蓝、青、橙；红绿仅限语义状态）。
- Don't 混用圆角体系：控件 6px、卡片 12px、胶囊全圆角，不出现 8/16/20px 等新圆角。
- Don't 给表格加斑马纹、重阴影、表头底色（表头为白底 Medium 字）。
- Don't 用 emoji 作图标；图标统一 16px 线性风格、`{colors.icon}` 色。
- Don't 用超大字号制造层级。
- Don't 给徽章加图标/阴影，且状态语义不得跨色滥用（紫≠失败，红≠成功）。
- Don't 临时造颜色：任何新色先入 Colors 登记角色再使用。
- Don't 用 AI 文案腔（"赋能/无缝/极致/Next-Gen"）。
- Don't 图片资源引用外链占位图，用本地 SVG/图标或纯色容器。

---

## 附：页面清单与信息架构

| 页面 | 路由（导出） | Frame | 内容 |
|---|---|---|---|
| 概览 Dashboard | `/` | Frame21 | 4 张 KPI 卡、Agent 状态分布（环形图）、任务完成趋势（7 天柱状图）、最近任务表 |
| 项目管理 | `/frame21440` | Frame21440 | 新建项目按钮 + 项目卡片网格（进度、成员、状态标签） |
| 用户管理 | `/frame21872` | Frame21872 | 搜索/角色筛选 + 用户表格（角色、状态、注册时间、操作） |
| 系统设置 | `/frame22301` | Frame22301 | 左侧设置分类导航 + 表单（输入框、开关）+ 保存按钮 |
| Agent 管理 | `/frame2555` | Frame2555 | 全局配置 + Agent 列表表格（类型、状态、模型版本、最后活跃、操作） |
| 任务中心 | `/frame2977` | Frame2977 | 状态筛选 tab + 搜索 + 高级筛选 + 任务表格（进度条、状态徽章） |

**外壳（六页共享）**：左侧固定导航（255px）+ 顶栏（64px，页面标题 + 管理员身份）+ 内容区。

## 附：动效与交互（⟡全部为推导规范）

静态稿无动效，按「Motion 1/10 克制」补充：

- 时长：hover/状态切换 **150ms**，弹层/抽屉 **200ms**；缓动 `ease-out`。不做弹跳、不做循环动画。
- 只动画 `transform` 与 `opacity`；绝不动画 `width/height/top/left`。
- 按下反馈：主/次按钮 `active` 下沉 1px。
- 焦点可见性：所有交互元素聚焦时显示 2px 紫色焦点环（见 Components/按钮与输入），键盘可达。
- 加载态：表格/卡片用**骨架屏**（灰色块 + 12px 圆角，shimmer 可选），不用圆形 spinner。
- 空状态：一句话说明 + 一个主操作按钮（如「新建项目」），配 16px 线性图标，不用插画堆砌。
- 错误态：表单错误红字（`{colors.negative}`）显示在字段下方；危险操作二次确认弹窗用同一套卡片 token。

## 附：落地 ui-v2（Ant Design 5）主题映射

在 `ui-v2` 中实现新页面时，用下列 token 对齐本规范（ConfigProvider theme）：

```ts
// design tokens ↔ Ant Design 5
{
  token: {
    colorPrimary: "#8848F9",            // 品牌紫
    colorSuccess: "#00A63E",
    colorError: "#F4165F",
    colorBgLayout: "#FAFAFA",           // 画布灰（页面背景）
    colorBgContainer: "#FFFFFF",        // 卡片/表格底
    colorText: "#202020",               // 正文石墨
    colorTextSecondary: "#7F7F7F",      // 中灰
    colorBorder: "#E0DFDF",
    colorBorderSecondary: "#E5E5E5",
    borderRadius: 6,                    // 按钮/输入框
    fontFamily: 'Inter, -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif',
    fontSize: 14,
    controlHeight: 36,                  // 按钮/输入框高度
  },
  components: {
    Card:   { borderRadiusLG: 12, paddingLG: 24 },        // 卡片 12px + 24 内距
    Table:  { headerBg: "#FFFFFF", headerColor: "#202020",
              rowHoverBg: "#FAFAFA", cellPaddingBlock: 16 },
    Badge:  {} /* 用 status 色 + 胶囊自定义渲染 */,
    Progress: { trackBg: "rgba(136,72,249,0.20)" },
    Switch: { trackHeight: 18, trackWidth: 32 },
  },
}
```

CSS 变量版（非 AntD 场景直接取用）：

```css
:root {
  --canvas: #FAFAFA;
  --surface: #FFFFFF;
  --ink: #0A0A0A;
  --graphite: #202020;
  --ink-60: rgba(10, 10, 10, 0.6);
  --steel: #7F7F7F;
  --line: #E5E5E5;
  --border: #E0DFDF;
  --border-2: #E2E2E2;
  --icon: #171717;
  --brand: #8848F9;
  --brand-tint: #F1E4FB;
  --brand-track: rgba(136, 72, 249, 0.2);
  --positive: #00A63E;
  --negative: #F4165F;
  --radius-control: 6px;
  --radius-card: 12px;
  --radius-pill: 999px;
  --shadow-card: 0 1px 2px -1px rgba(0, 0, 0, 0.1), 0 1px 3px 0 rgba(0, 0, 0, 0.1);
  --shadow-subtle: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
  --sidebar-w: 255px;
  --topbar-h: 64px;
  --content-w: 1664px;
  --space-1: 4px; --space-2: 8px; --space-3: 12px; --space-4: 16px; --space-6: 24px;
}
```

## 附：实测参考值速查

| 项 | 值 |
|---|---|
| 画布 | 1920 × ~993px（桌面稿） |
| 侧栏 | 255px 宽，导航项高 60px |
| 顶栏 | 64px 高，主列 1664px |
| 内容白板 | 1616px 宽，四周 24px 边距 |
| 主按钮 | 112 × 36px，圆角 6px |
| 搜索框 | 1082 × 36px，圆角 6px，1px `#E2E2E2` |
| 开关 | 32 × 18px 胶囊 |
| 头像/图标容器 | 32px 圆，`#F1E4FB` 底 |
| 表头行 | 40px 高，14px Medium |
| 卡片 | 圆角 12px，内距 24px，shadow-sm |
| 徽章 | 胶囊 ~54 × 22px，12px 字 |
| 常用间距 | 4 / 8 / 12 / 16 / 24 |
