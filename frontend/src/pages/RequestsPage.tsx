import { App, Button, Card, DatePicker, Form, Input, InputNumber, Modal, Select, Switch, Table, Tag } from 'antd'
import dayjs from 'dayjs'
import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, ApprovalRequest, Page, Template } from '../api'

export const STATUS_COLORS: Record<string, string> = {
  pending: 'processing',
  approved: 'success',
  rejected: 'error',
  changes_requested: 'warning',
  cancelled: 'default',
}

export default function RequestsPage() {
  const { message } = App.useApp()
  const [requests, setRequests] = useState<ApprovalRequest[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [templates, setTemplates] = useState<Template[]>([])
  const [open, setOpen] = useState(false)
  const [selected, setSelected] = useState<Template | null>(null)
  const [form] = Form.useForm()

  const load = useCallback(() => {
    setLoading(true)
    api
      .get<Page<ApprovalRequest>>('/requests', { params: { page, size: 10 } })
      .then((r) => {
        setRequests(r.data.items)
        setTotal(r.data.total)
      })
      .finally(() => setLoading(false))
  }, [page])

  useEffect(load, [load])
  useEffect(() => {
    api.get<Page<Template>>('/templates', { params: { size: 100 } }).then((r) => setTemplates(r.data.items))
  }, [])

  const submit = async (values: Record<string, unknown>) => {
    const { template_id, title, description, ...fields } = values
    const data: Record<string, unknown> = {}
    let amount: number | undefined
    for (const field of selected?.fields ?? []) {
      let value = fields[field.name]
      if (value === undefined || value === null || value === '') continue
      if (field.type === 'date' && dayjs.isDayjs(value)) value = value.format('YYYY-MM-DD')
      if (field.name === 'amount') amount = Number(value)
      else data[field.name] = value
    }
    try {
      await api.post('/requests', { template_id, title, description, amount, data })
      message.success('Request submitted')
      setOpen(false)
      form.resetFields()
      load()
    } catch (e: any) {
      message.error(e.response?.data?.detail ?? 'Submission failed')
    }
  }

  return (
    <Card
      title="My Requests"
      extra={
        <Button type="primary" onClick={() => setOpen(true)}>
          New Request
        </Button>
      }
    >
      <Table
        rowKey="id"
        loading={loading}
        dataSource={requests}
        pagination={{ current: page, total, pageSize: 10, onChange: setPage }}
        columns={[
          {
            title: 'Request',
            render: (_, r) => (
              <Link to={`/requests/${r.id}`}>
                #{r.id} — {r.title}
              </Link>
            ),
          },
          {
            title: 'Amount',
            render: (_, r) => (r.amount != null ? `$${Number(r.amount).toLocaleString()}` : '—'),
          },
          {
            title: 'Status',
            render: (_, r) => <Tag color={STATUS_COLORS[r.status]}>{r.status.replace('_', ' ')}</Tag>,
          },
          { title: 'Submitted', render: (_, r) => dayjs(r.created_at).format('MMM D, YYYY HH:mm') },
        ]}
      />
      <Modal
        open={open}
        title="Submit a new request"
        onCancel={() => setOpen(false)}
        onOk={form.submit}
        okText="Submit"
        destroyOnClose
      >
        <Form form={form} layout="vertical" onFinish={submit} preserve={false}>
          <Form.Item name="template_id" label="Workflow" rules={[{ required: true }]}>
            <Select
              placeholder="Choose a workflow"
              options={templates.map((t) => ({ value: t.id, label: t.name }))}
              onChange={(id) => setSelected(templates.find((t) => t.id === id) ?? null)}
            />
          </Form.Item>
          <Form.Item name="title" label="Title" rules={[{ required: true }]}>
            <Input placeholder="e.g. Laptop purchase for new hire" />
          </Form.Item>
          <Form.Item name="description" label="Description">
            <Input.TextArea rows={2} />
          </Form.Item>
          {selected?.fields.map((field) => (
            <Form.Item
              key={field.name}
              name={field.name}
              label={field.label}
              rules={[{ required: field.required }]}
              valuePropName={field.type === 'boolean' ? 'checked' : 'value'}
            >
              {field.type === 'number' ? (
                <InputNumber style={{ width: '100%' }} min={0} />
              ) : field.type === 'date' ? (
                <DatePicker style={{ width: '100%' }} />
              ) : field.type === 'boolean' ? (
                <Switch />
              ) : (
                <Input />
              )}
            </Form.Item>
          ))}
        </Form>
      </Modal>
    </Card>
  )
}
