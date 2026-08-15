import { Card, Descriptions, Empty, Table, Tag, Typography } from "antd";
import type { ReactNode } from "react";

/** Task 6 (R5): render a setup/gate artifact (pretty JSON produced by
 * `novel.render.artifact_text`) as structured AntD listings for the known
 * schemas; unknown shapes fall back to a key/value listing; non-JSON text
 * falls back to a <pre>. */

const FIELD_LABELS: Record<string, string> = {
  logline: "一句话概念",
  genre: "类型",
  tone: "基调",
  themes: "主题",
  target_length_words: "目标字数",
  audience: "读者画像",
  setting: "舞台设定",
  era: "时代",
  rules: "世界规则",
  power_system: "力量体系",
  factions: "阵营",
  locations: "地点",
  constraints: "硬性约束",
  id: "ID",
  slug: "别名",
  name: "姓名",
  role: "角色",
  backstory: "背景",
  motivation: "动机",
  arc: "人物弧",
  chapter_no: "章号",
  chapter_title: "章标题",
  planted_in: "埋设于",
  paid_off_in: "回收于",
  description: "描述",
};

/** Noise fields never useful in a stage artifact view (plan Task 6 filter). */
const HIDDEN_KEYS = new Set([
  "state",
  "voice_fingerprint",
  "mannerisms",
  "beats",
]);

function isEmptyValue(v: unknown): boolean {
  if (v === "" || v === null) return true;
  if (Array.isArray(v)) return v.length === 0;
  if (typeof v === "object" && v !== null) return Object.keys(v).length === 0;
  return false;
}

function renderValue(v: unknown): ReactNode {
  if (Array.isArray(v)) {
    return v.map((x, j) => (
      <Tag key={j}>{typeof x === "object" && x !== null ? JSON.stringify(x) : String(x)}</Tag>
    ));
  }
  if (typeof v === "object" && v !== null) return JSON.stringify(v);
  return String(v);
}

function fieldItems(obj: Record<string, unknown>) {
  return Object.entries(obj)
    .filter(([k, v]) => !HIDDEN_KEYS.has(k) && !isEmptyValue(v))
    .map(([k, v]) => ({
      key: k,
      label: FIELD_LABELS[k] ?? k,
      children: <span style={{ whiteSpace: "pre-wrap" }}>{renderValue(v)}</span>,
    }));
}

interface OutlineShape {
  arcs: { arc_name: string; chapters: { chapter_no: number; chapter_title: string }[] }[];
  foreshadow_ledger?: Record<string, unknown>[];
}

function asOutline(d: unknown): OutlineShape | null {
  if (typeof d !== "object" || d === null || Array.isArray(d)) return null;
  const o = d as { arcs?: unknown };
  return Array.isArray(o.arcs) ? (d as OutlineShape) : null;
}

/** Character lists carry a `name` — head each per-character Descriptions with it. */
function blockTitle(obj: object, isList: boolean): string | undefined {
  if (!isList) return undefined;
  const n = (obj as { name?: unknown }).name;
  return typeof n === "string" && n ? `人物：${n}` : undefined;
}

export function ArtifactView({ raw, title }: { raw: string; title?: string }) {
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    data = undefined;
  }
  if (data === undefined || data === null) {
    const trimmed = raw.trim();
    return trimmed ? <pre style={{ whiteSpace: "pre-wrap" }}>{trimmed}</pre> : <Empty />;
  }

  const outline = asOutline(data);
  if (outline) {
    return (
      <Card size="small" title={title} data-testid="artifact-view">
        {outline.arcs.length === 0 && (outline.foreshadow_ledger?.length ?? 0) === 0 ? (
          <Empty />
        ) : null}
        {outline.arcs.map((a) => (
          <div key={a.arc_name}>
            <Typography.Title level={5} style={{ marginTop: 12, marginBottom: 8 }}>
              {a.arc_name}
            </Typography.Title>
            <Table
              size="small"
              pagination={false}
              rowKey="chapter_no"
              dataSource={a.chapters}
              columns={[
                { title: "章号", dataIndex: "chapter_no", width: 90 },
                { title: "章标题", dataIndex: "chapter_title" },
              ]}
            />
          </div>
        ))}
        {(outline.foreshadow_ledger ?? []).map((f, i) => (
          <Descriptions
            key={String(f.id ?? i)}
            size="small"
            bordered
            column={1}
            style={{ marginTop: 12 }}
            items={fieldItems(f)}
          />
        ))}
      </Card>
    );
  }

  const isList = Array.isArray(data);
  const items: unknown[] = isList ? (data as unknown[]) : [data];
  return (
    <Card size="small" title={title} data-testid="artifact-view">
      {items.length === 0 ? <Empty /> : null}
      {items.map((obj, i) =>
        typeof obj !== "object" || obj === null ? (
          <Typography.Paragraph key={i}>{String(obj)}</Typography.Paragraph>
        ) : (
          <Descriptions
            key={i}
            size="small"
            bordered
            column={1}
            style={{ marginTop: i > 0 ? 12 : undefined }}
            title={blockTitle(obj, isList)}
            items={fieldItems(obj as Record<string, unknown>)}
          />
        ),
      )}
    </Card>
  );
}
