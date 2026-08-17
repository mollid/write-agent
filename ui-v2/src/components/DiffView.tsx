import type { CSSProperties } from "react";

/** Task 9: unified-diff preview. One element per line inside a single
 * `data-testid="diff-view"` container; each line carries `data-sign`
 * ("+" / "-" / "@" / "ctx") and the contract colors:
 * + green (#e6f4ea), - red (#fdecea), @@ gray, context unstyled. */

type Sign = "+" | "-" | "@" | "ctx";

const LINE_STYLES: Record<Sign, CSSProperties> = {
  "+": { backgroundColor: "#e6f4ea" },
  "-": { backgroundColor: "#fdecea" },
  "@": { backgroundColor: "#fafafa", color: "#8c8c8c" },
  ctx: {},
};

function signOf(line: string): Sign {
  if (line.startsWith("+")) return "+";
  if (line.startsWith("-")) return "-";
  if (line.startsWith("@")) return "@";
  return "ctx";
}

export default function DiffView({ diff }: { diff?: string }) {
  const lines = diff ? diff.split("\n") : [];
  return (
    <div
      data-testid="diff-view"
      style={{
        fontFamily: "monospace",
        fontSize: 12,
        lineHeight: "20px",
        border: "1px solid #f0f0f0",
        borderRadius: 4,
        overflow: "auto",
        maxHeight: 360,
      }}
    >
      {lines.map((line, i) => {
        const sign = signOf(line);
        return (
          <div key={i} data-sign={sign} style={{ whiteSpace: "pre-wrap", padding: "0 8px", ...LINE_STYLES[sign] }}>
            {line || "\u00A0"}
          </div>
        );
      })}
    </div>
  );
}
