import { App, Button, Card, Input, List, Modal, Space, Table, Tag, Typography } from 'antd'
import dayjs from 'dayjs'
import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, InboxItem, Page, StatusFeedItem } from '../api'
import { useAuth } from '../auth'
import { STATUS_COLORS } from './RequestsPage'

type DecisionKind = 'approved' | 'rejected' | 'changes_requested'

export default function InboxPage() {
  const { message } = App.useApp()
  const { user } = useAuth()
  const isApprover = ['manager', 'finance', 'vp'].includes(user?.role ?? '')
  const [items, setItems] = useState<InboxItem[]>([])
  const [feed, setFeed] = useState<StatusFeedItem[]>([])
  const [loading, setLoading] = useState(false)
  const [decideItem, setDecideItem] = useState<{ item: InboxItem; kind: DecisionKind } | null>(null)
  const [comment, setComment] = useState('')

  const load = useCallback(() => {
    setLoading(true)
    const calls: Promise<unknown>[] = [
      api.get<StatusFeedItem[]>('/inbox/status').then((r) => setFeed(r.data)),
    ]
    if (isApprover) {
      calls.push(api.get<Page<InboxItem>>('/inbox', { params: { size: 100 } }).then((r) => setItems(r.data.items)))
    }
    Promise.all(calls).finally(() => setLoading(false))
  }, [isApprover])

  useEffect(load, [load])

  const decide = async () => {
    if (!decideItem) return
    try {
      await api.post(`/requests/${decideItem.item.request.id}/decision`, {
        decision: decideItem.kind,
        comment: comment || undefined,
      })
      message.success(`Decision recorded: ${decideItem.kind.replace('_', ' ')}`)
      setDecideItem(null)
      setComment('')
      load()
    } catch (e: any) {
      message.error(e.response?.data?.detail ?? 'Failed to record decision')
    }
  }

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      {isApprover && (
        <Card title="Waiting for your decision" extra={<Button onClick={load}>Refresh</Button>}>
          <Table
        rowKey={(item) => `${item.request.id}-${item.step.id}-${item.on_behalf_of?.id ?? 'me'}`}
        loading={loading}
        dataSource={items}
        pagination={{ pageSize: 10 }}
        columns={[
          {
            title: 'Request',
            render: (_, { request }) => (
              <Link to={`/requests/${request.id}`}>
                #{request.id} — {request.title}
              </Link>
            ),
          },
          { title: 'Requester', render: (_, { request }) => request.requester.name },
          {
            title: 'Amount',
            render: (_, { request }) =>
              request.amount != null ? `$${Number(request.amount).toLocaleString()}` : '—',
          },
          {
            title: 'Step',
            render: (_, { step }) => (
              <Space>
                {step.name}
                {step.escalated && <Tag color="red">escalated</Tag>}
                <Tag>{step.approval_mode === 'all' ? 'all must approve' : 'any approver'}</Tag>
              </Space>
            ),
          },
          {
            title: 'Waiting since',
            render: (_, { step }) => (step.activated_at ? dayjs(step.activated_at).format('MMM D, HH:mm') : '—'),
          },
          {
            title: 'Authority',
            render: (_, { on_behalf_of }) =>
              on_behalf_of ? <Tag color="orange">for {on_behalf_of.name}</Tag> : <Tag color="blue">own</Tag>,
          },
          {
            title: 'Actions',
            render: (_, item) => (
              <Space>
                <Button type="primary" size="small" onClick={() => setDecideItem({ item, kind: 'approved' })}>
                  Approve
                </Button>
                <Button danger size="small" onClick={() => setDecideItem({ item, kind: 'rejected' })}>
                  Reject
                </Button>
                <Button size="small" onClick={() => setDecideItem({ item, kind: 'changes_requested' })}>
                  Request changes
                </Button>
              </Space>
            ),
          },
        ]}
          />
          <Modal
            open={!!decideItem}
            title={`Confirm: ${decideItem?.kind.replace('_', ' ')} — ${decideItem?.item.request.title}`}
            onOk={decide}
            onCancel={() => setDecideItem(null)}
            okText="Confirm decision"
          >
            <Typography.Paragraph>
              {decideItem?.item.on_behalf_of &&
                `You are acting on behalf of ${decideItem.item.on_behalf_of.name} (delegated). `}
              Add an optional comment:
            </Typography.Paragraph>
            <Input.TextArea rows={3} value={comment} onChange={(e) => setComment(e.target.value)} />
          </Modal>
        </Card>
      )}

      <Card
        title="My request status"
        extra={!isApprover && <Button onClick={load}>Refresh</Button>}
        loading={loading && feed.length === 0}
      >
        <List
          dataSource={feed}
          locale={{ emptyText: 'You have not submitted any requests yet' }}
          renderItem={(item) => (
            <List.Item
              actions={[
                <Tag key="status" color={STATUS_COLORS[item.request.status]}>
                  {item.request.status.replace('_', ' ')}
                </Tag>,
              ]}
            >
              <List.Item.Meta
                title={
                  <Link to={`/requests/${item.request.id}`}>
                    #{item.request.id} — {item.request.title}
                  </Link>
                }
                description={item.message.charAt(0).toUpperCase() + item.message.slice(1)}
              />
            </List.Item>
          )}
        />
      </Card>
    </Space>
  )
}
