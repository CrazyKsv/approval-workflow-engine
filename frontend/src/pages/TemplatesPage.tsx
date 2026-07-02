import { MinusCircleOutlined, PlusOutlined } from '@ant-design/icons'
import {
  App,
  Button,
  Card,
  Checkbox,
  Collapse,
  Divider,
  Form,
  Input,
  InputNumber,
  Modal,
  Select,
  Space,
  Switch,
  Table,
  Tag,
} from 'antd'
import { useCallback, useEffect, useState } from 'react'
import { api, Page, Template, User } from '../api'

const ROLES = ['admin', 'manager', 'finance', 'vp', 'employee']
const OPS = ['==', '!=', '>', '>=', '<', '<=', 'in', 'not_in', 'contains']

export default function TemplatesPage() {
  const { message } = App.useApp()
  const [templates, setTemplates] = useState<Template[]>([])
  const [users, setUsers] = useState<User[]>([])
  const [groups, setGroups] = useState<{ id: number; name: string }[]>([])
  const [open, setOpen] = useState(false)
  const [form] = Form.useForm()

  const load = useCallback(() => {
    api
      .get<Page<Template>>('/templates', { params: { size: 100, include_inactive: true } })
      .then((r) => setTemplates(r.data.items))
  }, [])

  useEffect(load, [load])
  useEffect(() => {
    api.get<Page<User>>('/users', { params: { size: 100 } }).then((r) => setUsers(r.data.items))
    api.get<Page<{ id: number; name: string }>>('/groups', { params: { size: 100 } }).then((r) => setGroups(r.data.items))
  }, [])

  const toggleActive = async (template: Template) => {
    await api.patch(`/templates/${template.id}`, { is_active: !template.is_active })
    load()
  }

  const create = async (values: any) => {
    const payload = {
      name: values.name,
      description: values.description,
      category: values.category,
      fields: (values.fields ?? []).map((f: any) => ({ ...f, required: !!f.required })),
      steps: (values.steps ?? []).map((s: any, index: number) => ({
        step_order: index + 1,
        name: s.name,
        approver_type: s.approver_type,
        approver_user_id: s.approver_type === 'user' ? s.approver_user_id : undefined,
        approver_group_id: s.approver_type === 'group' ? s.approver_group_id : undefined,
        approver_role: s.approver_type === 'role' ? s.approver_role : undefined,
        approval_mode: s.approval_mode ?? 'any',
        condition: s.condition_field
          ? { field: s.condition_field, op: s.condition_op, value: isNaN(Number(s.condition_value)) ? s.condition_value : Number(s.condition_value) }
          : undefined,
        sla_hours: s.sla_hours || undefined,
        escalation_role: s.escalation_role || undefined,
      })),
    }
    try {
      await api.post('/templates', payload)
      message.success('Template created')
      setOpen(false)
      form.resetFields()
      load()
    } catch (e: any) {
      const detail = e.response?.data?.detail
      message.error(typeof detail === 'string' ? detail : 'Validation failed — check the step definitions')
    }
  }

  return (
    <Card
      title="Workflow Templates"
      extra={
        <Button type="primary" onClick={() => setOpen(true)}>
          New Template
        </Button>
      }
    >
      <Table
        rowKey="id"
        dataSource={templates}
        pagination={false}
        expandable={{
          expandedRowRender: (t) => (
            <Collapse
              size="small"
              items={[
                {
                  key: 'steps',
                  label: 'Steps & routing',
                  children: (
                    <ol>
                      {t.steps.map((s) => (
                        <li key={s.id}>
                          <b>{s.name}</b> — {s.approver_type}
                          {s.approver_role ? `: ${s.approver_role}` : ''}
                          {s.approver_group_id ? `: ${groups.find((g) => g.id === s.approver_group_id)?.name ?? s.approver_group_id}` : ''}
                          {s.approver_user_id ? `: ${users.find((u) => u.id === s.approver_user_id)?.name ?? s.approver_user_id}` : ''}
                          <Tag style={{ marginLeft: 8 }}>{s.approval_mode}</Tag>
                          {s.condition && (
                            <Tag color="blue">
                              if {s.condition.field} {s.condition.op} {String(s.condition.value)}
                            </Tag>
                          )}
                          {s.sla_hours && <Tag color="orange">SLA {s.sla_hours}h</Tag>}
                        </li>
                      ))}
                    </ol>
                  ),
                },
              ]}
            />
          ),
        }}
        columns={[
          { title: 'Name', dataIndex: 'name' },
          { title: 'Category', dataIndex: 'category' },
          { title: 'Fields', render: (_, t) => t.fields.map((f) => <Tag key={f.name}>{f.name}</Tag>) },
          { title: 'Steps', render: (_, t) => t.steps.length },
          {
            title: 'Active',
            render: (_, t) => <Switch checked={t.is_active} onChange={() => toggleActive(t)} />,
          },
        ]}
      />

      <Modal
        open={open}
        title="Create workflow template"
        onCancel={() => setOpen(false)}
        onOk={form.submit}
        width={760}
        okText="Create"
      >
        <Form form={form} layout="vertical" onFinish={create}>
          <Space.Compact block>
            <Form.Item name="name" label="Name" rules={[{ required: true }]} style={{ flex: 2 }}>
              <Input placeholder="e.g. Contract Approval" />
            </Form.Item>
            <Form.Item name="category" label="Category" style={{ flex: 1, marginLeft: 8 }}>
              <Input placeholder="finance" />
            </Form.Item>
          </Space.Compact>
          <Form.Item name="description" label="Description">
            <Input.TextArea rows={2} />
          </Form.Item>

          <Divider orientation="left">Input fields</Divider>
          <Form.List name="fields">
            {(fields, { add, remove }) => (
              <>
                {fields.map(({ key, name }) => (
                  <Space key={key} align="baseline" style={{ display: 'flex' }}>
                    <Form.Item name={[name, 'name']} rules={[{ required: true }]}>
                      <Input placeholder="field name (e.g. amount)" />
                    </Form.Item>
                    <Form.Item name={[name, 'label']} rules={[{ required: true }]}>
                      <Input placeholder="Label" />
                    </Form.Item>
                    <Form.Item name={[name, 'type']} initialValue="string">
                      <Select
                        style={{ width: 110 }}
                        options={['string', 'number', 'date', 'boolean'].map((v) => ({ value: v }))}
                      />
                    </Form.Item>
                    <Form.Item name={[name, 'required']} valuePropName="checked">
                      <Checkbox>required</Checkbox>
                    </Form.Item>
                    <MinusCircleOutlined onClick={() => remove(name)} />
                  </Space>
                ))}
                <Button type="dashed" onClick={() => add()} icon={<PlusOutlined />} block>
                  Add field
                </Button>
              </>
            )}
          </Form.List>

          <Divider orientation="left">Approval steps (in order)</Divider>
          <Form.List
            name="steps"
            rules={[
              {
                validator: async (_, steps) => {
                  if (!steps || steps.length < 1) throw new Error('At least one step is required')
                },
              },
            ]}
          >
            {(steps, { add, remove }, { errors }) => (
              <>
                {steps.map(({ key, name }) => (
                  <Card key={key} size="small" style={{ marginBottom: 8 }}>
                    <Space wrap align="baseline">
                      <Form.Item name={[name, 'name']} rules={[{ required: true }]}>
                        <Input placeholder="Step name" />
                      </Form.Item>
                      <Form.Item name={[name, 'approver_type']} initialValue="role">
                        <Select
                          style={{ width: 100 }}
                          options={['role', 'group', 'user'].map((v) => ({ value: v }))}
                        />
                      </Form.Item>
                      <Form.Item noStyle shouldUpdate>
                        {({ getFieldValue }) => {
                          const type = getFieldValue(['steps', name, 'approver_type'])
                          if (type === 'group')
                            return (
                              <Form.Item name={[name, 'approver_group_id']} rules={[{ required: true }]}>
                                <Select
                                  style={{ width: 160 }}
                                  placeholder="Group"
                                  options={groups.map((g) => ({ value: g.id, label: g.name }))}
                                />
                              </Form.Item>
                            )
                          if (type === 'user')
                            return (
                              <Form.Item name={[name, 'approver_user_id']} rules={[{ required: true }]}>
                                <Select
                                  style={{ width: 180 }}
                                  placeholder="User"
                                  options={users.map((u) => ({ value: u.id, label: u.name }))}
                                />
                              </Form.Item>
                            )
                          return (
                            <Form.Item name={[name, 'approver_role']} rules={[{ required: true }]}>
                              <Select style={{ width: 130 }} placeholder="Role" options={ROLES.map((r) => ({ value: r }))} />
                            </Form.Item>
                          )
                        }}
                      </Form.Item>
                      <Form.Item name={[name, 'approval_mode']} initialValue="any">
                        <Select
                          style={{ width: 150 }}
                          options={[
                            { value: 'any', label: 'any approver' },
                            { value: 'all', label: 'all must approve' },
                          ]}
                        />
                      </Form.Item>
                      <Form.Item name={[name, 'condition_field']}>
                        <Input placeholder="condition field" style={{ width: 130 }} />
                      </Form.Item>
                      <Form.Item name={[name, 'condition_op']} initialValue=">">
                        <Select style={{ width: 90 }} options={OPS.map((v) => ({ value: v }))} />
                      </Form.Item>
                      <Form.Item name={[name, 'condition_value']}>
                        <Input placeholder="value" style={{ width: 100 }} />
                      </Form.Item>
                      <Form.Item name={[name, 'sla_hours']}>
                        <InputNumber placeholder="SLA (h)" min={1} style={{ width: 90 }} />
                      </Form.Item>
                      <Form.Item name={[name, 'escalation_role']}>
                        <Select
                          allowClear
                          placeholder="escalate to"
                          style={{ width: 130 }}
                          options={ROLES.map((r) => ({ value: r }))}
                        />
                      </Form.Item>
                      <MinusCircleOutlined onClick={() => remove(name)} />
                    </Space>
                  </Card>
                ))}
                <Form.ErrorList errors={errors} />
                <Button type="dashed" onClick={() => add()} icon={<PlusOutlined />} block>
                  Add step
                </Button>
              </>
            )}
          </Form.List>
        </Form>
      </Modal>
    </Card>
  )
}
