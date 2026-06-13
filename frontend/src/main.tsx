import React, { FormEvent, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Bot, ChevronDown, CircleStop, Clipboard, ExternalLink, RefreshCw, Send, Settings2, X } from "lucide-react";
import "./styles.css";

type Role = "user" | "assistant" | "system";

type ChatMessage = {
  id: string;
  role: Role;
  content: string;
  thinking?: string;
  thinkingTime?: string;
  isStreaming?: boolean;
  streamingThinking?: boolean;
  thinkingCollapsed?: boolean;
  isError?: boolean;
  reasoningEvents?: ReasoningEvent[];
};

type StreamEvent = {
  type: string;
  content?: string;
  answer?: string;
  message?: string;
  name?: string;
  arguments?: unknown;
  result?: unknown;
  session_id?: string;
  thinking?: string;
  time?: string;
  seq?: number;
};

type ReasoningEvent = {
  seq: number;
  type: "thinking" | "tool_use" | "tool_result";
  content?: string;
  name?: string;
  arguments?: unknown;
  result?: unknown;
};

type QrPrompt = {
  url: string;
  nativeUrl?: string;
  sessionId?: string;
  createdAt: number;
  popupBlocked?: boolean;
};

type DeviceRecord = {
  name?: string;
  alias?: string;
  platform?: string;
  source?: string;
  remark?: string;
  status_text?: string;
  status_ok?: boolean;
};

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:3011";

