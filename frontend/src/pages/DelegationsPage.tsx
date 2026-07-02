import { App, Button, Card, DatePicker, Form, Input, Modal, Select, Table, Tag } from 'antd'
import dayjs from 'dayjs'
import { useCallback, useEffect, useState } from 'react'
import { api, Delegation, Page, User } from '../api'
import { useAuth } from '../auth'

export default function DelegationsPage() {
  const { user } = useAuth()
  const { message } = App.useApp()
  const [delegations, setDelegations] = useState<Delegation[]>([])
  const [users, setUsers] = useState<User[]>([])
  const [open, setOpen] = useState(false)
  const [form] = Form.useForm()

  const load = useCallback(() => {
    api.get<Page<Delegation>>('/delegations', { params: { size: 100 } }).then((r) => setDelegations(r.data.items))
  }, [])

  useEffect(load, [load])
  useEffect(() => {
    api.get<Page<User>>('/users', { params: { size: 100 } }).then((r) => setUsers(r.data.items))
  }, [])

  const create = async (values: any) => {
    try {
      await api.post('/delegations', {
        delegate_id: values.delegate_id,
        starts_at: values.period[0].toISOString(),
        ends_at: values.period[1].toISOString(),
        reason: values.reason,
      })
      message.success('Delegation created')
      setOpen(false)
      form.resetFields()
      load()
    } catch (e: any) {
      message.error(e.response?.data?.detail ?? 'Failed to create delegation')
    }
  }

  const revoke = async (delegation: Delegation) => {
    try {
      await api.delete(`/delegations/${delegation.id}`)
      message.success('Delegation revoked')
      load()
    } catch (e: any) {
      message.error(e.response?.data?.detail ?? 'Failed to revoke')
    }
  }

  return (
    <Card
      title="Delegations"
      extra={
        <Button type="primary" onClick={() => setOpen(true)}>
          Delegate my approvals
        </Button>
      }
    >
      <Table
        rowKey="id"
        dataSource={delegations}
        pagination={false}
        columns={[
          { title: 'Delegator', render: (_, d) => d.delegator.name },
          { title: 'Delegate', render: (_, d) => d.delegate.name },
          {
            title: 'Window',
            render: (_, d) =>
              `${dayjs(d.starts_at).format('MMM D, HH:mm')} → ${dayjs(d.ends_at).format('MMM D, HH:mm')}`,
          },
          { title: 'Reason', dataIndex: 'reason' },
          {
            title: 'Status',
            render: (_, d) => {
              const now = dayjs()
              const active = d.is_active && now.isAfter(d.starts_at) && now.isBefore(d.ends_at)
              return d.is_active ? (
                <Tag color={active ? 'green' : 'blue'}>{active ? 'active now' : 'scheduled'}</Tag>
              ) : (
                <Tag>revoked</Tag>
              )
            },
          },
          {
            title: 'Actions',
            render: (_, d) =>
              d.is_active && d.delegator.id === user?.id ? (
                <Button size="small" danger onClick={() => revoke(d)}>
                  Revoke
                </Button>
              ) : null,
          },
        ]}
      />
      <Modal open={open} title="Delegate my approval authority" onCancel={() => setOpen(false)} onOk={form.submit}>
        <Form form={form} layout="vertical" onFinish={create}>
          <Form.Item name="delegate_id" label="Delegate to" rules={[{ required: true }]}>
            <Select
              showSearch
              optionFilterProp="label"
              options={users
                .filter((u) => u.id !== user?.id)
                .map((u) => ({ value: u.id, label: `${u.name} (${u.role})` }))}
            />
          </Form.Item>
          <Form.Item name="period" label="Period" rules={[{ required: true }]}>
            <DatePicker.RangePicker showTime style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="reason" label="Reason">
            <Input placeholder="e.g. Vacation" />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  )
}
