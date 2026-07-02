import {
  App,
  Button,
  Card,
  Col,
  Descriptions,
  Modal,
  Row,
  Space,
  Steps,
  Table,
  Tag,
  Timeline,
  Typography,
} from 'antd'
import dayjs from 'dayjs'
import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api, ApprovalRequest, AuditEntry, Page } from '../api'
import { useAuth } from '../auth'
import { STATUS_COLORS } from './RequestsPage'

const STEP_STATUS: Record<string, 'wait' | 'process' | 'finish' | 'error'> = {
  pending: 'wait',
  active: 'process',
  approved: 'finish',
  rejected: 'error',
  skipped: 'wait',
}

export default function RequestDetailPage() {
  const { id } = useParams()
  const { user } = useAuth()
  const { message } = App.useApp()
  const [request, setRequest] = useState<ApprovalRequest | null>(null)
  const [audit, setAudit] = useState<AuditEntry[]>([])

  const load = useCallback(() => {
    api.get<ApprovalRequest>(`/requests/${id}`).then((r) => setRequest(r.data))
    api
      .get<Page<AuditEntry>>('/audit', { params: { request_id: id, size: 100 } })
      .then((r) => setAudit([...r.data.items].reverse()))
      .catch(() => setAudit([]))
  }, [id])

  useEffect(load, [load])

  if (!request) return null

  const cancel = () =>
    Modal.confirm({
      title: 'Cancel this request?',
      onOk: async () => {
        try {
          await api.post(`/requests/${request.id}/cancel`)
          message.success('Request cancelled')
          load()
        } catch (e: any) {
          message.error(e.response?.data?.detail ?? 'Failed to cancel')
        }
      },
    })

  const canCancel =
    (user?.id === request.requester.id || user?.role === 'admin') &&
    ['pending', 'changes_requested'].includes(request.status)

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <Card
        title={`Request #${request.id} — ${request.title}`}
        extra={
          <Space>
            <Tag color={STATUS_COLORS[request.status]}>{request.status.replace('_', ' ')}</Tag>
            {canCancel && <Button onClick={cancel}>Cancel request</Button>}
          </Space>
        }
      >
        <Descriptions size="small" column={2}>
          <Descriptions.Item label="Requester">{request.requester.name}</Descriptions.Item>
          <Descriptions.Item label="Amount">
            {request.amount != null ? `$${Number(request.amount).toLocaleString()}` : '—'}
          </Descriptions.Item>
          <Descriptions.Item label="Submitted">
            {dayjs(request.created_at).format('MMM D, YYYY HH:mm')}
          </Descriptions.Item>
          <Descriptions.Item label="Description">{request.description || '—'}</Descriptions.Item>
          {Object.entries(request.data ?? {}).map(([key, value]) => (
            <Descriptions.Item key={key} label={key}>
              {String(value)}
            </Descriptions.Item>
          ))}
        </Descriptions>
      </Card>

      <Row gutter={16}>
        <Col span={14}>
          <Card title="Approval steps">
            <Steps
              direction="vertical"
              items={(request.steps ?? []).map((step) => ({
                title: (
                  <Space>
                    {step.name}
                    {step.status === 'skipped' && <Tag>skipped by condition</Tag>}
                    {step.escalated && <Tag color="red">escalated</Tag>}
                  </Space>
                ),
                status: STEP_STATUS[step.status],
                description: (
                  <div>
                    {step.approvers.map((a) => (
                      <Tag
                        key={a.id}
                        color={a.status === 'approved' ? 'green' : a.status === 'rejected' ? 'red' : 'default'}
                      >
                        {a.approver.name}
                        {a.is_escalation ? ' (escalation)' : ''}: {a.status}
                      </Tag>
                    ))}
                    {step.due_at && step.status === 'active' && (
                      <Typography.Text type="secondary"> due {dayjs(step.due_at).format('MMM D, HH:mm')}</Typography.Text>
                    )}
                  </div>
                ),
              }))}
            />
            {!!request.decisions?.length && (
              <Table
                size="small"
                rowKey="id"
                title={() => 'Decisions'}
                pagination={false}
                dataSource={request.decisions}
                columns={[
                  { title: 'Decision', render: (_, d) => <Tag>{d.decision.replace('_', ' ')}</Tag> },
                  {
                    title: 'By',
                    render: (_, d) =>
                      d.acting_user.id === d.approver.id
                        ? d.approver.name
                        : `${d.acting_user.name} (for ${d.approver.name})`,
                  },
                  { title: 'Comment', dataIndex: 'comment' },
                  { title: 'At', render: (_, d) => dayjs(d.created_at).format('MMM D, HH:mm') },
                ]}
              />
            )}
          </Card>
        </Col>
        <Col span={10}>
          <Card title="Audit trail">
            <Timeline
              items={audit.map((entry) => ({
                children: (
                  <>
                    <Typography.Text strong>{entry.action.replace(/_/g, ' ')}</Typography.Text>
                    {entry.actor && <Typography.Text> — {entry.actor.name}</Typography.Text>}
                    <br />
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                      {dayjs(entry.created_at).format('MMM D, YYYY HH:mm:ss')}
                    </Typography.Text>
                  </>
                ),
              }))}
            />
          </Card>
        </Col>
      </Row>
    </Space>
  )
}
