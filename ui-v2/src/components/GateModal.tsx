import { App as AntApp, Alert, Button, Input, List, Modal, Space, Typography } from "antd";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useEvents } from "../stores/events";
import { useResolveGate } from "../api/hooks";
import { GATE_LABELS, SETUP_STAGE_NAMES } from "../constants";

/** Ensure JSON artifacts always display pretty, whatever the wire format. */
function prettyArtifact(raw: string): string {
  const text = raw.trim();
  if (!text.startsWith("{") && !text.startsWith("[")) return raw;
  try {
    return JSON.stringify(JSON.parse(text), null, 2);
  } catch {
    return raw;
  }
}

/** R4: global approval modal. Setup and arc_detail gates carry a feedback box;
 * the force-pass gate requires an explicit second confirmation step. The X
 * button only DISMISSES the modal — the job keeps waiting server-side and
 * the JobStrip offers「打开审批」to bring it back. */
export default function GateModal({ project }: { project: string }) {
  const gate = useEvents((s) => s.gate);
  const dismissed = useEvents((s) => s.gateDismissed);
  const dismissGate = useEvents((s) => s.dismissGate);
  const feedbackHistory = useEvents((s) => s.feedbackHistory);
  const pushFeedback = useEvents((s) => s.pushFeedback);
  const resolve = useResolveGate();
  const [feedback, setFeedback] = useState("");
  const [confirmForce, setConfirmForce] = useState(false);
  const openerRef = useRef<HTMLElement | null>(null);
  const { message } = AntApp.useApp();

  useEffect(() => {
    if (gate) {
      openerRef.current = document.activeElement as HTMLElement | null;
      setFeedback("");
      setConfirmForce(false);
    } else if (openerRef.current) {
      // R6: return focus to the element that had it when the modal opened
      openerRef.current.focus();
      openerRef.current = null;
    }
  }, [gate]);

  if (!gate || dismissed || gate.label.startsWith("bible:") ||
      gate.label.startsWith("rewrite:"))
    return null;
  const isSetup = gate.label.startsWith("setup:");
  const isArcDetail = gate.label === "arc_detail";
  const isArcCast = gate.label === "arc_cast";
  const isForce = gate.label === "chapter_review_failed";
  const title = isSetup
    ? `设定阶段：${SETUP_STAGE_NAMES[gate.label.slice(6)] ?? gate.label.slice(6)} — 通过还是修改？`
    : (GATE_LABELS[gate.label] ?? gate.label);

  async function submit(approve: boolean, fb = "") {
    if (!approve && isSetup && !fb.trim()) {
      message.warning("请填写修改意见，或点击「通过」");
      return;
    }
    if (approve && isForce && !confirmForce) {
      setConfirmForce(true);
      return;
    }
    try {
      await resolve.mutateAsync({ id: gate!.id, approve, feedback: fb });
      // N1: only record history after a successful POST — a failed resolve
      // must not leave phantom/duplicated feedback entries behind.
      if (!approve && fb.trim()) pushFeedback(fb.trim());
    } catch (e) {
      message.error(String(e));
    }
  }

  return (
    <Modal
      open
      title={title}
      closable
      maskClosable={false}
      onCancel={() => dismissGate()}
      footer={null}
      width={720}
      data-testid="gate-modal"
      aria-live="polite"
    >
      {gate.label === "chapter" ? (
        <Typography.Paragraph data-testid="gate-artifact">
          第 <strong>{gate.artifact.trim() || "?"}</strong> 章生成完毕并通过评分。继续写作下一章？（
          <Link to={`/p/${project}/reader?chapter=${gate.artifact.trim()}`}>查看本章</Link>）
        </Typography.Paragraph>
      ) : gate.artifact ? (
        <pre data-testid="gate-artifact" style={{ whiteSpace: "pre-wrap", maxHeight: "60vh", overflow: "auto" }}>
          {prettyArtifact(gate.artifact)}
        </pre>
      ) : (
        <Typography.Text type="secondary">（产物内容不可用——重连恢复的审批）</Typography.Text>
      )}
      {(isSetup || isArcDetail || isArcCast) && (
        <>
          {feedbackHistory.length > 0 && (
            <List
              size="small"
              header={
                <Typography.Text type="secondary">本阶段已提交的反馈</Typography.Text>
              }
              dataSource={feedbackHistory}
              renderItem={(item) => <List.Item style={{ padding: "4px 0" }}>{item}</List.Item>}
            />
          )}
          <Input.TextArea
            data-testid="gate-feedback"
            rows={3}
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            placeholder={
              isArcDetail
                ? "修改意见（如「本卷太短，按骨架章数细化」），系统会带着意见重新细化该卷；留空拒绝则骨架回到队列…"
                : isArcCast
                  ? "修改意见（如「反派动机与地窟旧怨挂钩」），系统会带着意见重新拟阵容；留空拒绝 = 本卷不新增…"
                  : "修改意见（自然语言），系统会带着意见重新生成该阶段…"
            }
          />
        </>
      )}
      {isForce && confirmForce && (
        <Alert
          type="warning"
          showIcon
          style={{ marginTop: 8 }}
          message="强行放行不可撤销：该章将以未达标状态保存。确认放行？"
        />
      )}
      <Space style={{ marginTop: 12 }}>
        <Button type="primary" data-testid="gate-approve" onClick={() => submit(true)}>
          {isForce && confirmForce ? "确认强行放行" : "通过"}
        </Button>
        <Button
          data-testid="gate-reject"
          danger={isForce && confirmForce}
          onClick={() => submit(false, feedback)}
        >
          {isSetup
            ? "带反馈重生成"
            : isArcDetail
              ? "带反馈重细化"
              : isArcCast
                ? "带反馈重拟"
                : isForce
                  ? "跳过本章（本章将不保存）"
                  : "拒绝"}
        </Button>
      </Space>
    </Modal>
  );
}
