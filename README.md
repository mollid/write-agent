# 多智能体小说生成系统

这是一个命令行小说生成工具。它使用固定的多智能体工作流完成故事设定、世界观、角色、大纲、逐章写作、连续性检查与质量评分，并维护故事圣经、向量记忆和章节工作记忆。

当前版本是 CLI 工具，支持两种运行方式：

- **演示模式**：默认模式，使用内置确定性示例响应，不请求任何模型服务，适合熟悉流程和验证安装。
- **真实模型模式**：设置 `NOVEL_LIVE=1` 后通过 LiteLLM 调用 `project.config.yaml` 中配置的模型，适合实际生成内容。

主要特性：

- **中英文开关**：`project.config.yaml` 的 `language: zh|en` 在真实模型模式下让所有 9 个智能体统一用一种语言输出，无需每次创意里加提示词。
- **混用多家模型**：每个智能体可各自指定 `api_base` + `api_key`，在同一项目里混用 deepseek、agnes.ai、哈基米API站、ollama 等任意 OpenAI 兼容端点。`project.config.yaml` 默认被 git 忽略，可安全存放 key。详见[配置真实模型](#配置真实模型)。

## 环境要求

- Python 3.11 或更高版本
- [uv](https://docs.astral.sh/uv/)
- 真实模型模式还需要对应模型服务商的 API Key

确认环境：

```bash
python --version
uv --version
```

## 安装与启动

在仓库根目录安装项目和开发依赖：

```bash
uv sync
```

所有命令均从仓库根目录执行，并通过 `uv run novel` 启动。可先查看完整帮助：

```bash
uv run novel --help
```

可用子命令：

```text
init           创建小说项目目录
premise        根据一句创意生成并保存故事概念
setup          标准模式：分阶段生成并确认设定（概念/世界观/人物/大纲）
write-chapter  生成接下来的 N 个章节
threads        查看未闭合的伏笔/线索
export         合并章节并导出 Markdown 小说
```

## 图形界面（Web GUI）

除了命令行，还可以用浏览器图形界面完成整个流程（新建项目 → 生成概念 → 生成章节（实时进度 + 审批）→ 阅读/导出）：

```bash
uv run novel-ui
```

启动后会自动打开浏览器访问 `http://127.0.0.1:8765`（可用 `--no-browser` 关闭自动打开）。界面是新版的 React 控制台 SPA（`ui-v2/`，构建产物由服务端直接伺服）。常用参数：

```bash
uv run novel-ui --root ./my-novels   # 指定项目所在根目录（默认当前目录）
uv run novel-ui --port 9000          # 指定端口
```

### 前端开发模式（两进程）

修改 `ui-v2/` 前端代码时不需要每次重新构建，用两个进程进行开发：

```bash
# 终端 1：后端 API（8765 端口）
uv run novel-ui --no-browser

# 终端 2：Vite 开发服务器（5173 端口，已配置将 /api 代理到 8765）
cd ui-v2 && npm run dev
```

然后浏览器访问 `http://127.0.0.1:5173`（享受热更新）。前端测试与类型检查：`cd ui-v2 && npm run test && npm run typecheck`。

### 构建与发布

`uv run novel-ui` 伺服的是 `ui-v2/dist/` 里的构建产物（该目录不入库），发布/演示前请先构建：

```bash
cd ui-v2 && npm install && npm run build
```

若 `ui-v2/dist/` 不存在，`/` 会自动退回旧版界面。对等功能验收完成之前的过渡期内，旧版原生 JS 界面仍可通过 `/legacy` 访问（`http://127.0.0.1:8765/legacy/`）。

说明：

- **模式与 CLI 一致**：默认演示模式；在启动前设置 `NOVEL_LIVE=1` 即为真实模型模式（界面右上角有模式标识），模型配置同样读自各项目的 `project.config.yaml`。
- **实时进度**：章节生成的各阶段（世界观、大纲、写作、评分、连续性检查等）通过 SSE 推送到浏览器，含进度条和事件日志。
- **评分历史留档**：每次质量评分（含重写前后的各次尝试、维度得分与批评意见）追加写入项目内 `.meta/reviews/reviews.jsonl`，界面「评分历史」面板按章展开查看。
- **审批门控**：真实模式下大纲与章节阶段的人工审核会以卡片形式弹出，点击「批准/拒绝」即可，无需命令行交互。
- **任务管理**：每个项目同一时间只能有一个任务在运行，可随时取消；取消在章节边界生效。
- **分阶段设定（标准模式）**：点击「分阶段设定」，四个设定阶段（概念/世界观/人物/大纲）逐个生成并弹出审批卡片，卡片内可填写自然语言修改意见让系统重新生成，或直接通过；已通过的阶段在重跑时自动跳过。
- **设定库**：「创作 → 设定库」页面（`/p/{项目名}/bible`）集中查看与修改全部故事设定，支持六段预览、手动 JSON 编辑、对话改写与大纲追章，详见下文[设定库](#设定库)小节。
- 章节阅读、伏笔台账、导出 `novel.md` 均可在界面内完成。

### 设定库

左侧菜单「创作 → 设定库」（路径 `/p/{项目名}/bible`）是全部故事设定的工作台，分六段展示当前故事圣经：

- **概念**：一句话概念、类型、基调、主题、目标字数、读者画像。
- **世界观**：舞台设定、时代、力量体系、世界规则与约束、地点、势力。
- **人物**：角色卡（动机、角色弧光、语言样本、神态习惯），并合并展示写作过程中抽取的动态状态（当前状态、最近事件）。
- **大纲**：篇章/章节/节拍（视点角色、场景、事件、伏笔埋设与回收计划）。
- **伏笔**：伏笔台账（说明、状态：待埋设/已埋设/已回收、关联章节）。
- **事件**：按时间线排列的事件因果日志（系统在写作过程中自动维护，只读）。

#### 手动编辑 JSON

除「事件」由系统自动维护外，每个分段都有「编辑 JSON」按钮，可直接修改该段完整 JSON 后保存（PUT 语义，整体替换）：

- 结构不合法（字段缺失、类型错误）时返回 `422` 并提示具体字段错误，保存不会生效。
- 该项目有任务运行中时拒绝保存（`409`），等任务结束后重试即可。

#### 对话改写

「对话改写」用自然语言指令让 AI 修改设定：选择分段（人物段还可再选中单个角色，只改这一个角色卡），输入修改要求（如「让主角的动机更自私一点」），系统给出修改建议并以逐行差异（diff）展示；确认后点「应用」生效，不满意点「放弃」，或在审批卡片里填写反馈让 AI 重改——最多 3 轮反馈。支持的分段：概念/世界观/人物/伏笔（大纲请用「大纲追章」）。

- **演示模式**下改写不改变内容（原样回显），但 diff、审批、应用的完整流程可以走通。
- **真实模式**使用 `setting_editor` 智能体槽位，可在 `project.config.yaml` 的 `models` 里像其他智能体一样单独配置；未配置时自动回退 `default`，无需额外改动。

#### 大纲追章

大纲章节不够写时（`write-chapter` 会警告 `outline exhausted`），在设定库「大纲」段使用「大纲追章」：输入要追加的章节数（1–50），系统生成追章建议并以 diff 展示，批准后并入大纲；之后再次运行 `write-chapter`（或界面「生成章节」）即可继续写新追加的章节，`outline exhausted` 警告随之消除。演示模式下会确定性地追加占位章节，流程同样可以走通。

## 快速开始：演示模式

演示模式不需要 API Key，也不会调用网络模型。以下流程会在当前目录创建 `demo-novel/`，生成故事设定与三章示例内容，并导出一本 Markdown 小说。

```bash
# 1. 创建项目
uv run novel init demo-novel --genre fantasy

# 2. 进入项目目录
cd demo-novel

# 3. 根据创意生成故事概念并保存到故事圣经
uv run novel premise "一个能偷走时间的盗贼"

# 4. 从当前进度开始生成 3 章
uv run novel write-chapter 3

# 5. 查看未闭合的伏笔和线索
uv run novel threads

# 6. 导出所有已生成章节
uv run novel export
```

完成后，合并后的小说位于 `demo-novel/novel.md`，单章文件位于 `demo-novel/chapters/`。

## 完整操作流程

### 1. 创建小说项目

`init` 会创建独立的项目目录和全部必要存储。`--genre` 可替换为任意类型，例如 `sci-fi`、`mystery`、`romance`。

```bash
uv run novel init my-novel --genre sci-fi
```

项目初始化后的目录结构：

```text
my-novel/
├── project.config.yaml       # 模型、评分门槛、上下文预算配置
├── bible/                    # 故事圣经和结构化事实
│   ├── _canonical.json       # 权威故事数据
│   ├── foreshadowing.json    # 伏笔状态
│   └── events.jsonl          # 事件因果日志
├── chapters/                 # 已生成章节，如 001.md
│   └── _summaries/           # 章节摘要
├── memory/chroma/            # 本地向量记忆数据库
├── .meta/reviews/            # 评分与审阅记录
├── runs/                     # 运行记录预留目录
└── novel.md                  # 执行 export 后生成
```

### 2. 生成故事概念

进入项目目录后运行 `premise`。它会调用策略智能体，将一句创意扩展为题材、语调、主题、目标字数和受众等结构化概念，并保存到 `bible/_canonical.json`。

```bash
cd my-novel
uv run novel premise "火星殖民地的档案员发现每次日落都会少一名居民"
```

也可以不切换目录，通过全局参数指定项目路径：

```bash
uv run novel premise "火星殖民地的档案员发现每次日落都会少一名居民" --project ./my-novel
```

### 2b. 标准模式：分阶段设定（可选）

如果不习惯「一句话全自动」，可以用 `setup` 命令分阶段生成并逐个确认设定：

```bash
uv run novel setup --premise "一个能偷走时间的盗贼"
```

省略 `--premise` 时：项目里已有保存的概念则使用其 logline，否则会提示输入创意。

流程按顺序走 概念 → 世界观 → 人物 → 大纲 四个阶段。每个阶段先展示生成结果，然后提供三个选项：

- **通过（a）**：接受当前结果，进入下一阶段。
- **反馈（f）**：用自然语言描述不满意的地方（如「主角动机太单薄」），系统会带着你的反馈重新生成该阶段。反馈逐条累积——每轮重新生成都会带上全部历史反馈，直到你满意为止。
- **退出（q）**：中止设定。已通过的阶段会被保留，中途退出后重跑 `setup` 会跳过已通过的阶段，从断点继续。

设定全部通过后，`write-chapter` 会自动跳过设定阶段、直接开始写章——标准模式与「一句话全自动」模式并存，无需任何配置开关。

演示模式下整个流程同样可以走通，但反馈不会改变生成内容（使用内置确定性响应）。

> **注意**：`setup` 会跳过所有已通过的阶段。因此对一个已经完成设定（或已生成章节）的项目重跑 `setup` 不会改变任何东西——当前版本没有提供重做单个阶段的入口；如需重做设定，需要手动删除或编辑 `bible/` 下对应的设定数据（高级操作，可能影响后续章节与既有章节的一致性）。

### 3. 生成章节

`write-chapter N` 会执行完整管线：补全世界观、角色和大纲，组装记忆上下文，生成下一章，提取状态与事件，检查连续性，并使用评分智能体决定是否重写或升级处理。

```bash
# 生成接下来的 3 章
uv run novel write-chapter 3

# 或指定项目路径
uv run novel write-chapter 1 --project ./my-novel
```

章节按三位数字递增保存为 `chapters/001.md`、`chapters/002.md` 等。再次执行命令时已完成的章节会被自动跳过，从第一个缺失或未完成的章节继续：

```bash
# 已有 001.md 到 003.md 时，以下命令会生成 004.md 和 005.md
uv run novel write-chapter 2
```

**中断后续跑**：`write-chapter` 是幂等的——章节文件完整（长度达到 `generation.min_chapter_chars`）且评分留档（`.meta/reviews/reviews.jsonl`）中有通过记录的章节会被自动跳过，空文件或过短的半成品章节会被重写。生成中断后（崩溃、取消、断网）直接重跑同一条命令即可从断点继续，CLI 会打印 `Resuming from chapter N`；CLI 与图形界面的续跑行为完全一致。评分留档功能之前的旧项目没有 `reviews.jsonl`，此时只按文件长度判定，不会被全量重写。

章节采用原子写入（先写 `chapters/.NNN.md.tmp` 临时文件再改名），中断不会留下半截的 `001.md`；极少数情况下磁盘上可能残留 `.001.md.tmp` 之类的临时文件，下次运行时会自动清理，不影响章节识别与导出。

### 4. 查看故事线索

使用 `threads` 查看尚未收束的伏笔和线索：

```bash
uv run novel threads
```

输出包含线索 ID、说明和状态。状态通常为 `open`、`planted` 或 `paid_off`。

### 5. 导出小说

当前仅支持 Markdown 导出。`export` 会按章节编号顺序合并 `chapters/` 下的内容，输出 `novel.md`：

```bash
uv run novel export
```

`--format` 的默认值为 `md`；当前版本无 DOCX 或 EPUB 导出：

```bash
uv run novel export --format md
```

## 配置真实模型

默认演示模式使用内置响应。实际生成前，需要配置模型并设置 `NOVEL_LIVE=1`。

### 1. 设置 API Key

`project.config.yaml` 已被本仓库默认 git 忽略，因此可以**直接在配置里写明文 `api_key`**（见 [配置字段说明](#配置字段说明) 中的 `api_base` / `api_key`），尤其适合接入 agnes、哈基米等 OpenAI 兼容端点。

除配置文件外，LiteLLM 也读取服务商常用环境变量作为另一条途径（无 `api_key` 字段时由 litellm 自动使用，例如 `provider: deepseek` 会读取 `DEEPSEEK_API_KEY`）。常见示例：

```bash
# 智谱（litellm 读取 ZHIPUAI_API_KEY）
export ZHIPUAI_API_KEY="your-api-key"

# DeepSeek（litellm 读取 DEEPSEEK_API_KEY）
export DEEPSEEK_API_KEY="your-api-key"

# OpenAI 官方（litellm 读取 OPENAI_API_KEY；若设了 api_base 则指向兼容端点而非官方）
export OPENAI_API_KEY="your-api-key"

# Anthropic（litellm 读取 ANTHROPIC_API_KEY）
export ANTHROPIC_API_KEY="your-api-key"
```

> 安全提示：即便已忽略该配置文件，仍请确认**项目目录不在某个会 `git add -A` 的父仓库里**，并避免把含 key 的文件复制到会被提交的位置。

### 2. 编辑项目配置

打开项目根目录的 `project.config.yaml`。新项目的初始配置如下：

```yaml
models:
  strategist: { provider: zhipu, model: glm-4-plus }
  writer: { provider: zhipu, model: glm-4-plus }
  scorer: { provider: deepseek, model: deepseek-chat }
thresholds:
  score_min: 80
  max_retries: 3
generation:
  human_gate_every_n_chapters: 1
  context_token_budget: 24000
```

`models` 为智能体指定 LiteLLM 的 `provider` 和 `model`。未单独配置的智能体会回退到 `default`，如果不存在 `default`，则使用 `models` 中的第一个模型。因此，建议为所有角色设置统一默认模型：

```yaml
models:
  default: { provider: openai, model: gpt-4o-mini }
  writer: { provider: openai, model: gpt-4o }
  scorer: { provider: openai, model: gpt-4o-mini }
thresholds:
  score_min: 80
  max_retries: 3
generation:
  human_gate_every_n_chapters: 1
  context_token_budget: 24000
```

配置字段说明：

| 字段 | 作用 |
| --- | --- |
| `models.<agent>.provider` | LiteLLM 服务商名称，如 `openai`、`anthropic`、`deepseek`、`zhipu`。OpenAI 兼容接口统一填 `openai` 并配合 `api_base`。 |
| `models.<agent>.model` | 服务商的实际模型名称。 |
| `models.<agent>.api_base` | （可选）OpenAI 兼容接口的 base URL，用于接入 agnes、哈基米API站、ollama 等任意兼容端点。也写作 `base_url`。 |
| `models.<agent>.api_key` | （可选）该模型的 API key。**写入后请勿把 `project.config.yaml` 提交进 git**（本仓库已默认忽略它）。 |
| `models.<agent>.timeout` | （可选）单次调用超时秒数。本地大模型推理慢时建议设大（如 `300`）；省略则用 litellm 默认。 |
| `models.default` | 未单独指定模型的智能体的默认配置。 |
| `thresholds.score_min` | 每个评分维度的最低通过分数，默认 `80`。 |
| `thresholds.max_retries` | 未通过评分时的最大定向重写次数，默认 `3`。 |
| `generation.context_token_budget` | 每章工作记忆的上下文 Token 预算，默认 `24000`。 |
| `generation.min_chapter_chars` | 断点续跑时判定章节「已完成」的最小字符数，默认 `50`（必须低于演示模式章节长度 62）。真实模型项目建议设为实际章节长度的下限（如 `2000`）；设得过大会导致同一章每次续跑都被重写。 |
| `generation.human_gate_every_n_chapters` | 人工审核频率配置；当前实现会在真实模式的大纲与每章阶段请求批准。 |
| `language` | 输出语言开关，`en`（默认）或 `zh`。真实模式下所有智能体按此语言生成自然语言文本。 |

#### 混用多家 OpenAI 兼容模型

每个智能体可各自指定 `api_base` + `api_key`，从而在同一项目里混用 deepseek、agnes、哈基米API站等。`project.config.yaml` 已被 git 忽略，可安全存放 key：

```yaml
models:
  default: { provider: deepseek, model: deepseek-v4-pro }                                                       # deepseek 官方（litellm 自动用 DEEPSEEK_API_KEY，无需写 api_key）
  writer:  { provider: openai,   model: gpt-5.6-terra, api_base: https://api.gemai.cc/v1,        api_key: sk-哈基米key }   # opencode 免费模型
  scorer:  { provider: openai,   model: agnes-xxx,      api_base: https://apihub.agnes-ai.com/v1, api_key: sk-agnes-key }  # agnes.ai
thresholds:
  score_min: 80
  max_retries: 2
generation:
  human_gate_every_n_chapters: 1
  context_token_budget: 24000
language: zh
```

说明：所有 OpenAI 兼容端点（含 `api_base` 的）`provider` 一律填 `openai`；未写 `api_key` 时，deepseek/anthropic 等官方 provider 由 litellm 从对应环境变量（`DEEPSEEK_API_KEY` / `ANTHROPIC_API_KEY`）读取。

#### 本地部署的模型（Ollama / vLLM / LM Studio 等）

本地部署的模型只要暴露 OpenAI 兼容接口即可接入，配置方式与[混用多家模型](#混用多家-openai-兼容模型)完全相同：`provider` 填 `openai`，`api_base` 指向本地端点。常见服务的默认 OpenAI 兼容端点：

| 服务 | 默认 OpenAI 兼容 endpoint |
| --- | --- |
| Ollama | `http://localhost:11434/v1` |
| vLLM | `http://localhost:8000/v1` |
| LM Studio | `http://localhost:1234/v1` |
| llama.cpp `llama-server` | `http://localhost:8080/v1` |
| 其他（SGLang / TGI / KoboldCpp 等） | 见各服务文档，OpenAI 兼容路径通常为 `/v1` |

以 Ollama 跑 `qwen2.5:14b` 为例（先 `ollama pull qwen2.5:14b` 拉模型，再 `ollama serve` 起服务）：

```yaml
models:
  default: { provider: openai, model: qwen2.5:14b, api_base: http://localhost:11434/v1, api_key: local, timeout: 300 }
  scorer:  { provider: deepseek, model: deepseek-v4-pro }       # 评分可继续用云，更稳
thresholds:
  score_min: 80
  max_retries: 2
generation:
  human_gate_every_n_chapters: 1
  context_token_budget: 24000
language: zh
```

要点：

- **`api_key` 填占位字符串**：本地服务通常不验证 key，但 OpenAI 客户端要求该字段非空，填任意值（如 `local`）即可。
- **`model` 用本地实际名**：Ollama 取 `ollama list` 里的 tag（如 `qwen2.5:14b`）；vLLM 取启动 `--model` 的名字；LM Studio 取其模型标识。
- **`timeout` 给本地慢推理**：大模型生成可能久，建议设 `timeout: 300`（秒）或更大；省略则用 litellm 默认（可能不够）。
- **可混本地与云**：例如 `writer` 用本地 14B 模型跑创作、`scorer` 用 deepseek 云做评分；`timeout` 按 agent 各自配置。
- **离线环境**：无网时 litellm 启动期会尝试拉取模型价目表并失败回退为本地副本，仅打印一条警告，不影响调用。
- 也支持 Ollama 原生协议（`provider: ollama, model: <tag>`），但需额外给 litellm 配置 ollama base，不如走 OpenAI 兼容接口统一简便，本节推荐后者。

### 3. 在真实模型模式下运行

每次要调用真实模型的命令前添加 `NOVEL_LIVE=1`：

```bash
cd my-novel
NOVEL_LIVE=1 uv run novel premise "一名法医能听见死者最后十分钟的记忆"
NOVEL_LIVE=1 uv run novel write-chapter 3
uv run novel export
```

真实模式会在需要人工审核的阶段显示结果，并提示：

```text
Approve? [a]pprove/[e]dit/[r]egen/[s]how
```

当前命令只会在输入 `a` 或直接按 Enter 时继续。其他输入会使当前审核结果不通过并中止该阶段；交互式编辑、重新生成和全文展示仍是后续扩展项。

## 模型分工与质量控制

工作流包含以下角色：

| 角色 | 职责 |
| --- | --- |
| Strategist | 将创意转换为故事概念。 |
| Worldbuilder | 创建世界规则、地点、势力和约束。 |
| Character | 创建角色、动机、角色弧光与声音特征。 |
| Outliner | 将故事拆分为篇章、章节和情节节拍，并维护伏笔台账。 |
| Writer | 基于当前章节计划和工作记忆生成正文。 |
| Continuity | 检查角色状态、时间线、地点和因果一致性。 |
| Scorer | 根据产物类型的评分量表评估质量，并触发定向重写。 |
| Editor | 对章节进行最后编辑。 |
| Extractor | 从已写章节中抽取角色状态、声音样本、神态习惯和关键事件，回写故事圣经与向量记忆，供下一章使用。 |
| Setting Editor | 在图形界面「设定库」的对话改写中，按自然语言指令改写设定段（概念/世界观/人物/伏笔）。模型用 `models.setting_editor` 配置，缺省回退 `default`。 |

单次评分中任一维度低于 `score_min` 时，系统会按批评意见进行定向重写；超过 `max_retries` 后会升级给人审批而不是硬放行或无限重试。

## 常用命令速查

```bash
# 安装依赖
uv sync

# 查看帮助
uv run novel --help
uv run novel write-chapter --help

# 图形界面（浏览器）
uv run novel-ui

# 创建项目
uv run novel init my-novel --genre mystery

# 演示模式：在项目目录内运行
uv run novel premise "一句故事创意"
uv run novel write-chapter 1
uv run novel threads
uv run novel export

# 指定项目目录
uv run novel write-chapter 2 --project ./my-novel

# 真实模型模式
NOVEL_LIVE=1 uv run novel premise "一句故事创意" --project ./my-novel
NOVEL_LIVE=1 uv run novel write-chapter 2 --project ./my-novel
```

## 验证与开发

运行全部测试、格式检查和类型检查：

```bash
uv run pytest -q
uv run ruff check .
uv run mypy novel
```

测试使用 `FakeProvider`，不会发送真实模型请求或消耗 API 额度。

## 排错

### `uv: command not found`

安装 uv 后重新打开终端，或依据 [uv 安装文档](https://docs.astral.sh/uv/getting-started/installation/) 将其加入 `PATH`。

### `project.config.yaml` 找不到

需要在小说项目目录内执行命令，或使用 `--project` 指定项目目录：

```bash
uv run novel write-chapter 1 --project ./my-novel
```

### 真实模型模式调用失败

依次检查：

- 是否在该终端设置了服务商所需的 API Key（环境变量），或在 `project.config.yaml` 里写了 `api_key`。
- `NOVEL_LIVE=1` 是否加在要调用模型的命令前。
- `project.config.yaml` 中的 `provider` 和 `model` 是否为 LiteLLM 支持的有效组合。
- OpenAI 兼容端点（agnes / 哈基米 / Ollama / vLLM 等）`provider` 应填 `openai` 并配 `api_base`，`model` 用该端点上的实际模型名。
- 本地端点是否在运行、端口是否正确；`api_key` 字段非空（本地可填 `local`）。
- 服务商账户是否具有目标模型的访问权限与足够额度；本地模型是否有足够显存/是否已 `pull`。

### 章节没有从预期位置继续

续跑的起点是第一个缺失或未完成的章节：章节文件缺失、文件长度不足 `generation.min_chapter_chars`，或 `.meta/reviews/reviews.jsonl` 中有该章评分记录但无通过（`passed`）记录时，该章会被重写；之前的已完成章节全部跳过。排查建议：

- `generation.min_chapter_chars` 是否设得过大，导致本来完整的章节被判为未完成而反复重写。
- 该章文件是否为空或过短（如上次中断留下的半成品）。
- `.meta/reviews/reviews.jsonl` 中是否有该章的 `passed` 记录；评分留档功能之前的旧项目没有该文件，此时只按文件长度判定。

另外，续写仅识别 `chapters/` 下命名为 `001.md`、`002.md` 这类三位数字的章节文件。不要手动修改章节编号格式；需要重新开始时，请创建新项目目录。

续写会严格按大纲章节顺序对位：第 N 个章节文件由大纲第 N 章的节拍生成。若请求的章节数超过大纲已有的章节数，命令会给出 `outline exhausted` 警告并只写出实际可写的章节。
