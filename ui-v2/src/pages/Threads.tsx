import { Card, Empty, Table, Tag } from "antd";
import { useParams } from "react-router-dom";
import { useThreads } from "../api/hooks";

const STATUS_META: Record<string, { color: string; text: string }> = {
  open: { color: "orange", text: "待埋设" },
  planted: { color: "blue", text: "已埋设" },
  paid_off: { color: "green", text: "已回收" },
};
const meta = (s: string) => STATUS_META[s] ?? { color: "default", text: s };

/** Task 8: foreshadowing ledger — table of planted threads with status tags. */
export default function Threads() {
  const { name = "" } = useParams();
  const { data: threads = [], isFetched } = useThreads(name);

  return (
    <Card size="small" title="伏笔台账" data-testid="page-threads">
      {isFetched && threads.length === 0 ? (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="暂无伏笔记录——生成章节时埋设的伏笔会自动登记到这里"
        />
      ) : (
        <Table
          rowKey="id"
          size="small"
          dataSource={threads}
          pagination={false}
          columns={[
            { title: "ID", dataIndex: "id", width: 140 },
            { title: "描述", dataIndex: "description" },
            {
              title: "状态",
              dataIndex: "status",
              width: 140,
              render: (s: string) => (
                <Tag color={meta(s).color}>
                  {meta(s).text}（{s}）
                </Tag>
              ),
            },
          ]}
        />
      )}
    </Card>
  );
}
