import { useEffect, useRef, useState } from "react";

import { DeleteOutlined, PlusOutlined, RobotOutlined, SearchOutlined, SendOutlined, StopOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Empty, Input, Popconfirm, Skeleton, Tag, Typography } from "antd";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { apiClient } from "@/api/client";
import { showError } from "@/api/errors";
import type { components } from "@/api/schema";
import { PageHeader } from "@/components/ui";
import { useAuthStore } from "@/stores/authStore";

type Status = components["schemas"]["AssistantStatus"];
type Summary = components["schemas"]["ConversationSummary"];
type Exchange = components["schemas"]["Exchange"];
type ToolCall = components["schemas"]["ToolCall"];

/** One server-sent event of POST /assistant/ask (app/api/v1/assistant.py) */
type AskEvent =
  | { type: "conversation"; id: string }
  | { type: "text"; text: string }
  | { type: "tool"; name: string; label: string }
  | { type: "tool_done"; name: string; rows: number | null; error: string | null }
  | { type: "done"; usage: Record<string, number> }
  | { type: "error"; message: string };

const SUGGESTIONS = [
  "What expires in the next 30 days, and where is it?",
  "Which sales orders are short, and could they be covered now?",
  "What did we receive and ship today?",
  "Which zones are nearly full?",
];

/** POST and read the answer as it streams (EventSource cannot POST or send the sign-in header) */
async function streamAnswer(body: object, onEvent: (event: AskEvent) => void, signal: AbortSignal) {
  const token = useAuthStore.getState().token;
  const response = await fetch("/api/v1/assistant/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}`, Accept: "text/event-stream" },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok || !response.body) {
    const detail = await response.json().catch(() => null);
    throw new Error(detail?.detail ?? `The assistant is unavailable (${response.status})`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) return;
    buffer += decoder.decode(value, { stream: true });
    let end: number;
    while ((end = buffer.indexOf("\n\n")) >= 0) {
      const line = buffer.slice(0, end);
      buffer = buffer.slice(end + 2);
      if (line.startsWith("data: ")) onEvent(JSON.parse(line.slice(6)) as AskEvent);
    }
  }
}

function ToolChip({ call }: { call: ToolCall & { running?: boolean } }) {
  const detail = call.running ? "…" : call.error ? "failed" : call.rows != null ? `${call.rows} row${call.rows === 1 ? "" : "s"}` : "done";
  return (
    <Tag icon={<SearchOutlined />} color={call.error ? "error" : "default"} title={call.error ?? undefined} className="wms-ai-tool">
      {call.label} · {detail}
    </Tag>
  );
}

function ExchangeView({ exchange, streaming }: { exchange: Exchange & { error?: string }; streaming?: boolean }) {
  return (
    <div className="wms-ai-exchange">
      <div className="wms-ai-question">{exchange.question}</div>
      {exchange.tools.length > 0 && (
        <div className="wms-ai-tools">
          {exchange.tools.map((call, i) => (
            <ToolChip key={i} call={call} />
          ))}
        </div>
      )}
      <div className="wms-ai-answer" data-testid="ai-answer">
        {exchange.answer ? (
          <Markdown remarkPlugins={[remarkGfm]}>{exchange.answer}</Markdown>
        ) : (
          streaming && !exchange.error && <Typography.Text type="secondary">Thinking…</Typography.Text>
        )}
      </div>
      {exchange.error && <Alert type="warning" showIcon title={exchange.error} />}
    </div>
  );
}

