import { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  BrowserRouter,
  Navigate,
  Outlet,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useParams,
} from "react-router-dom";
import { App as AntApp, Button, ConfigProvider, Layout, Menu, Select, Tag } from "antd";
import zhCN from "antd/locale/zh_CN";
import { useMode, useProjects } from "./api/hooks";
import { useProjectEvents } from "./api/events";
import JobStrip from "./components/JobStrip";
import GateModal from "./components/GateModal";
import Projects from "./pages/Projects";
import Overview from "./pages/Overview";
import Setup from "./pages/Setup";
import Bible from "./pages/Bible";
import Generate from "./pages/Generate";
import Reader from "./pages/Reader";
import Reviews from "./pages/Reviews";
import Threads from "./pages/Threads";
import Export from "./pages/Export";

const qc = new QueryClient();

function Shell() {
  const { name = "" } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);
  const { data: mode } = useMode();
  const { data: projects = [] } = useProjects();
  useProjectEvents(name || undefined);
  const items = [
    {
      type: "group" as const,
      label: "创作",
      children: [
        { key: "overview", label: "概览" },
        { key: "setup", label: "分阶段设定" },
        { key: "bible", label: "设定库" },
        { key: "generate", label: "生成章节" },
        { key: "reader", label: "章节阅读" },
      ],
    },
    {
      type: "group" as const,
      label: "审阅与输出",
      children: [
        { key: "reviews", label: "评分历史" },
        { key: "threads", label: "伏笔台账" },
        { key: "export", label: "导出" },
      ],
    },
  ];
  const selected = location.pathname.split("/")[3] ?? "overview";
  return (
    <Layout style={{ height: "100%" }}>
      <Layout.Sider
        width={200}
        theme="light"
        breakpoint="lg"
        collapsible
        collapsed={collapsed}
        onCollapse={setCollapsed}
        trigger={null}
      >
        {/* clickable title = the only way back to the project list from /p/:name */}
        <div
          data-testid="home-link"
          role="button"
          tabIndex={0}
          aria-label="返回项目列表"
          style={{
            padding: 16,
            fontWeight: 600,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 8,
            cursor: "pointer",
          }}
          onClick={() => navigate("/")}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") navigate("/");
          }}
        >
          {!collapsed && <span>小说控制台</span>}
          {/* a11y: the default Sider trigger is a plain div with no accessible
           * role — replace it with a labelled button */}
          <Button
            type="text"
            size="small"
            aria-label={collapsed ? "展开侧边栏" : "收起侧边栏"}
            onClick={() => setCollapsed(!collapsed)}
          >
            {collapsed ? "»" : "«"}
          </Button>
        </div>
        <Menu
          mode="inline"
          selectedKeys={[selected]}
          items={items}
          onSelect={({ key }) => navigate(`/p/${name}/${key}`)}
        />
      </Layout.Sider>
      <Layout>
        <Layout.Header
          style={{
            background: "#fff",
            paddingInline: 16,
            display: "flex",
            alignItems: "center",
            gap: 12,
          }}
        >
          <Select
            style={{ minWidth: 180 }}
            placeholder="选择项目…"
            value={name || undefined}
            options={projects.map((p) => ({ value: p.name, label: p.name }))}
            onChange={(v) => navigate(`/p/${v}/overview`)}
          />
          <Tag color={mode?.live ? "green" : "default"}>
            {mode?.live ? "真实模型模式" : "演示模式"}
          </Tag>
        </Layout.Header>
        <div style={{ padding: "0 16px" }}>
          {name ? (
            <>
              <JobStrip project={name} />
              <GateModal project={name} />
            </>
          ) : null}
        </div>
        <Layout.Content style={{ padding: 16, overflow: "auto" }}>
          <Outlet />
        </Layout.Content>
      </Layout>
    </Layout>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <ConfigProvider locale={zhCN}>
        <AntApp>
          <BrowserRouter>
            <Routes>
              <Route path="/" element={<Projects />} />
              <Route path="/p/:name" element={<Shell />}>
                <Route index element={<Navigate to="overview" replace />} />
                <Route path="overview" element={<Overview />} />
                <Route path="setup" element={<Setup />} />
                <Route path="bible" element={<Bible />} />
                <Route path="generate" element={<Generate />} />
                <Route path="reader" element={<Reader />} />
                <Route path="reviews" element={<Reviews />} />
                <Route path="threads" element={<Threads />} />
                <Route path="export" element={<Export />} />
              </Route>
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </BrowserRouter>
        </AntApp>
      </ConfigProvider>
    </QueryClientProvider>
  );
}
