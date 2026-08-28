import {
  App as AntApp,
  Button,
  Form,
  Input,
  InputNumber,
  Modal,
  Progress,
  Select,
  Skeleton,
  Space,
  Tag,
  Typography,
} from "antd";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import {
  useCreateProject,
  useMode,
  useProjectConfig,
  useProjects,
  useStatus,
  type ProjectSummary,
} from "../api/hooks";
import type { ProjectStatus } from "../api/types";
import { pageTitle, tokens } from "../theme";

const GENRES = [
  { value: "fantasy", label: "奇幻" },
  { value: "scifi", label: "科幻" },
  { value: "mystery", label: "悬疑" },
  { value: "romance", label: "言情" },
  { value: "historical", label: "历史" },
];

interface CreateValues {
  name: string;
  genre: string;
  targetChapters?: number;
}

/* ---------- 状态徽章（DESIGN.md · 状态徽章：紫=活跃，红=异常，浅紫=停用，灰=待定） ---------- */

type BadgeTone = "active" | "error" | "idle" | "pending";

function statusBadge(status?: ProjectStatus): { label: string; tone: BadgeTone } {
  const job = status?.job ?? null;
  if (job?.error || job?.status === "failed") return { label: "异常", tone: "error" };
  if (job?.status === "running") return { label: "进行中", tone: "active" };
  if (job?.status === "done") return { label: "已完成", tone: "active" };
  if (job) return { label: "已停止", tone: "idle" };
  if ((status?.chapters?.length ?? 0) > 0) return { label: "已暂停", tone: "idle" };
  return { label: "待处理", tone: "pending" };
}

const BADGE_STYLE: Record<BadgeTone, React.CSSProperties> = {
  active: { background: tokens.brand, color: "#FFFFFF", borderColor: "transparent" },
  error: { background: tokens.negative, color: "#FFFFFF", borderColor: "transparent" },
  idle: { background: tokens.brandTint, color: tokens.graphite, borderColor: "transparent" },
  pending: { background: tokens.surface, color: tokens.graphite },
};

/** 下一步引导文案：按项目所处阶段给出真实语义的提示。 */
function nextStepHint(status?: ProjectStatus): string {
  if (!status) return "加载中…";
  if (status.job?.status === "running") return "任务运行中，可进入查看实时进度";
  if (!status.has_concept) return "从一句创意开始";
  if ((status.chapters?.length ?? 0) === 0) return "设定就绪，可开始生成章节";
  return "继续创作下一章";
}

/* ---------- 16px 线性图标（DESIGN.md：图标统一 16px 线性风格） ---------- */

function BookIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M2 2.75h4.25a1.75 1.75 0 0 1 1.75 1.75v8.75a1.31 1.31 0 0 0-1.31-1.31H2z" />
      <path d="M14 2.75H9.75A1.75 1.75 0 0 0 8 4.5v8.75a1.31 1.31 0 0 1 1.31-1.31H14z" />
    </svg>
  );
}

/* ---------- 项目卡片 ---------- */

