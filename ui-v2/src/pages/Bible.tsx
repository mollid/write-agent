import {
  App as AntApp,
  Alert,
  Button,
  Card,
  Col,
  Collapse,
  Descriptions,
  Divider,
  Input,
  InputNumber,
  Menu,
  Modal,
  Row,
  Space,
  Table,
  Tag,
  Timeline,
  Typography,
} from "antd";
import { useState } from "react";
import type { ReactNode } from "react";
import { useParams } from "react-router-dom";
import { ApiError } from "../api/client";
import {
  useBible,
  useMode,
  useOutlineExtend,
  useResolveGate,
  useSaveBibleSection,
} from "../api/hooks";
import { useEvents } from "../stores/events";
import { BIBLE_SECTION_NAMES } from "../constants";
import BibleChat from "../components/BibleChat";
import DiffView from "../components/DiffView";
import type {
  BibleData,
  CharacterData,
  EventData,
  ForeshadowData,
  OutlineFullData,
  WorldData,
} from "../api/types";

const EMPTY_TEXT = "该设定尚未生成";

const FORESHADOW_STATUS: Record<string, { color: string; text: string }> = {
  open: { color: "default", text: "待埋设" },
  planted: { color: "processing", text: "已埋设" },
  paid_off: { color: "success", text: "已回收" },
};

function EmptySection() {
  return <Typography.Text type="secondary">{EMPTY_TEXT}</Typography.Text>;
}

function ConceptView({ data }: { data: BibleData["concept"] }) {
  if (!data) return <EmptySection />;
  return (
    <Descriptions
      size="small"
      bordered
      column={1}
      items={[
        { key: "logline", label: "一句话概念", children: data.logline },
        { key: "genre", label: "类型", children: data.genre },
        { key: "tone", label: "基调", children: data.tone },
        { key: "themes", label: "主题", children: data.themes.join("、") },
        { key: "audience", label: "读者画像", children: data.audience },
        { key: "target_length_words", label: "目标字数", children: data.target_length_words },
      ]}
    />
  );
}

function WorldView({ data }: { data: WorldData | null }) {
  if (!data) return <EmptySection />;
  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }}>
      <Descriptions
        size="small"
        bordered
        column={1}
        items={[
          { key: "setting", label: "舞台设定", children: data.setting },
          { key: "era", label: "时代", children: data.era || "—" },
          { key: "power_system", label: "力量体系", children: data.power_system || "—" },
        ]}
      />
      {data.rules.length > 0 && (
        <div>
          <Typography.Text strong>世界规则</Typography.Text>
          <ul style={{ margin: "8px 0 0", paddingLeft: 20 }}>
            {data.rules.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        </div>
      )}
      {data.constraints.length > 0 && (
        <div>
          <Typography.Text strong>硬性约束</Typography.Text>
          <ul style={{ margin: "8px 0 0", paddingLeft: 20 }}>
            {data.constraints.map((c, i) => (
              <li key={i}>{c}</li>
            ))}
          </ul>
        </div>
      )}
      {data.locations.length > 0 && (
        <div>
          <Typography.Text strong>地点</Typography.Text>
          <Row gutter={[8, 8]} style={{ marginTop: 8 }}>
            {data.locations.map((l) => (
              <Col key={l.name} span={12}>
                <Card size="small" type="inner" title={l.name}>
                  <Typography.Text type="secondary">{l.description}</Typography.Text>
                </Card>
              </Col>
            ))}
          </Row>
        </div>
      )}
      {data.factions.length > 0 && (
        <div>
          <Typography.Text strong>阵营</Typography.Text>
          <Row gutter={[8, 8]} style={{ marginTop: 8 }}>
            {data.factions.map((f) => (
              <Col key={f.name} span={12}>
                <Card size="small" type="inner" title={f.name}>
                  <Typography.Text type="secondary">{f.ideology}</Typography.Text>
                </Card>
              </Col>
            ))}
          </Row>
        </div>
      )}
    </Space>
  );
}

function CharactersView({ data }: { data: CharacterData[] }) {
  if (data.length === 0) return <EmptySection />;
  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }}>
      {data.map((c) => (
        <Card key={c.id} size="small" type="inner" title={`${c.name}（${c.role}）`}>
          <Descriptions
            size="small"
            bordered
            column={1}
            items={[
              { key: "backstory", label: "背景", children: c.backstory || "—" },
              { key: "motivation", label: "动机", children: c.motivation || "—" },
              { key: "arc", label: "人物弧", children: c.arc || "—" },
            ]}
          />
          <Descriptions
            size="small"
            column={1}
            title="动态状态"
            style={{ marginTop: 12 }}
            items={[
              { key: "emotional_state", label: "情绪", children: c.state.emotional_state || "—" },
              { key: "location_end", label: "章末位置", children: c.state.location_end || "—" },
              {
                key: "voice_fingerprint",
                label: "语言指纹",
                children: `${Object.keys(c.voice_fingerprint).length} 条`,
              },
              {
                key: "mannerisms",
                label: "口头禅 Top3",
                children:
                  c.mannerisms
                    .slice(0, 3)
                    .map((m) => `${m.text} ×${m.used_count}`)
                    .join("；") || "—",
              },
              {
                key: "description_history",
                label: "描写历史",
                children: `${c.description_history.length} 条`,
              },
              {
                key: "relationships",
                label: "关系",
                children:
                  Object.entries(c.relationships)
                    .map(([k, v]) => `${k}：${v}`)
                    .join("；") || "—",
              },
            ]}
          />
        </Card>
      ))}
    </Space>
  );
}

