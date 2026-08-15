import { App as AntApp, Alert, Button, Card, Input, Space, Steps, Typography } from "antd";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { useMode, usePremise, useSetup, useStatus } from "../api/hooks";
import { useEvents } from "../stores/events";
import { SETUP_STAGE_NAMES } from "../constants";
import { ArtifactView } from "../components/ArtifactView";

/** Task 6: R1 Step 0 (premise) + R5 structured stage artifacts.
 * Per-stage approval lives in the global GateModal — this page only reflects
 * progress (Steps + latest artifact) and starts the two jobs. */
export default function Setup() {
  const { name = "" } = useParams();
  const { data: status } = useStatus(name);
  const { data: mode } = useMode();
  const job = useEvents((s) => s.job);
  const setupArtifact = useEvents((s) => s.setupArtifact);
  const premise = usePremise(name);
  const setup = useSetup(name);
  const [text, setText] = useState("");
  const { message } = AntApp.useApp();

  const hasConcept = !!status?.has_concept;
  const hasWorld = !!status?.has_world;
  const hasOutline = !!status?.has_outline;
  // /status has no has_characters flag: characters are always approved before
  // the outline stage runs, so outline presence is the terminal proxy — while
  // world is done but the outline is absent, the 人物 step stays "process"
  // (indeterminate: characters may be done or awaiting their gate).
  const hasCharacters = hasOutline;

  const done = [hasConcept, hasConcept, hasWorld, hasCharacters, hasOutline];
  const current = done.includes(false) ? done.indexOf(false) : done.length - 1;
  const items = ["创意", "概念", "世界观", "人物", "大纲"].map((title, i) => ({
    title,
    status: done[i]
      ? ("finish" as const)
      : i === current
        ? ("process" as const)
        : ("wait" as const),
  }));

  async function generateConcept() {
    if (!text.trim()) {
      message.warning("请先输入一句创意");
      return;
    }
    try {
      await premise.mutateAsync({ text: text.trim() });
      // Concept lands via SSE premise_done → status invalidation (events hook)
      message.info("概念生成中…");
    } catch (e) {
      message.error(String(e instanceof Error ? e.message : e));
    }
  }

  async function startSetup() {
    try {
      await setup.mutateAsync({ premise: "" });
      message.info("分阶段设定开始——每个阶段的审批弹窗会依次出现");
    } catch (e) {
      message.error(String(e instanceof Error ? e.message : e));
    }
  }

  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }} data-testid="page-setup">
      <Typography.Title level={4} style={{ margin: 0 }}>
        分阶段设定
      </Typography.Title>
      {/* R6: honest demo notice — persistent while on the page */}
      {mode && !mode.live && (
        <Alert
          type="info"
          showIcon
          data-testid="demo-notice"
          message="演示模式：反馈不会改变生成内容"
        />
      )}
      <Steps items={items} />
      {!hasConcept && !setupArtifact && (
        <Typography.Paragraph type="secondary">
          从一句创意开始，逐步确认概念、世界观、人物与大纲
        </Typography.Paragraph>
      )}
      <Card size="small" title="第 0 步 · 创意">
        {hasConcept ? (
          <Typography.Text type="success">概念已生成，可直接开始分阶段设定</Typography.Text>
        ) : (
          <div>
            <Input.TextArea
              data-testid="premise-input"
              rows={2}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="一句话创意，例如：一个能偷走时间的小偷…"
            />
            <Button
              type="primary"
              style={{ marginTop: 8 }}
              loading={premise.isPending}
              onClick={generateConcept}
            >
              生成概念
            </Button>
          </div>
        )}
      </Card>
      <Card size="small" title="第 1-4 步 · 概念 / 世界观 / 人物 / 大纲">
        <Space direction="vertical">
          <Button
            type="primary"
            data-testid="start-setup"
            disabled={!hasConcept || !!job}
            loading={setup.isPending}
            onClick={startSetup}
          >
            开始分阶段设定
          </Button>
          <Typography.Text type="secondary">
            {job
              ? "任务进行中——每个阶段的产物会出现在审批弹窗中"
              : !hasConcept
                ? "请先在第 0 步生成概念"
                : "依次生成各阶段产物，并在弹窗中通过或带反馈重生成"}
          </Typography.Text>
        </Space>
      </Card>
      {setupArtifact && (
        <ArtifactView
          raw={setupArtifact.artifact}
          title={`最新产物 · ${SETUP_STAGE_NAMES[setupArtifact.stage] ?? setupArtifact.stage}（第 ${setupArtifact.attempt} 次生成）`}
        />
      )}
      <Typography.Text type="secondary">项目：{name}</Typography.Text>
    </Space>
  );
}