export default function AssistantPage() {
  const queryClient = useQueryClient();
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [live, setLive] = useState<(Exchange & { error?: string }) | null>(null);
  const [question, setQuestion] = useState("");
  const abort = useRef<AbortController | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  const { data: status } = useQuery({
    queryKey: ["assistant", "status"],
    queryFn: async () => (await apiClient.get<Status>("/assistant/status")).data,
  });
  const available = !!status?.available;
  const { data: conversations } = useQuery({
    queryKey: ["assistant", "conversations"],
    queryFn: async () => (await apiClient.get<Summary[]>("/assistant/conversations")).data,
    enabled: available,
  });
  const { data: transcript, isLoading: loadingTranscript } = useQuery({
    queryKey: ["assistant", "conversation", conversationId],
    queryFn: async () => (await apiClient.get<{ exchanges: Exchange[] }>(`/assistant/conversations/${conversationId}`)).data,
    enabled: available && !!conversationId,
  });
  const remove = useMutation({
    mutationFn: async (id: string) => apiClient.delete(`/assistant/conversations/${id}`),
    onSuccess: (_, id) => {
      if (id === conversationId) setConversationId(null);
      void queryClient.invalidateQueries({ queryKey: ["assistant", "conversations"] });
    },
    onError: showError,
  });

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "end" });
  }, [live, transcript]);

  const ask = async (text: string) => {
    const asked = text.trim();
    if (!asked || live) return;
    setQuestion("");
    const exchange: Exchange & { error?: string } = { question: asked, answer: "", tools: [] };
    setLive({ ...exchange });
    abort.current = new AbortController();
    let id = conversationId;
    const update = (change: (e: typeof exchange) => void) => {
      change(exchange);
      setLive({ ...exchange, tools: [...exchange.tools] });
    };
    try {
      await streamAnswer(
        { question: asked, conversation_id: conversationId },
        (event) => {
          if (event.type === "conversation") id = event.id;
          else if (event.type === "text") update((e) => (e.answer += event.text));
          else if (event.type === "tool") update((e) => e.tools.push({ label: event.label, rows: null, error: null, running: true } as ToolCall));
          else if (event.type === "tool_done")
            update((e) => {
              const call = e.tools[e.tools.length - 1] as ToolCall & { running?: boolean };
              Object.assign(call, { rows: event.rows, error: event.error, running: false });
            });
          else if (event.type === "error") update((e) => (e.error = event.message));
        },
        abort.current.signal,
      );
    } catch (error) {
      if (!abort.current?.signal.aborted) update((e) => (e.error = error instanceof Error ? error.message : "The question could not be sent"));
    }
    // Show the stored conversation; a failed answer stays on screen until the next question
    if (id) {
      if (id !== conversationId) setConversationId(id);
      await queryClient.invalidateQueries({ queryKey: ["assistant", "conversation", id] });
    }
    void queryClient.invalidateQueries({ queryKey: ["assistant"] });
    if (!exchange.error) setLive(null);
    else setLive({ ...exchange, answer: exchange.answer });
    abort.current = null;
  };

  const header = (
    <PageHeader title="AI assistant" description="Ask about stock, documents and reports in plain language. It can look things up; it cannot change anything." />
  );
  if (!status) return <Skeleton active />;
  if (!available) {
    return (
      <>
        {header}
        <Alert type="info" showIcon title="The AI assistant is not available" description={status.reason} />
      </>
    );
  }

  const shown = (transcript?.exchanges ?? []).filter((e) => !(live && live.error === undefined && e.question === live.question));
  const usage = status.daily_token_budget ? Math.round((status.tokens_today / status.daily_token_budget) * 100) : null;

  return (
    <>
      {header}
      <div className="wms-ai">
        <aside className="wms-ai-list">
          <Button block icon={<PlusOutlined />} onClick={() => setConversationId(null)} disabled={!!live}>
            New conversation
          </Button>
          {conversations?.map((c) => (
            <div key={c.id} className={`wms-ai-item${c.id === conversationId ? " wms-ai-item-active" : ""}`}>
              <button type="button" onClick={() => !live && setConversationId(c.id)}>
                {c.title}
              </button>
              <Popconfirm title="Delete this conversation?" onConfirm={() => remove.mutate(c.id)}>
                <Button type="text" size="small" icon={<DeleteOutlined />} aria-label={`Delete ${c.title}`} />
              </Popconfirm>
            </div>
          ))}
        </aside>

        <section className="wms-ai-chat">
          <div className="wms-ai-transcript" data-testid="ai-transcript">
            {conversationId && loadingTranscript && <Skeleton active />}
            {!conversationId && !live && (
              <Empty image={<RobotOutlined className="wms-ai-empty-icon" />} description="Ask a question, or start with one of these">
                <div className="wms-ai-suggestions">
                  {SUGGESTIONS.map((s) => (
                    <Button key={s} onClick={() => void ask(s)}>
                      {s}
                    </Button>
                  ))}
                </div>
              </Empty>
            )}
            {shown.map((e, i) => (
              <ExchangeView key={i} exchange={e} />
            ))}
            {live && <ExchangeView exchange={live} streaming />}
            <div ref={bottom} />
          </div>

          <div className="wms-ai-composer">
            <Input.TextArea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onPressEnter={(e) => {
                if (!e.shiftKey) {
                  e.preventDefault();
                  void ask(question);
                }
              }}
              placeholder="e.g. Where is SKU A100 and how much is free?  (Enter to send, Shift+Enter for a new line)"
              autoSize={{ minRows: 1, maxRows: 6 }}
              maxLength={2000}
              disabled={!!live}
              aria-label="Question"
            />
            {live ? (
              <Button icon={<StopOutlined />} onClick={() => abort.current?.abort()} aria-label="Stop">
                Stop
              </Button>
            ) : (
              <Button type="primary" icon={<SendOutlined />} onClick={() => void ask(question)} disabled={!question.trim()} aria-label="Send">
                Send
              </Button>
            )}
          </div>
          <Typography.Text type="secondary" className="wms-ai-footnote">
            Answers come from {status.model} and may be wrong: check important figures on the screens they mention.
            {usage !== null && ` Today's AI usage for your company: ${usage}% of the daily limit.`}
          </Typography.Text>
        </section>
      </div>
    </>
  );
}
