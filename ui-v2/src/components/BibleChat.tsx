import { App as AntApp, Button, Input, List, Select, Space, Tag, Typography } from "antd";
import { useEffect, useState } from "react";
import { useBible, useBibleChat, useResolveGate } from "../api/hooks";
import { useEvents } from "../stores/events";
import DiffView from "./DiffView";

/** Task 9: conversational bible editor for one section. Sends an instruction
 * via POST /bible/chat, shows the pending entry (生成中), renders the SSE
 * proposal as a DiffView with 应用/放弃 (gate resolve, no feedback box —
 * re-instruct after discarding instead), and flips the history entry on
 * `bible_chat_done`. outline/events are read-only sections. */

interface ChatEntry {
  instruction: string;
  status: "pending" | "applied" | "discarded";
}

const READONLY_NOTES: Record<string, string> = {
  outline: "大纲请使用追章（在「大纲」卡片追加章节），此处为只读展示",
  events: "事件由系统自动记录（写作时由系统回写），此处为只读展示",
};

const STATUS_TAGS: Record<ChatEntry["status"], { text: string; color: string }> = {
  pending: { text: "生成中", color: "processing" },
  applied: { text: "已应用", color: "success" },
  discarded: { text: "已放弃", color: "default" },
};

export default function BibleChat({ name, section }: { name: string; section: string }) {
  const proposal = useEvents((s) => s.bibleProposal);
  const bibleChatDone = useEvents((s) => s.bibleChatDone);
  const chat = useBibleChat(name);
  const resolve = useResolveGate(name);
  const { data: bible } = useBible(name);
  const [text, setText] = useState("");
  const [history, setHistory] = useState<ChatEntry[]>([]);
  const [characterId, setCharacterId] = useState<string | undefined>();
  const { message } = AntApp.useApp();

  const readonlyNote = READONLY_NOTES[section];
  const active = proposal && proposal.section === section ? proposal : null;

  // flip the last pending entry once OUR section's bible_chat_done lands
  const done = bibleChatDone && bibleChatDone.section === section ? bibleChatDone : null;
  const doneSeq = done?.seq ?? null;
  useEffect(() => {
    if (doneSeq === null || !done) return;
    setHistory((h) => {
      const idx = h.map((e) => e.status).lastIndexOf("pending");
      if (idx === -1) return h;
      const next = [...h];
      next[idx] = { ...next[idx], status: done.applied ? "applied" : "discarded" };
      return next;
    });
  }, [doneSeq]);

  if (readonlyNote) {
    return (
      <Typography.Paragraph type="secondary" data-testid="chat-readonly-note">
        {readonlyNote}
      </Typography.Paragraph>
    );
  }

  async function send() {
    const instruction = text.trim();
    if (!instruction) return;
    try {
      await chat.mutateAsync({
        section,
        instruction,
        ...(section === "characters" && characterId ? { character_id: characterId } : {}),
      });
      setHistory((h) => [...h, { instruction, status: "pending" }]);
      setText("");
    } catch (e) {
      message.error(String(e));
    }
  }

  async function resolveProposal(approve: boolean) {
    if (!active) return;
    try {
      await resolve.mutateAsync({ id: active.gateId, approve });
    } catch (e) {
      message.error(String(e));
    }
  }

  const sendDisabled = !!active || chat.isPending || !text.trim();

  return (
    <div>
      {section === "characters" && (
        <Select
          data-testid="chat-character-select"
          allowClear
          placeholder="选择人物（可选，不选则改全部）"
          style={{ width: "100%", marginBottom: 8 }}
          value={characterId}
          onChange={(v) => setCharacterId(v)}
          options={(bible?.characters ?? []).map((c) => ({ value: c.id, label: c.name }))}
        />
      )}
      <Input.TextArea
        data-testid="chat-input"
        rows={3}
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="用一句话描述想改什么，例如「让世界观更冷酷」…"
      />
      <Button
        type="primary"
        block
        data-testid="chat-send"
        style={{ marginTop: 8 }}
        disabled={sendDisabled}
        loading={chat.isPending}
        onClick={() => void send()}
      >
        发送
      </Button>

      {history.length > 0 && (
        <List
          size="small"
          style={{ marginTop: 12 }}
          dataSource={history}
          renderItem={(item) => (
            <List.Item style={{ padding: "4px 0" }}>
              <Typography.Text
                style={{ flex: 1, marginRight: 8 }}
                ellipsis={{ tooltip: item.instruction }}
              >
                {item.instruction}
              </Typography.Text>
              <Tag color={STATUS_TAGS[item.status].color}>{STATUS_TAGS[item.status].text}</Tag>
            </List.Item>
          )}
        />
      )}

      {active && (
        <div style={{ marginTop: 12 }} data-testid="chat-proposal">
          <Typography.Text type="secondary">AI 修改建议（应用前请确认）</Typography.Text>
          <div style={{ marginTop: 4 }}>
            <DiffView diff={active.diff} />
          </div>
          <Space style={{ marginTop: 8 }}>
            <Button
              type="primary"
              data-testid="chat-apply"
              loading={resolve.isPending}
              onClick={() => void resolveProposal(true)}
            >
              应用
            </Button>
            <Button data-testid="chat-discard" onClick={() => void resolveProposal(false)}>
              放弃
            </Button>
          </Space>
          <Typography.Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0 }}>
            不满意？点「放弃」后重新描述要求，即可再次生成。
          </Typography.Paragraph>
        </div>
      )}
    </div>
  );
}