function ProjectCard({ project, onOpen }: { project: ProjectSummary; onOpen: () => void }) {
  const { data: status } = useStatus(project.name);
  const { data: config } = useProjectConfig(project.name);
  // 容忍部分 status/config 载荷（加载中为 {}）——永不因渲染崩溃
  const chapters = status?.chapters?.length ?? 0;
  const target = config?.target_chapters ?? null;
  const openThreads = status?.open_threads ?? 0;
  const badge = statusBadge(status);
  const percent = target && target > 0 ? Math.min(100, Math.round((chapters / target) * 100)) : null;

  return (
    <div
      className="project-card"
      role="button"
      tabIndex={0}
      data-testid={`enter-${project.name}`}
      aria-label={`打开项目 ${project.name}`}
      onClick={onOpen}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onOpen();
        }
      }}
      style={{
        background: tokens.surface,
        borderRadius: 12,
        padding: 24,
        boxShadow: "var(--shadow-card)",
        cursor: "pointer",
        display: "flex",
        flexDirection: "column",
        gap: 16,
      }}
    >
      {/* 头部：头像 + 名称 + 状态徽章 */}
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <div
          aria-hidden="true"
          style={{
            width: 32,
            height: 32,
            borderRadius: "50%",
            background: tokens.brandTint,
            color: tokens.brand,
            fontWeight: 600,
            fontSize: 14,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexShrink: 0,
          }}
        >
          {project.name.slice(0, 1).toUpperCase()}
        </div>
        <Typography.Text
          strong
          ellipsis
          style={{ flex: 1, fontSize: 16, fontWeight: 600, color: tokens.ink }}
        >
          {project.name}
        </Typography.Text>
        <Tag style={BADGE_STYLE[badge.tone]}>{badge.label}</Tag>
      </div>

      {/* 进度：目标章数已知时显示进度条 + 等宽百分比 */}
      {percent != null ? (
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <Progress percent={percent} showInfo={false} style={{ flex: 1, margin: 0 }} />
          <span className="tnum" style={{ fontSize: 12, color: tokens.steel, flexShrink: 0 }}>
            {percent}%
          </span>
        </div>
      ) : null}

      {/* 计量行：等宽数字 */}
      <div
        className="tnum"
        style={{ fontSize: 12, color: tokens.steel, display: "flex", gap: 16 }}
      >
        <span>
          章节 {chapters}
          {target ? ` / ${target}` : ""}
        </span>
        <span>伏笔未闭合 {openThreads}</span>
      </div>

      {/* 底部：阶段引导 + 迷你胶囊动作（卡片本身可点，胶囊仅为视觉锚点） */}
      <div
        style={{
          borderTop: `1px solid ${tokens.line}`,
          paddingTop: 16,
          marginTop: "auto",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 8,
        }}
      >
        <Typography.Text ellipsis style={{ fontSize: 12, color: tokens.steel }}>
          {nextStepHint(status)}
        </Typography.Text>
        <span
          aria-hidden="true"
          style={{
            flexShrink: 0,
            borderRadius: 999,
            padding: "4px 12px",
            fontSize: 12,
            fontWeight: 500,
            background: tokens.brandTint,
            color: tokens.brand,
          }}
        >
          进入控制台
        </span>
      </div>
    </div>
  );
}

/** 加载骨架：灰色块 + 12px 圆角（DESIGN.md · 动效与交互），不用圆形 spinner。 */
function CardSkeleton() {
  return (
    <div
      aria-hidden="true"
      style={{
        background: tokens.surface,
        borderRadius: 12,
        padding: 24,
        boxShadow: "var(--shadow-card)",
      }}
    >
      <Skeleton avatar active title paragraph={{ rows: 2 }} />
    </div>
  );
}

