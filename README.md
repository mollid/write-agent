# 多智能体小说生成系统

这是一个命令行小说生成工具。它使用固定的多智能体工作流完成故事设定、世界观、角色、大纲、逐章写作、连续性检查与质量评分，并维护故事圣经、向量记忆和章节工作记忆。

当前版本是 CLI 工具，支持两种运行方式：

- **演示模式**：默认模式，使用内置确定性示例响应，不请求任何模型服务，适合熟悉流程和验证安装。
- **真实模型模式**：设置 `NOVEL_LIVE=1` 后通过 LiteLLM 调用 `project.config.yaml` 中配置的模型，适合实际生成内容。

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
write-chapter  生成接下来的 N 个章节
threads        查看未闭合的伏笔/线索
export         合并章节并导出 Markdown 小说
```

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

### 3. 生成章节

`write-chapter N` 会执行完整管线：补全世界观、角色和大纲，组装记忆上下文，生成下一章，提取状态与事件，检查连续性，并使用评分智能体决定是否重写或升级处理。

```bash
# 生成接下来的 3 章
uv run novel write-chapter 3

# 或指定项目路径
uv run novel write-chapter 1 --project ./my-novel
```

章节按三位数字递增保存为 `chapters/001.md`、`chapters/002.md` 等。再次执行命令不会覆盖已有章节，而是从最后一个章节号继续：

```bash
# 已有 001.md 到 003.md 时，以下命令会生成 004.md 和 005.md
uv run novel write-chapter 2
```

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

LiteLLM 会读取服务商常用环境变量。以下是常见示例，实际变量以你所选服务商和 LiteLLM 文档为准：

```bash
# 智谱
export ZHIPUAI_API_KEY="your-api-key"

# DeepSeek
export DEEPSEEK_API_KEY="your-api-key"

# OpenAI
export OPENAI_API_KEY="your-api-key"

# Anthropic
export ANTHROPIC_API_KEY="your-api-key"
```

不要将 API Key 写入 `project.config.yaml` 或提交到版本控制系统。

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
| `models.default` | 未单独指定模型的智能体的默认配置。 |
| `thresholds.score_min` | 每个评分维度的最低通过分数，默认 `80`。 |
| `thresholds.max_retries` | 未通过评分时的最大定向重写次数，默认 `3`。 |
| `generation.context_token_budget` | 每章工作记忆的上下文 Token 预算，默认 `24000`。 |
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
| Outliner | 将故事拆分为篇章、章节和情节节拍。 |
| Writer | 基于当前章节计划和工作记忆生成正文。 |
| Continuity | 检查角色状态、时间线、地点和因果一致性。 |
| Scorer | 根据产物类型的评分量表评估质量，并触发定向重写。 |
| Editor | 对章节进行最后编辑。 |

单次评分中任一维度低于 `score_min` 时，系统会按批评意见进行定向重写；超过 `max_retries` 后会进入升级处理，而不是无限重试。

## 常用命令速查

```bash
# 安装依赖
uv sync

# 查看帮助
uv run novel --help
uv run novel write-chapter --help

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

- 是否在该终端设置了服务商所需的 API Key。
- `NOVEL_LIVE=1` 是否加在要调用模型的命令前。
- `project.config.yaml` 中的 `provider` 和 `model` 是否为 LiteLLM 支持的有效组合。
- 服务商账户是否具有目标模型的访问权限与足够额度。

### 章节没有从预期位置继续

续写仅识别 `chapters/` 下命名为 `001.md`、`002.md` 这类三位数字的章节文件。不要手动修改章节编号格式；需要重新开始时，请创建新项目目录。
