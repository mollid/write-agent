import type { ThemeConfig } from "antd";
import type { CSSProperties } from "react";

/**
 * 设计 token —— 唯一来源：仓库根目录 DESIGN.md（小说创作平台 · 管理后台设计规范）。
 * 所有颜色实测自 design/react/ 导出稿；禁止在别处临时新增颜色（DESIGN.md「颜色禁令」）。
 */
export const tokens = {
  canvas: "#FAFAFA",
  surface: "#FFFFFF",
  ink: "#0A0A0A",
  graphite: "#202020",
  ink60: "rgba(10, 10, 10, 0.6)",
  steel: "#7F7F7F",
  line: "#E5E5E5",
  border: "#E0DFDF",
  border2: "#E2E2E2",
  icon: "#171717",
  brand: "#8848F9",
  brandHover: "#7A3CE6",
  brandTint: "#F1E4FB",
  brandTrack: "rgba(136, 72, 249, 0.2)",
  positive: "#00A63E",
  negative: "#F4165F",
} as const;

/** 卡片阴影：仅一层 shadow-sm，禁止更重阴影（DESIGN.md · Elevation & Depth） */
export const shadowCard = "0 1px 2px -1px rgba(0,0,0,0.10), 0 1px 3px 0 rgba(0,0,0,0.10)";

/** AntD ConfigProvider 主题 —— DESIGN.md「落地 ui-v2（Ant Design 5）主题映射」 */
export const theme: ThemeConfig = {
  token: {
    colorPrimary: tokens.brand,
    // 全站唯一 accent：info 同用品牌紫，避免引入蓝色
    colorInfo: tokens.brand,
    colorSuccess: tokens.positive,
    colorError: tokens.negative,
    colorBgLayout: tokens.canvas,
    colorBgContainer: tokens.surface,
    colorText: tokens.graphite,
    colorTextHeading: tokens.ink,
    colorTextSecondary: tokens.steel,
    colorBorder: tokens.border,
    colorBorderSecondary: tokens.line,
    borderRadius: 6,
    fontFamily: 'Inter, -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif',
    fontSize: 14,
    controlHeight: 36,
  },
  components: {
    Layout: {
      siderBg: tokens.canvas,
      headerBg: tokens.surface,
      headerHeight: 64,
      headerPadding: "0 24px",
    },
    Menu: {
      itemBg: "transparent",
      itemHeight: 48,
      itemBorderRadius: 6,
      itemSelectedBg: tokens.brandTint,
      itemSelectedColor: tokens.brand,
      groupTitleColor: tokens.ink60,
      itemMarginInline: 12,
    },
    Card: {
      borderRadiusLG: 12,
      paddingLG: 24,
      paddingSM: 16,
      boxShadowTertiary: shadowCard,
    },
    Table: {
      headerBg: tokens.surface,
      headerColor: tokens.graphite,
      rowHoverBg: tokens.canvas,
      cellPaddingBlock: 16,
    },
    Progress: {
      remainingColor: tokens.brandTrack,
    },
    Switch: {
      trackHeight: 18,
      trackMinWidth: 32,
      handleSize: 14,
    },
    Tag: {
      // 状态徽章为全圆角胶囊（DESIGN.md · 状态徽章）
      borderRadiusSM: 999,
    },
    Button: {
      // 主按钮无边框无阴影（DESIGN.md · 按钮）
      primaryShadow: "none",
      defaultShadow: "none",
      dangerShadow: "none",
    },
  },
};

/** 页面标题：Display 30px/36px Bold Ink（DESIGN.md · Typography） */
export const pageTitle: CSSProperties = {
  margin: 0,
  fontSize: 30,
  lineHeight: "36px",
  fontWeight: 700,
  color: tokens.ink,
};
