"use client";

import { useEffect, useState } from "react";
import { STRINGS, Lang } from "@/lib/i18n";
import { OpenAILogo, AnthropicLogo, TerminalIcon, DotsIcon } from "./HarnessLogos";

type TabId = "chatgpt" | "claude" | "claudecode" | "cli" | "other";

const TABS: { id: TabId; logo: React.ReactNode }[] = [
  { id: "chatgpt", logo: <OpenAILogo /> },
  { id: "claude", logo: <AnthropicLogo /> },
  { id: "claudecode", logo: <AnthropicLogo /> },
  { id: "cli", logo: <TerminalIcon /> },
  { id: "other", logo: <DotsIcon /> },
];

export default function McpConnect({ lang }: { lang: Lang }) {
  const t = STRINGS[lang];
  const m = t.mcp;
  const [tab, setTab] = useState<TabId>("claudecode");
  const [origin, setOrigin] = useState("");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    setOrigin(window.location.origin);
  }, []);

  function fill(template: string) {
    return template
      .replaceAll("{displayName}", lang === "fr" ? "Canopée des arbres de Toronto" : "Toronto Tree Canopy")
      .replaceAll("{slug}", "toronto-tree-canopy")
      .replaceAll("{origin}", origin || "https://trees.canada.nshipyard.com");
  }

  const prompts: Record<Exclude<TabId, "other">, string> = {
    chatgpt: fill(m.pChatgpt),
    claude: fill(m.pClaude),
    claudecode: fill(m.pClaudeCode),
    cli: fill(m.pCli),
  };

  const tabLabel = (id: TabId) => m.tabs[id];
  const activePrompt = tab === "other" ? "" : prompts[tab];

  async function copy() {
    const text = tab === "other" ? `${origin || "https://trees.canada.nshipyard.com"}/mcp` : activePrompt;
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const ta = document.createElement("textarea");
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
    }
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  }

  const shownOrigin = origin || "https://trees.canada.nshipyard.com";

  return (
    <section className="mcp">
      <p className="mcp-kicker">{m.kicker}</p>
      <h2 className="mcp-title">{m.title}</h2>
      <p className="mcp-body">{m.body}</p>

      <div className="mcp-tabs" role="tablist">
        {TABS.map(({ id, logo }) => (
          <button
            key={id}
            role="tab"
            aria-selected={tab === id}
            onClick={() => setTab(id)}
            className={`mcp-tab${tab === id ? " active" : ""}`}
          >
            {logo}
            {tabLabel(id)}
          </button>
        ))}
      </div>

      <div className="mcp-card">
        <div className="mcp-cardhead">
          <h3>{tab === "other" ? m.otherTitle : m.cardTitle.replace("{tab}", tabLabel(tab))}</h3>
          <button onClick={copy} className="mcp-copy">
            {copied ? m.copied : m.copy}
          </button>
        </div>
        {tab === "other" ? (
          <div className="mcp-other">
            <p className="mcp-otherbody">{m.otherBody}</p>
            <dl className="mcp-rows">
              <div>
                <dt>{m.mcpEndpoint}</dt>
                <dd><code>{shownOrigin}/mcp</code></dd>
              </div>
              <div>
                <dt>{m.openapiSpec}</dt>
                <dd><code>{shownOrigin}/api/openapi.json</code></dd>
              </div>
              <div>
                <dt>{m.restExample}</dt>
                <dd><code>GET {shownOrigin}/api/v1/screen?address=407%20Arlington%20Ave</code></dd>
              </div>
            </dl>
          </div>
        ) : (
          <div className="mcp-promptwrap">
            {tab === "chatgpt" && <p className="mcp-note">{m.chatgptNote}</p>}
            <pre className="mcp-prompt">{activePrompt}</pre>
          </div>
        )}
      </div>
    </section>
  );
}
