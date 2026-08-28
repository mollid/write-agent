import { Card, Descriptions, Empty, Space, Tag, Typography } from "antd";
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useBible } from "../api/hooks";
import { RelationGraph, buildGraph, roleColor } from "../components/RelationGraph";
import { pageTitle, tokens } from "../theme";

/** 人物关系图谱：节点=人物（大小按关系数，颜色按角色），边=关系描述
 * （静态设定 + 最新章节演化，共同出场次数决定粗细）。点击节点看人物卡。 */
export default function Relationships() {
  const { name = "" } = useParams();
  const { data: bible } = useBible(name);
  const [selected, setSelected] = useState<string | null>(null);

  const graph = useMemo(() => (bible ? buildGraph(bible) : { nodes: [], edges: [] }), [bible]);
  const selectedChar = bible?.characters.find((c) => c.id === selected) ?? null;

  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }} data-testid="page-relationships">
      <Typography.Title level={4} style={pageTitle}>
        人物关系图谱
      </Typography.Title>
      {graph.nodes.length === 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="尚无人物设定">
          <Link to={`/p/${name}/setup`}>去分阶段设定</Link>
        </Empty>
      ) : (
        <div style={{ display: "flex", gap: 16, alignItems: "flex-start", flexWrap: "wrap" }}>
          <Card size="small" style={{ flex: "1 1 460px", minWidth: 0 }} title="图谱（点击人物查看详情）">
            <RelationGraph
              nodes={graph.nodes}
              edges={graph.edges}
              selected={selected}
              onSelect={(id) => setSelected((cur) => (cur === id ? null : id))}
            />
            <Space wrap style={{ marginTop: 8 }}>
              {[
                [tokens.brand, "主角/主人公"],
                [tokens.negative, "反派/宿敌"],
                [tokens.steel, "配角/盟友"],
              ].map(([color, text]) => (
                <Tag key={text} color={color}>
                  {text}
                </Tag>
              ))}
              <Tag>其他角色</Tag>
              <Typography.Text type="secondary">边越粗 = 共同关键事件越多</Typography.Text>
            </Space>
          </Card>
          <Card size="small" style={{ flex: "0 1 320px" }} title="人物详情" data-testid="relation-detail">
            {selectedChar ? (
              <>
                <Space style={{ marginBottom: 8 }}>
                  <Tag style={{ background: tokens.brandTint, borderColor: "transparent", color: tokens.graphite }}>
                    {selectedChar.role}
                  </Tag>
                  <Typography.Text strong>{selectedChar.name}</Typography.Text>
                </Space>
                <Descriptions
                  size="small"
                  column={1}
                  bordered
                  items={[
                    { key: "motivation", label: "动机", children: selectedChar.motivation },
                    { key: "arc", label: "人物弧", children: selectedChar.arc },
                    {
                      key: "state",
                      label: "当前状态",
                      children: `${selectedChar.state.emotional_state || "—"} · ${
                        selectedChar.state.location_end || "—"
                      }`,
                    },
                    {
                      key: "relationships",
                      label: "关系",
                      children: (
                        <ul style={{ margin: 0, paddingLeft: 18 }}>
                          {Object.entries({
                            ...selectedChar.relationships,
                            ...selectedChar.state.relationships_shifted,
                          }).map(([other, text]) => (
                            <li key={other}>
                              <span
                                style={{
                                  display: "inline-block",
                                  width: 8,
                                  height: 8,
                                  borderRadius: 4,
                                  background: roleColor(
                                    bible?.characters.find((c) => c.id === other)?.role ?? "",
                                  ),
                                  marginRight: 6,
                                }}
                              />
                              {bible?.characters.find((c) => c.id === other)?.name ?? other}：{text}
                            </li>
                          ))}
                          {Object.keys({
                            ...selectedChar.relationships,
                            ...selectedChar.state.relationships_shifted,
                          }).length === 0 && <li>（暂无关系记录）</li>}
                        </ul>
                      ),
                    },
                  ]}
                />
              </>
            ) : (
              <Typography.Text type="secondary">点击图谱中的人物查看详情</Typography.Text>
            )}
          </Card>
        </div>
      )}
      <Typography.Text type="secondary">项目：{name}</Typography.Text>
    </Space>
  );
}