function OutlineArcsView({ data }: { data: OutlineFullData | null }) {
  if (!data || data.arcs.length === 0) return <EmptySection />;
  return (
    <Collapse
      items={data.arcs.map((arc, ai) => ({
        key: String(ai),
        label: arc.arc_name || `弧线 ${ai + 1}`,
        children: (
          <Collapse
            items={arc.chapters.map((ch) => ({
              key: String(ch.chapter_no),
              label: `第${ch.chapter_no}章 · ${ch.chapter_title}`,
              children:
                ch.beats.length === 0 ? (
                  <Typography.Text type="secondary">（无节拍）</Typography.Text>
                ) : (
                  <Space direction="vertical" size="small" style={{ width: "100%" }}>
                    {ch.beats.map((b, bi) => (
                      <div key={b.beat_id || bi}>
                        <Typography.Text>{b.event}</Typography.Text>{" "}
                        <Typography.Text type="secondary">
                          （{b.pov} · {b.emotional_turn}）
                        </Typography.Text>{" "}
                        {b.plants.map((id) => (
                          <Tag key={`p-${id}`} color="orange">
                            埋设 {id}
                          </Tag>
                        ))}
                        {b.payoffs.map((id) => (
                          <Tag key={`y-${id}`} color="green">
                            回收 {id}
                          </Tag>
                        ))}
                      </div>
                    ))}
                  </Space>
                ),
            }))}
          />
        ),
      }))}
    />
  );
}

function OutlineExtendBlock({ name }: { name: string }) {
  const outlineProposal = useEvents((s) => s.outlineProposal);
  const extend = useOutlineExtend(name);
  const resolve = useResolveGate(name);
  const { message } = AntApp.useApp();
  const [n, setN] = useState(3);

  async function doExtend() {
    try {
      await extend.mutateAsync({ n });
      message.info("追章任务已开始，建议生成后会出现在下方");
    } catch (e) {
      message.error(String(e instanceof Error ? e.message : e));
    }
  }

  async function resolveProposal(approve: boolean) {
    if (!outlineProposal) return;
    try {
      await resolve.mutateAsync({ id: outlineProposal.gateId, approve });
      message.info("已提交确认");
    } catch (e) {
      message.error(String(e instanceof Error ? e.message : e));
    }
  }

  return (
    <div>
      <Divider style={{ margin: "16px 0 12px" }} />
      <Space wrap>
        <Typography.Text>追章：</Typography.Text>
        <InputNumber min={1} max={50} value={n} onChange={(v) => setN(v ?? 1)} />
        <Button
          type="primary"
          data-testid="extend-outline"
          loading={extend.isPending}
          onClick={() => void doExtend()}
        >
          追加章节
        </Button>
        <Typography.Text type="secondary">在既有大纲末尾续写后续章节</Typography.Text>
      </Space>
      {outlineProposal && (
        <div data-testid="outline-proposal" style={{ marginTop: 16 }}>
          <Typography.Text type="secondary">
            追章建议（新增 {outlineProposal.added} 章，应用前请确认）
          </Typography.Text>
          <div style={{ marginTop: 4 }}>
            <DiffView diff={outlineProposal.diff} />
          </div>
          <Space style={{ marginTop: 8 }}>
            <Button
              type="primary"
              data-testid="outline-apply"
              loading={resolve.isPending}
              onClick={() => void resolveProposal(true)}
            >
              应用
            </Button>
            <Button data-testid="outline-discard" onClick={() => void resolveProposal(false)}>
              放弃
            </Button>
          </Space>
        </div>
      )}
    </div>
  );
}

function ForeshadowsView({ data }: { data: ForeshadowData[] }) {
  if (data.length === 0) return <EmptySection />;
  const ch = (v: number | null) => (v == null ? "—" : v);
  return (
    <Table
      rowKey="id"
      size="small"
      pagination={false}
      dataSource={data}
      columns={[
        { title: "ID", dataIndex: "id", width: 120 },
        { title: "描述", dataIndex: "description" },
        { title: "埋设章", dataIndex: "planted_ch", width: 90, render: ch },
        { title: "回收章", dataIndex: "payoff_ch", width: 90, render: ch },
        {
          title: "状态",
          dataIndex: "status",
          width: 110,
          render: (s: string) => {
            const meta = FORESHADOW_STATUS[s];
            return <Tag color={meta?.color ?? "default"}>{meta?.text ?? s}</Tag>;
          },
        },
      ]}
    />
  );
}

