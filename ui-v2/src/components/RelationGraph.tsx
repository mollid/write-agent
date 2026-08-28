import type { BibleData } from "../api/types";
import type { CharacterData } from "../api/types";

/** 人物关系图谱 — 数据构建 + 无依赖 SVG 径向布局。
 * 边 = 静态 relationships 标签（随章节更新的 relationships_shifted 覆盖）
 *    + 关键事件共同出场次数（权重/粗细）。
 * 节点 = 人物，大小按连接数，颜色按 role 关键词。 */

export interface GraphNode {
  id: string;
  name: string;
  role: string;
  degree: number;
}
export interface GraphEdge {
  a: string;
  b: string;
  label: string;
  weight: number;
}

const pairKey = (a: string, b: string): string => (a < b ? `${a}|${b}` : `${b}|${a}`);

/** Derive nodes+edges from a bible payload. Pure — exported for tests. */
export function buildGraph(bible: BibleData): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const chars = bible.characters;
  const names = new Map(chars.map((c) => [c.id, c.name]));

  // edge weight: co-appearance in key events
  const weight = new Map<string, number>();
  for (const ev of bible.events ?? []) {
    const ids = [...new Set(ev.characters ?? [])].filter((id) => names.has(id));
    for (let i = 0; i < ids.length; i++) {
      for (let j = i + 1; j < ids.length; j++) {
        const k = pairKey(ids[i], ids[j]);
        weight.set(k, (weight.get(k) ?? 0) + 1);
      }
    }
  }

  // edge label: static relationships first, latest per-chapter shifts override
  const label = new Map<string, string>();
  const collect = (c: CharacterData, src: Record<string, string> | undefined): void => {
    for (const [other, text] of Object.entries(src ?? {})) {
      if (names.has(other) && text.trim()) label.set(pairKey(c.id, other), text.trim());
    }
  };
  for (const c of chars) {
    collect(c, c.relationships);
    collect(c, c.state?.relationships_shifted);
  }

  const keys = [...new Set([...weight.keys(), ...label.keys()])];
  const edges: GraphEdge[] = keys.map((k) => {
    const [a, b] = k.split("|");
    return { a, b, label: label.get(k) ?? "", weight: weight.get(k) ?? 0 };
  });

  const degree = new Map<string, number>(chars.map((c) => [c.id, 0]));
  for (const e of edges) {
    degree.set(e.a, (degree.get(e.a) ?? 0) + 1);
    degree.set(e.b, (degree.get(e.b) ?? 0) + 1);
  }
  const nodes: GraphNode[] = chars.map((c) => ({
    id: c.id, name: c.name, role: c.role, degree: degree.get(c.id) ?? 0,
  }));
  return { nodes, edges };
}

// 角色配色取自 DESIGN.md 调色板：品牌紫（主角）、语义红（反派）、中灰（配角）
const ROLE_COLORS: [RegExp, string][] = [
  [/主角|主人公|视图主角|protagonist/i, "#8848F9"],
  [/反派|宿敌|对手|antagonist|villain/i, "#F4165F"],
  [/配角|盟友|导师|ally|mentor|support/i, "#7F7F7F"],
];
export const roleColor = (role: string): string =>
  ROLE_COLORS.find(([re]) => re.test(role))?.[1] ?? "#8c8c8c";

const W = 680;
const H = 520;

export function RelationGraph({
  nodes,
  edges,
  selected,
  onSelect,
}: {
  nodes: GraphNode[];
  edges: GraphEdge[];
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  // radial layout: highest-degree node at the centre, the rest clockwise from
  // the top in degree order — deterministic, so tests and rerenders are stable
  const byDegree = [...nodes].sort((x, y) => y.degree - x.degree || x.id.localeCompare(y.id));
  const [center, ...rest] = byDegree;
  const cx = W / 2;
  const cy = H / 2;
  const radius = Math.min(200, 60 + rest.length * 13);
  const pos = new Map<string, { x: number; y: number }>();
  if (center) pos.set(center.id, { x: cx, y: cy });
  rest.forEach((n, i) => {
    const angle = (i / Math.max(rest.length, 1)) * Math.PI * 2 - Math.PI / 2;
    pos.set(n.id, { x: cx + radius * Math.cos(angle), y: cy + radius * Math.sin(angle) });
  });

  const nodeR = (n: GraphNode): number => 16 + Math.min(n.degree, 6) * 2.5;
  const relatedTo = (id: string): Set<string> => {
    const s = new Set<string>();
    for (const e of edges) {
      if (e.a === id) s.add(e.b);
      if (e.b === id) s.add(e.a);
    }
    return s;
  };
  const related = selected != null ? relatedTo(selected) : null;

  return (
    <svg data-testid="relation-graph" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="人物关系图谱" style={{ width: "100%", maxWidth: W }}>
      {edges.map((e) => {
        const pa = pos.get(e.a);
        const pb = pos.get(e.b);
        if (!pa || !pb) return null;
        const active = selected == null || e.a === selected || e.b === selected;
        return (
          <g key={`${e.a}|${e.b}`} opacity={active ? 1 : 0.2}>
            <line
              x1={pa.x} y1={pa.y} x2={pb.x} y2={pb.y}
              stroke="#bfbfbf" strokeWidth={1 + Math.min(e.weight, 5)}
            />
            <title>{`${e.label || "（无关系描述）"} · 共同关键事件 ${e.weight} 次`}</title>
            {e.label && (
              <text
                x={(pa.x + pb.x) / 2} y={(pa.y + pb.y) / 2 - 5}
                fontSize={10} textAnchor="middle" fill="#595959"
              >
                {e.label.length > 10 ? `${e.label.slice(0, 10)}…` : e.label}
              </text>
            )}
          </g>
        );
      })}
      {byDegree.map((n) => {
        const p = pos.get(n.id);
        if (!p) return null;
        const dim = selected != null && selected !== n.id && !related?.has(n.id);
        return (
          <g
            key={n.id}
            data-testid={`graph-node-${n.id}`}
            transform={`translate(${p.x},${p.y})`}
            style={{ cursor: "pointer" }}
            opacity={dim ? 0.4 : 1}
            onClick={() => onSelect(n.id)}
          >
            <title>{`${n.name}（${n.role}）· ${n.degree} 段关系`}</title>
            <circle r={nodeR(n)} fill={roleColor(n.role)} stroke="#fff" strokeWidth={2} />
            <text y={4} textAnchor="middle" fontSize={11} fontWeight={600} fill="#fff">
              {n.name.slice(0, 2)}
            </text>
            <text y={nodeR(n) + 15} textAnchor="middle" fontSize={12} fill="#262626">
              {n.name}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
