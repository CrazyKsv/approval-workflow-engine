import { RobotOutlined, SendOutlined, ToolOutlined, UserOutlined } from '@ant-design/icons'
import { Avatar, Button, Card, Collapse, Input, Space, Spin, Tag, Typography } from 'antd'
import { useEffect, useRef, useState } from 'react'
import { api, ChatResponse, ToolEvent } from '../api'
import { useAuth } from '../auth'

interface Message {
  role: 'user' | 'assistant'
  content: string
  toolEvents?: ToolEvent[]
}

const SUGGESTIONS = [
  'I need approval for a $5,000 laptop purchase',
  'What requests are waiting for my approval?',
  'Show me the status of my requests',
  'Delegate my approvals to Mike for next week',
]

function ToolTrace({ events }: { events: ToolEvent[] }) {
  if (!events.length) return null
  return (
    <Collapse
      size="small"
      style={{ marginTop: 8 }}
      items={[
        {
          key: 'trace',
          label: (
            <Space>
              <ToolOutlined />
              {events.length} tool call{events.length > 1 ? 's' : ''}
              {events.some((e) => e.error) && <Tag color="red">errors</Tag>}
            </Space>
          ),
          children: events.map((event, i) => (
            <div key={i} style={{ marginBottom: 8 }}>
              <Space>
                <Tag color={event.error ? 'red' : event.result?.status === 'confirmation_required' ? 'orange' : 'blue'}>
                  {event.tool_name}
                </Tag>
                {event.latency_ms != null && (
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    {event.latency_ms} ms
                  </Typography.Text>
                )}
              </Space>
              <pre style={{ fontSize: 11, background: '#fafafa', padding: 8, overflowX: 'auto', margin: '4px 0' }}>
                {JSON.stringify({ arguments: event.arguments, result: event.result }, null, 2)}
              </pre>
            </div>
          )),
        },
      ]}
    />
  )
}

export default function ChatPage() {
  const { user } = useAuth()
  const [messages, setMessages] = useState<Message[]>([])
  const [conversationId, setConversationId] = useState<number | null>(null)
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, busy])

  const send = async (text?: string) => {
    const content = (text ?? input).trim()
    if (!content || busy) return
    setInput('')
    setMessages((m) => [...m, { role: 'user', content }])
    setBusy(true)
    try {
      const r = await api.post<ChatResponse>('/agent/chat', {
        message: content,
        conversation_id: conversationId ?? undefined,
      })
      setConversationId(r.data.conversation_id)
      setMessages((m) => [
        ...m,
        { role: 'assistant', content: r.data.reply, toolEvents: r.data.tool_events },
      ])
    } catch (e: any) {
      setMessages((m) => [
        ...m,
        { role: 'assistant', content: e.response?.data?.detail ?? 'Something went wrong. Please try again.' },
      ])
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card
      title="AI Workflow Assistant"
      extra={
        conversationId && (
          <Button
            size="small"
            onClick={() => {
              setMessages([])
              setConversationId(null)
            }}
          >
            New conversation
          </Button>
        )
      }
      styles={{ body: { display: 'flex', flexDirection: 'column', height: 'calc(100vh - 180px)' } }}
    >
      <div style={{ flex: 1, overflowY: 'auto', paddingRight: 8 }}>
        {messages.length === 0 && (
          <div style={{ textAlign: 'center', marginTop: 60 }}>
            <RobotOutlined style={{ fontSize: 40, color: '#2f54eb' }} />
            <Typography.Paragraph type="secondary" style={{ marginTop: 12 }}>
              Hi {user?.name?.split(' ')[0]} — I can submit requests, review your pending approvals,
              record decisions, and manage delegations. Try one of these:
            </Typography.Paragraph>
            <Space direction="vertical">
              {SUGGESTIONS.map((s) => (
                <Button key={s} onClick={() => send(s)}>
                  {s}
                </Button>
              ))}
            </Space>
          </div>
        )}
        {messages.map((msg, i) => (
          <div
            key={i}
            style={{
              display: 'flex',
              justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
              marginBottom: 12,
            }}
          >
            <Space align="start">
              {msg.role === 'assistant' && <Avatar icon={<RobotOutlined />} style={{ background: '#2f54eb' }} />}
              <div
                style={{
                  maxWidth: 640,
                  padding: '8px 12px',
                  borderRadius: 8,
                  background: msg.role === 'user' ? '#2f54eb' : '#f5f5f5',
                  color: msg.role === 'user' ? '#fff' : 'inherit',
                  whiteSpace: 'pre-wrap',
                }}
              >
                {msg.content}
                {msg.toolEvents && <ToolTrace events={msg.toolEvents} />}
              </div>
              {msg.role === 'user' && <Avatar icon={<UserOutlined />} />}
            </Space>
          </div>
        ))}
        {busy && <Spin style={{ display: 'block', margin: '12px auto' }} />}
        <div ref={bottomRef} />
      </div>
      <Space.Compact block style={{ marginTop: 12 }}>
        <Input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onPressEnter={() => send()}
          placeholder="Ask me to submit a request, review approvals, approve something…"
          disabled={busy}
        />
        <Button type="primary" icon={<SendOutlined />} onClick={() => send()} loading={busy}>
          Send
        </Button>
      </Space.Compact>
    </Card>
  )
}