function uid(prefix: string) {
  return `${prefix}_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

function stringify(value: unknown) {
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function eventSeq(eventData: StreamEvent, fallback: number) {
  return Number.isFinite(eventData.seq) ? Number(eventData.seq) : fallback;
}

function addReasoningEvent(message: ChatMessage, event: ReasoningEvent): ChatMessage {
  const current = [...(message.reasoningEvents || [])].sort((a, b) => a.seq - b.seq);
  const last = current[current.length - 1];
  if (event.type === "thinking" && last?.type === "thinking") {
    return {
      ...message,
      reasoningEvents: [
        ...current.slice(0, -1),
        {
          ...last,
          seq: Math.min(last.seq, event.seq),
          content: `${last.content || ""}${event.content || ""}`,
        },
      ],
    };
  }
  return {
    ...message,
    reasoningEvents: [...current, event].sort((a, b) => a.seq - b.seq),
  };
}

function isJsonLike(text: string) {
  const value = text.trim();
  return (value.startsWith("{") && value.endsWith("}")) || (value.startsWith("[") && value.endsWith("]"));
}

function compactToolResult(result: unknown) {
  const text = stringify(result).trim();
  if (!text) return "";
  if (isJsonLike(text)) {
    try {
      const parsed = JSON.parse(text);
      if (typeof parsed === "object" && parsed !== null && "stdout" in parsed) {
        return stringify((parsed as { stdout?: unknown }).stdout).trim();
      }
    } catch {
      return text;
    }
  }
  return text;
}

function MessageView({ message }: { message: ChatMessage }) {
  const [expanded, setExpanded] = useState(message.isStreaming || false);
  const [copied, setCopied] = useState(false);
  const isUser = message.role === "user";
  const events = [...(message.reasoningEvents || [])].sort((a, b) => a.seq - b.seq);
  const hasProcess = !isUser && (events.length > 0 || !!message.thinking);

  async function copyAnswer() {
    await navigator.clipboard.writeText(message.content || "");
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1400);
  }

  if (isUser) {
    return (
      <article className="message user">
        <div className="bubble user-bubble">{message.content}</div>
      </article>
    );
  }

  return (
    <article className={`message assistant ${message.isStreaming ? "streaming" : ""}`}>
      {hasProcess && (
        <section className="reasoning-panel">
          <button type="button" className="reasoning-header" onClick={() => setExpanded((value) => !value)}>
            <ChevronDown size={14} className={expanded ? "expanded" : ""} />
            <span>{message.isStreaming ? "正在思考与调用工具" : `思考与工具${message.thinkingTime ? ` · ${message.thinkingTime}s` : ""}`}</span>
          </button>
          {expanded && (
            <div className="reasoning-timeline">
              {events.length > 0 ? (
                events.map((item, index) => (
                  <div className={`reasoning-event ${item.type}`} key={`${item.type}-${item.seq}-${index}`}>
                    {item.type === "thinking" && <p>{item.content}</p>}
                    {item.type === "tool_use" && (
                      <details open>
                        <summary>调用工具 · {item.name || "tool"}</summary>
                        <pre>{stringify(item.arguments || {})}</pre>
                      </details>
                    )}
                    {item.type === "tool_result" && (
                      <details>
                        <summary>工具结果 · {item.name || "tool"}</summary>
                        <pre>{compactToolResult(item.result)}</pre>
                      </details>
                    )}
                  </div>
                ))
              ) : (
                <div className="reasoning-event thinking">
                  <p>{message.thinking}</p>
                </div>
              )}
              {message.isStreaming && <span className="cursor">_</span>}
            </div>
          )}
        </section>
      )}
      <div className={`bubble assistant-bubble ${message.isError ? "error" : ""}`}>
        {message.content ? (
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
        ) : (
          <span className="pending-text">{message.isStreaming ? "..." : ""}</span>
        )}
        {message.isStreaming && !message.streamingThinking && <span className="cursor">_</span>}
      </div>
      {!message.isStreaming && message.content && (
        <button type="button" className="copy-button" onClick={copyAnswer} title="Copy answer">
          <Clipboard size={13} />
          <span>{copied ? "已复制" : "复制"}</span>
        </button>
      )}
    </article>
  );
}

function findQrPrompt(value: unknown): QrPrompt | null {
  const rawText = typeof value === "string" ? value : stringify(value);
  let text = rawText;
  if (typeof value === "string") {
    try {
      const parsed = JSON.parse(value) as { stdout?: unknown };
      if (typeof parsed.stdout === "string") {
        text = parsed.stdout;
      }
    } catch {
      text = rawText;
    }
  }
  const nativeUrl = text.match(/^\s*url=(http:\/\/127\.0\.0\.1:\d+\/\?\S+)/m)?.[1];
  const localUrl = text.match(/local_qr_url=(\/\S+)/)?.[1];
  const publicUrl = text.match(/public_url=(https?:\/\/\S+)/)?.[1] || text.match(/!\[[^\]]*\]\((https?:\/\/[^)\s]+)\)/)?.[1];
  const sessionId = text.match(/session_id=([A-Za-z0-9_-]+)/)?.[1];
  const rawUrl = nativeUrl || (localUrl ? `${API_BASE}${localUrl}` : publicUrl);
  if (!rawUrl) return null;
  const separator = rawUrl.includes("?") ? "&" : "?";
  return {
    url: nativeUrl ? rawUrl : `${rawUrl}${separator}t=${Date.now()}`,
    nativeUrl,
    sessionId,
    createdAt: Date.now(),
  };
}

async function readSse(response: Response, onEvent: (event: StreamEvent) => void) {
  if (!response.body) throw new Error("No response body");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() || "";
    for (const chunk of chunks) {
      const line = chunk.split("\n").find((item) => item.startsWith("data: "));
      if (!line) continue;
      onEvent(JSON.parse(line.slice(6)));
    }
  }
}

function App() {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: uid("msg"),
      role: "assistant",
      content: "你好，我是 Robomix。可以直接聊天，也可以通过工具控制 EntroFlow 设备。",
      thinkingCollapsed: true,
    },
  ]);
  const [input, setInput] = useState("");
  const [model, setModel] = useState("deepseek-v4-flash");
  const [models, setModels] = useState<string[]>(["deepseek-v4-flash", "deepseek-v4-pro", "kimi-k2.5"]);
  const [busy, setBusy] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [qrPrompt, setQrPrompt] = useState<QrPrompt | null>(null);
  const [qrAgeSeconds, setQrAgeSeconds] = useState(0);
  const [devices, setDevices] = useState<DeviceRecord[]>([]);
  const [devicesLoading, setDevicesLoading] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const scrollerRef = useRef<HTMLDivElement | null>(null);
  const eventFallbackSeqRef = useRef(0);

  useEffect(() => {
    fetch(`${API_BASE}/api/models`)
      .then((response) => response.json())
      .then((data) => {
        const names = (data.models || [])
          .map((item: { id?: string; name?: string }) => item.id || item.name)
          .filter((item: unknown): item is string => typeof item === "string" && item.length > 0);
        if (names.length) {
          const uniqueNames: string[] = Array.from(new Set<string>(names));
          setModels(uniqueNames);
          setModel(uniqueNames.includes(data.default_model) ? data.default_model : uniqueNames[0]);
        } else if (data.default_model) {
          setModels([data.default_model]);
          setModel(data.default_model);
        }
      })
      .catch(() => undefined);
  }, []);

  async function loadDevices() {
    setDevicesLoading(true);
    try {
      const response = await fetch(`${API_BASE}/api/devices`);
      const data = await response.json();
      setDevices(Array.isArray(data.devices) ? data.devices : []);
    } catch {
      setDevices([]);
    } finally {
      setDevicesLoading(false);
    }
  }

  useEffect(() => {
    void loadDevices();
  }, []);

  useEffect(() => {
    scrollerRef.current?.scrollTo({ top: scrollerRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, busy]);

  useEffect(() => {
    if (!qrPrompt) return;
    setQrAgeSeconds(0);
    const timer = window.setInterval(() => {
      setQrAgeSeconds(Math.floor((Date.now() - qrPrompt.createdAt) / 1000));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [qrPrompt]);

  async function submit(event?: FormEvent) {
    event?.preventDefault();
    const text = input.trim();
    if (!text || busy) return;
    const assistantId = uid("msg");
    setInput("");
    setBusy(true);
    setMessages((current) => [
      ...current,
      { id: uid("msg"), role: "user", content: text },
      {
        id: assistantId,
        role: "assistant",
        content: "",
        thinking: "",
        isStreaming: true,
        streamingThinking: true,
        thinkingCollapsed: false,
        reasoningEvents: [],
      },
    ]);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const response = await fetch(`${API_BASE}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: text,
          model,
          sessionId,
          enableTools: true,
        }),
        signal: controller.signal,
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }

      eventFallbackSeqRef.current = 0;
      await readSse(response, (eventData) => {
        const seq = eventSeq(eventData, ++eventFallbackSeqRef.current);
        if (eventData.type === "start") {
          setMessages((current) =>
            current.map((msg) => (msg.id === assistantId ? { ...msg, thinkingTime: eventData.time || msg.thinkingTime } : msg)),
          );
        }
        if (eventData.type === "thinking_token") {
          setMessages((current) =>
            current.map((msg) =>
              msg.id === assistantId
                ? addReasoningEvent(
                    {
                      ...msg,
                      thinking: `${msg.thinking || ""}${eventData.content || ""}`,
                      streamingThinking: true,
                      isStreaming: true,
                    },
                    { seq, type: "thinking", content: eventData.content || "" },
                  )
                : msg,
            ),
          );
        }
        if (eventData.type === "response_token") {
          setMessages((current) =>
            current.map((msg) =>
              msg.id === assistantId
                ? { ...msg, content: msg.content + (eventData.content || ""), streamingThinking: false, isStreaming: true }
                : msg,
            ),
          );
        }
        if (eventData.type === "tool_use") {
          setMessages((current) =>
            current.map((msg) =>
              msg.id === assistantId
                ? addReasoningEvent(
                    { ...msg, streamingThinking: false, isStreaming: true },
                    { seq, type: "tool_use", name: eventData.name || "tool", arguments: eventData.arguments },
                  )
                : msg,
            ),
          );
        }
        if (eventData.type === "tool_result") {
          const qr = findQrPrompt(eventData.result);
          if (qr) {
            if (qr.nativeUrl) {
              const opened = window.open(qr.nativeUrl, "entroflow-mihome-login", "popup=yes,width=980,height=760");
              setQrPrompt({ ...qr, popupBlocked: !opened });
            } else {
              setQrPrompt(qr);
            }
          }
          setMessages((current) =>
            current.map((msg) =>
              msg.id === assistantId
                ? addReasoningEvent(
                    { ...msg, streamingThinking: false, isStreaming: true },
                    { seq, type: "tool_result", name: eventData.name || "tool", result: eventData.result },
                  )
                : msg,
            ),
          );
          const resultText = stringify(eventData.result);
          if (/device_|setup|list_devices|connect_poll|connected successfully/i.test(resultText)) {
            void loadDevices();
          }
        }
        if (eventData.type === "done" && eventData.answer) {
          setMessages((current) =>
            current.map((msg) =>
              msg.id === assistantId
                ? {
                    ...msg,
                    content: eventData.answer || msg.content || "",
                    thinking: eventData.thinking || msg.thinking || "",
                    thinkingTime: eventData.time || msg.thinkingTime,
                    thinkingCollapsed: true,
                    isStreaming: false,
                    streamingThinking: false,
                  }
                : msg,
            ),
          );
        }
        if (eventData.type === "react_complete") {
          setMessages((current) =>
            current.map((msg) =>
              msg.id === assistantId ? { ...msg, thinkingCollapsed: true, isStreaming: false, streamingThinking: false } : msg,
            ),
          );
        }
        if (eventData.type === "session_id" && eventData.session_id) {
          setSessionId(eventData.session_id);
        }
        if (eventData.type === "error") {
          setMessages((current) =>
            current.map((msg) =>
              msg.id === assistantId
                ? {
                    ...msg,
                    content: `Error: ${eventData.message || "unknown error"}`,
                    isError: true,
                    isStreaming: false,
                    streamingThinking: false,
                    thinkingCollapsed: true,
                  }
                : msg,
            ),
          );
        }
      });
    } catch (error) {
      if ((error as Error).name !== "AbortError") {
        setMessages((current) =>
          current.map((msg) =>
            msg.id === assistantId
              ? {
                  ...msg,
                  content: `Error: ${(error as Error).message}`,
                  isError: true,
                  isStreaming: false,
                  streamingThinking: false,
                  thinkingCollapsed: true,
                }
              : msg,
          ),
        );
      }
    } finally {
      setBusy(false);
      abortRef.current = null;
    }
  }

  function stop() {
    abortRef.current?.abort();
    setBusy(false);
  }

  return (
    <main className="app-shell">
      <div className="workspace">
      <section className="chat-panel">
        <header className="topbar">
          <div className="brand">
            <Bot size={22} />
            <span>Robomix</span>
          </div>
          <div className="controls">
            <label className="model-field">
              <Settings2 size={16} />
              <select value={model} onChange={(event) => setModel(event.target.value)}>
                {models.map((item) => (
                  <option value={item} key={item}>
                    {item}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </header>

        <div className="messages" ref={scrollerRef}>
          {messages.map((message) => (
            <MessageView message={message} key={message.id} />
          ))}
        </div>

        <form className="composer" onSubmit={submit}>
          <textarea
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void submit();
              }
            }}
            placeholder="输入消息..."
            rows={1}
          />
          {busy ? (
            <button type="button" className="icon-button" onClick={stop} title="Stop">
              <CircleStop size={20} />
            </button>
          ) : (
            <button type="submit" className="icon-button" disabled={!input.trim()} title="Send">
              <Send size={20} />
            </button>
          )}
        </form>
      </section>
      <aside className="device-panel">
        <div className="device-panel-header">
          <div>
            <h2>已接入设备</h2>
            <span>{devices.length} devices</span>
          </div>
          <button type="button" className="refresh-button" onClick={() => void loadDevices()} title="Refresh devices">
            <RefreshCw size={16} className={devicesLoading ? "spin" : ""} />
          </button>
        </div>
        <div className="device-list">
          {devices.length === 0 ? (
            <div className="empty-devices">
              <span>暂无设备</span>
              <small>连接平台并 setup 设备后会显示在这里。</small>
            </div>
          ) : (
            devices.map((device, index) => (
              <article className="device-card" key={`${device.platform || "entroflow"}-${device.name || "device"}-${index}`}>
                <div className="device-card-top">
                  <strong>{device.alias || device.name || "Unnamed device"}</strong>
                  <span>{device.platform || device.source || "entroflow"}</span>
                </div>
                <div className={`device-status ${device.status_ok === false ? "error" : "ok"}`}>
                  <div>
                    <span className="status-dot" />
                    <span>{device.status_ok === false ? "状态异常" : "状态"}</span>
                  </div>
                  <p>{device.status_text || "状态未查询"}</p>
                </div>
                {device.remark && <p>{device.remark}</p>}
              </article>
            ))
          )}
        </div>
      </aside>
      </div>
      {qrPrompt && (
        <div className="modal-backdrop" role="dialog" aria-modal="true">
          <div className="qr-modal">
            <button className="modal-close" type="button" onClick={() => setQrPrompt(null)} title="Close">
              <X size={18} />
            </button>
            <h2>米家扫码登录</h2>
            {qrPrompt.nativeUrl && !qrPrompt.popupBlocked ? (
              <div className="native-opened">
                <p>已打开 EntroFlow 原生登录页。</p>
                <p>请在新窗口中扫码并确认登录。</p>
              </div>
            ) : qrPrompt.nativeUrl ? (
              <div className="native-opened">
                <p>浏览器拦截了自动弹窗。</p>
                <p>点击下面按钮打开 EntroFlow 原生登录页。</p>
              </div>
            ) : (
              <img src={qrPrompt.url} alt="Mi Home login QR code" />
            )}
            <p>用米家 App 扫描 EntroFlow 登录页里的二维码，并在手机上确认登录。</p>
            <small>生成于 {qrAgeSeconds} 秒前，二维码通常只保持当前会话有效。</small>
            {qrPrompt.sessionId && <code>session_id: {qrPrompt.sessionId}</code>}
            <a href={qrPrompt.url} target="_blank" rel="noreferrer">
              <ExternalLink size={15} />
              打开 EntroFlow 原生登录页
            </a>
          </div>
        </div>
      )}
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