function EventsView({ data }: { data: EventData[] }) {
  if (data.length === 0) return <EmptySection />;
  return (
    <Timeline
      items={[...data].reverse().map((ev) => ({
        key: ev.id,
        children: (
          <div>
            <div>{`第${ev.chapter}章 · ${ev.summary}`}</div>
            {ev.characters.length > 0 && (
              <Typography.Text type="secondary">{ev.characters.join("、")}</Typography.Text>
            )}
          </div>
        ),
      }))}
    />
  );
}

function sectionDataOf(bible: BibleData | undefined, section: string): unknown {
  if (!bible) return undefined;
  switch (section) {
    case "concept":
      return bible.concept;
    case "world":
      return bible.world;
    case "characters":
      return bible.characters;
    case "outline":
      return bible.outline;
    case "foreshadows":
      return bible.foreshadows;
    default:
      return undefined;
  }
}

function sectionBody(section: string, bible: BibleData): ReactNode {
  switch (section) {
    case "concept":
      return <ConceptView data={bible.concept} />;
    case "world":
      return <WorldView data={bible.world} />;
    case "characters":
      return <CharactersView data={bible.characters} />;
    case "outline":
      return <OutlineArcsView data={bible.outline} />;
    case "foreshadows":
      return <ForeshadowsView data={bible.foreshadows} />;
    case "events":
      return <EventsView data={bible.events} />;
    default:
      return null;
  }
}

/** Task 10: bible workbench — per-section preview, JSON edit modal, chat
 * panel (right column) and outline extend with a gate-resolved proposal. */
export default function Bible() {
  const { name = "" } = useParams();
  const [section, setSection] = useState("concept");
  const { data: mode } = useMode();
  const { data: bible } = useBible(name);
  const save = useSaveBibleSection(name);
  const { message } = AntApp.useApp();
  const [editOpen, setEditOpen] = useState(false);
  const [editText, setEditText] = useState("");

  const label = BIBLE_SECTION_NAMES[section] ?? section;

  function openEdit() {
    const seed =
      sectionDataOf(bible, section) ?? (section === "characters" || section === "foreshadows" ? [] : {});
    setEditText(JSON.stringify(seed, null, 2));
    setEditOpen(true);
  }

  async function saveEdit() {
    let parsed: unknown;
    try {
      parsed = JSON.parse(editText);
    } catch {
      message.error("非法 JSON");
      return;
    }
    try {
      await save.mutateAsync({ section, data: parsed });
      message.success("已保存");
      setEditOpen(false);
    } catch (e) {
      if (e instanceof ApiError) message.error(e.message);
      else message.error(String(e instanceof Error ? e.message : e));
    }
  }

  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }} data-testid="page-bible">
      <Typography.Title level={4} style={{ margin: 0 }}>
        设定库
      </Typography.Title>
      {mode && !mode.live && (
        <Alert
          type="info"
          showIcon
          data-testid="demo-notice"
          message="演示模式：对话改写不会改变内容"
        />
      )}
      <div style={{ display: "flex", gap: 16, alignItems: "flex-start" }}>
        <Card size="small" title="设定分类" style={{ width: 170 }}>
          <Menu
            mode="inline"
            style={{ borderInlineEnd: 0 }}
            selectedKeys={[section]}
            onSelect={({ key }) => setSection(String(key))}
            items={Object.entries(BIBLE_SECTION_NAMES).map(([k, v]) => ({ key: k, label: v }))}
          />
        </Card>
        <Row gutter={[16, 16]} style={{ flex: 1, minWidth: 0 }}>
          <Col span={16} style={{ minWidth: 0 }}>
            <Card
              size="small"
              title={label}
              extra={
                section !== "events" ? (
                  <Button size="small" data-testid="edit-json" onClick={openEdit}>
                    编辑 JSON
                  </Button>
                ) : undefined
              }
            >
              {bible === undefined ? (
                <Typography.Text type="secondary">加载中…</Typography.Text>
              ) : (
                <>
                  {sectionBody(section, bible)}
                  {section === "outline" && <OutlineExtendBlock name={name} />}
                </>
              )}
            </Card>
          </Col>
          <Col span={8} style={{ minWidth: 0 }}>
            <Card size="small" title={`对话改写 · ${label}`}>
              <BibleChat name={name} section={section} />
            </Card>
          </Col>
        </Row>
      </div>
      <Modal
        title={`编辑 JSON · ${label}`}
        open={editOpen}
        onCancel={() => setEditOpen(false)}
        onOk={() => void saveEdit()}
        okText="保存"
        cancelText="取消"
        okButtonProps={{ loading: save.isPending }}
        width={680}
      >
        <Input.TextArea
          data-testid="edit-json-text"
          rows={16}
          style={{ fontFamily: "monospace" }}
          value={editText}
          onChange={(e) => setEditText(e.target.value)}
        />
      </Modal>
    </Space>
  );
}
