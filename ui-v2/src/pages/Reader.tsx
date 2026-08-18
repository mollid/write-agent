import { Alert, App as AntApp, Button, Card, Empty, Input, Menu, Segmented, Space, Typography } from "antd";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import {
  useChapter,
  useChapterRewrite,
  useOutline,
  useResolveGate,
  useSaveChapter,
  useStatus,
} from "../api/hooks";
import { useEvents } from "../stores/events";
import { REWRITE_MODE_NAMES } from "../constants";

/** Task 8: chapter reader — left chapter list (outline titles), right prose at
 * a comfortable measure. F1: `?chapter=N` deep links from Generate preselect.
 * Below the prose: chapter rewrite (微调 / 创意重编排) with a diff proposal
 * panel approved via the rewrite:{N} gate, plus manual in-place editing. */
export default function Reader() {
  const { name = "" } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const { data: status } = useStatus(name);
  const { data: outline } = useOutline(name);
  const [selected, setSelected] = useState<number | null>(null);
  const chapter = useChapter(name, selected);
  const job = useEvents((s) => s.job);
  const proposal = useEvents((s) => s.chapterProposal);
  const rewrite = useChapterRewrite(name);
  const resolve = useResolveGate(name);
  const saveChapter = useSaveChapter(name);
  const [mode, setMode] = useState<string>("polish");
  const [instruction, setInstruction] = useState("");
  const [feedback, setFeedback] = useState("");
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const { message } = AntApp.useApp();

  const titles = useMemo(() => {
    const m = new Map<number, string>();
    for (const arc of outline?.arcs ?? [])
      for (const c of arc.chapters) m.set(c.chapter_no, c.chapter_title);
    return m;
  }, [outline]);
  const chapters = status?.chapters ?? [];

  // F1: honor the ?chapter=N deep link once, then clear it (replace, not push)
  // so the browser back button returns to the referring page, not a re-select.
  const param = searchParams.get("chapter");
  useEffect(() => {
    if (param == null) return;
    const n = Number(param);
    if (Number.isInteger(n) && n > 0) setSelected(n);
    setSearchParams({}, { replace: true });
  }, [param, setSearchParams]);

  // default to the first chapter once the list is known
  useEffect(() => {
    if (selected == null && chapters.length > 0) setSelected(chapters[0]);
  }, [selected, chapters]);

  // switching chapters abandons any in-progress manual edit (draft belongs to
  // the old chapter)
  useEffect(() => {
    setEditing(false);
  }, [selected]);

  const hasLaterChapters = selected != null && chapters.some((c) => c > selected);

  function startEditing() {
    if (chapter.data) setDraft(chapter.data.content);
    setEditing(true);
  }

  function saveEdit() {
    if (selected == null) return;
    saveChapter.mutate(
      { chapter: selected, content: draft },
      {
        onSuccess: () => {
          setEditing(false);
          message.success("已保存，旧稿已自动备份");
        },
        onError: (e) => message.error(String(e)),
      },
    );
  }

  function startRewrite() {
    if (selected == null) return;
    if (!instruction.trim()) {
      message.warning("请先填写改写指令");
      return;
    }
    setFeedback("");
    rewrite.mutate(
      { chapter: selected, mode, instruction: instruction.trim() },
      { onError: (e) => message.error(String(e)) },
    );
  }

  async function resolveProposal(approve: boolean, fb = "") {
    if (!proposal) return;
    if (!approve && !fb.trim()) {
      message.warning("请填写修改意见，或点击「应用改写」/「放弃」");
      return;
    }
    try {
      await resolve.mutateAsync({ id: proposal.gateId, approve, feedback: fb });
      if (!approve && fb.trim()) setFeedback("");
    } catch (e) {
      message.error(String(e));
    }
  }

  return (
    <div data-testid="page-reader" style={{ display: "flex", gap: 16, alignItems: "flex-start" }}>
      <Card size="small" title="章节目录" style={{ minWidth: 230 }}>
        {chapters.length === 0 ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="尚无章节">
            <Link to={`/p/${name}/generate`}>去生成</Link>
          </Empty>
        ) : (
          <Menu
            mode="inline"
            style={{ borderInlineEnd: 0 }}
            selectedKeys={selected != null ? [String(selected)] : []}
            items={chapters.map((c) => ({
              key: String(c),
              label: `${String(c).padStart(3, "0")} · ${titles.get(c) ?? "（无标题）"}`,
            }))}
            onSelect={({ key }) => setSelected(Number(key))}
          />
        )}
      </Card>
      <Space direction="vertical" size="middle" style={{ flex: 1, minWidth: 0 }}>
        <Card
          size="small"
          extra={
            !editing && chapter.data && selected != null ? (
              <Button size="small" data-testid="edit-chapter" disabled={!!job} onClick={startEditing}>
                编辑
              </Button>
            ) : undefined
          }
          title={
            selected != null
              ? `第 ${selected} 章 · ${titles.get(selected) ?? "（无标题）"}`
              : "正文"
          }
        >
          {editing ? (
            <Space direction="vertical" size="small" style={{ width: "100%" }}>
              <Input.TextArea
                data-testid="edit-area"
                rows={16}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
              />
              <Space>
                <Button
                  type="primary"
                  data-testid="edit-save"
                  loading={saveChapter.isPending}
                  disabled={!!job}
                  onClick={saveEdit}
                >
                  保存（旧稿自动备份）
                </Button>
                <Button data-testid="edit-cancel" onClick={() => setEditing(false)}>
                  取消
                </Button>
              </Space>
            </Space>
          ) : chapter.data ? (
            <Typography.Paragraph
              data-testid="reader-prose"
              style={{ maxWidth: "72ch", lineHeight: 1.8, whiteSpace: "pre-wrap", marginBottom: 0 }}
            >
              {chapter.data.content}
            </Typography.Paragraph>
          ) : chapter.isError ? (
            <Typography.Text type="danger">章节内容加载失败</Typography.Text>
          ) : selected != null ? (
            <Typography.Text type="secondary">加载中…</Typography.Text>
          ) : (
            <Typography.Text type="secondary">从左侧选择一章开始阅读</Typography.Text>
          )}
        </Card>
        {proposal && (
          <Card
            size="small"
            data-testid="rewrite-proposal"
            title={`第 ${proposal.chapter} 章改写提案${
              proposal.mode ? ` · ${REWRITE_MODE_NAMES[proposal.mode] ?? proposal.mode}` : ""
            }`}
          >
            {proposal.diff ? (
              <pre
                data-testid="rewrite-diff"
                style={{ whiteSpace: "pre-wrap", maxHeight: "50vh", overflow: "auto",
                         fontSize: 12, lineHeight: 1.6, marginTop: 0 }}
              >
                {proposal.diff}
              </pre>
            ) : (
              <Typography.Text type="secondary">
                （差异不可用——重连恢复的提案，下方为改写稿全文）
              </Typography.Text>
            )}
            <Input.TextArea
              data-testid="rewrite-feedback"
              rows={2}
              style={{ marginTop: 8 }}
              value={feedback}
              onChange={(e) => setFeedback(e.target.value)}
              placeholder="修改意见（自然语言）：不满意可带意见重新改写…"
            />
            <Space style={{ marginTop: 8 }}>
              <Button
                type="primary"
                data-testid="rewrite-approve"
                disabled={!proposal.gateId}
                onClick={() => resolveProposal(true)}
              >
                应用改写
              </Button>
              <Button
                data-testid="rewrite-reject"
                disabled={!proposal.gateId}
                onClick={() => resolveProposal(false, feedback)}
              >
                带反馈再改
              </Button>
              <Button
                data-testid="rewrite-abandon"
                disabled={!proposal.gateId}
                onClick={() => resolveProposal(false)}
              >
                放弃
              </Button>
            </Space>
          </Card>
        )}
        {chapters.length > 0 && (
          <Card size="small" title="章节改写" data-testid="rewrite-card">
            {hasLaterChapters && (
              <Alert
                type="warning"
                showIcon
                style={{ marginBottom: 8 }}
                message="本章之后已有后续章节：重写本章可能与后续内容衔接不畅"
              />
            )}
            <Space direction="vertical" size="small" style={{ width: "100%" }}>
              <Segmented
                data-testid="rewrite-mode"
                value={mode}
                onChange={(v) => setMode(v as string)}
                options={Object.entries(REWRITE_MODE_NAMES).map(([value, label]) => ({
                  value,
                  label,
                }))}
              />
              <Input.TextArea
                data-testid="rewrite-instruction"
                rows={2}
                value={instruction}
                onChange={(e) => setInstruction(e.target.value)}
                placeholder={
                  mode === "polish"
                    ? "微调指令，例如：把结尾的对白改短，语气更克制"
                    : "重编排指令，例如：把酒馆冲突提前开场，回忆改为插叙"
                }
              />
              <Button
                type="primary"
                data-testid="rewrite-start"
                disabled={selected == null || !!job}
                loading={rewrite.isPending}
                onClick={startRewrite}
              >
                开始改写
              </Button>
            </Space>
          </Card>
        )}
      </Space>
    </div>
  );
}