/** Task 9: project home — 富项目卡片网格（进度、状态徽章、阶段引导）+ 创建弹窗。 */
export default function Projects() {
  const navigate = useNavigate();
  const { data: projects = [], isFetched } = useProjects();
  const { data: mode } = useMode();
  const create = useCreateProject();
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm<CreateValues>();
  const { message } = AntApp.useApp();

  async function submit(values: CreateValues) {
    try {
      await create.mutateAsync({
        name: values.name,
        genre: values.genre,
        // undefined is dropped by JSON.stringify → short-form projects stay clean
        target_chapters: values.targetChapters || undefined,
      });
      message.success(`项目 ${values.name} 已创建`);
      setOpen(false);
      form.resetFields();
    } catch (e) {
      if (e instanceof ApiError && e.status === 409)
        message.error(`创建失败（冲突）：${e.message}`);
      else message.error(String(e instanceof Error ? e.message : e));
    }
  }

  return (
    <div data-testid="page-projects" style={{ maxWidth: 1440, margin: "0 auto" }}>
      {/* 页头：标题 + 副标题居左，唯一主按钮居右（DESIGN.md · Layout 工具条） */}
      <header
        style={{
          display: "flex",
          alignItems: "flex-end",
          justifyContent: "space-between",
          gap: 16,
          marginBottom: 24,
        }}
      >
        <div>
          <Space wrap size={12} align="center" style={{ marginBottom: 4 }}>
            <Typography.Title level={4} style={{ ...pageTitle, marginBottom: 0 }}>
              项目
            </Typography.Title>
            {mode ? (
              <Tag color={mode.live ? "success" : "default"}>
                {mode.live ? "真实模型模式" : "演示模式"}
              </Tag>
            ) : null}
          </Space>
          <Typography.Text style={{ fontSize: 16, color: tokens.steel, display: "block" }}>
            全部创作项目与进度一览
          </Typography.Text>
        </div>
        <Button type="primary" data-testid="new-project" onClick={() => setOpen(true)}>
          新建项目
        </Button>
      </header>

      {isFetched && projects.length === 0 ? (
        // 空状态：一句话说明 + 一个主操作，配 16px 线性图标（不用插画堆砌）
        <div
          style={{
            background: tokens.surface,
            borderRadius: 12,
            padding: 48,
            boxShadow: "var(--shadow-card)",
            display: "flex",
            alignItems: "center",
            gap: 16,
          }}
        >
          <div
            aria-hidden="true"
            style={{
              width: 32,
              height: 32,
              borderRadius: "50%",
              background: tokens.brandTint,
              color: tokens.brand,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              flexShrink: 0,
            }}
          >
            <BookIcon />
          </div>
          <div style={{ flex: 1 }}>
            <Typography.Text strong style={{ display: "block", color: tokens.ink }}>
              还没有项目
            </Typography.Text>
            <Typography.Text style={{ fontSize: 12, color: tokens.steel }}>
              新建一个项目，从一句创意开始你的小说
            </Typography.Text>
          </div>
          <Button type="primary" onClick={() => setOpen(true)}>
            创建第一个项目
          </Button>
        </div>
      ) : (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))",
            gap: 24,
          }}
        >
          {!isFetched
            ? [0, 1, 2].map((i) => <CardSkeleton key={i} />)
            : projects.map((proj) => (
                <ProjectCard
                  key={proj.name}
                  project={proj}
                  onOpen={() => navigate(`/p/${proj.name}/overview`)}
                />
              ))}
        </div>
      )}

      <Modal
        open={open}
        title="新建项目"
        onCancel={() => setOpen(false)}
        footer={null}
        data-testid="create-project-modal"
      >
        <Form form={form} layout="vertical" initialValues={{ genre: "fantasy" }} onFinish={submit}>
          <Form.Item
            name="name"
            label="项目名"
            rules={[
              { required: true, message: "请输入项目名" },
              { max: 64, message: "项目名不超过 64 个字符" },
            ]}
          >
            <Input data-testid="project-name-input" placeholder="例如：clockwork-city" />
          </Form.Item>
          <Form.Item name="genre" label="类型" rules={[{ required: true, message: "请选择类型" }]}>
            <Select options={GENRES} />
          </Form.Item>
          <Form.Item
            name="targetChapters"
            label="计划全书章数"
            extra="长篇小说请填写（如 660）：启用两段式大纲——先出全书卷骨架，写作时逐卷细化。留空为短篇一次性大纲。"
          >
            <InputNumber
              min={1}
              max={5000}
              style={{ width: "100%" }}
              data-testid="project-target-input"
              placeholder="留空 = 短篇"
            />
          </Form.Item>
          <Space style={{ display: "flex", justifyContent: "flex-end", width: "100%" }}>
            <Button onClick={() => setOpen(false)}>取消</Button>
            <Button
              type="primary"
              htmlType="submit"
              data-testid="create-submit"
              loading={create.isPending}
            >
              创建
            </Button>
          </Space>
        </Form>
      </Modal>
    </div>
  );
}
