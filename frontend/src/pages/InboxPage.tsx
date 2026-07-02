import { App, Button, Card, Input, Modal, Space, Table, Tag, Typography } from 'antd'
import dayjs from 'dayjs'
import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, InboxItem, Page } from '../api'

type DecisionKind = 'approved' | 'rejected' | 'changes_requested'

export default function InboxPage() {
  const { message } = App.useApp()
  const [items, setItems] = useState<InboxItem[]>([])
  const [loading, setLoading] = useState(false)
  const [decideItem, setDecideItem] = useState<{ item: InboxItem; kind: DecisionKind } | null>(null)
  const [comment, setComment] = useState('')

  const load = useCallback(() => {
    setLoading(true)
    api
      .get<Page<InboxItem>>('/inbox', { params: { size: 100 } })
      .then((r) => setItems(r.data.items))
      .finally(() => setLoading(false))
  }, [])

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
    <Card title="Approval Inbox" extra={<Button onClick={load}>Refresh</Button>}>
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
  )
}
