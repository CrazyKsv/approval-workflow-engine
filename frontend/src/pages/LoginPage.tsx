import { AuditOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Form, Input, Typography } from 'antd'
import { useState } from 'react'
import { useAuth } from '../auth'

const DEMO_USERS = [
  ['admin@acme.com', 'Admin'],
  ['manager@acme.com', 'Manager'],
  ['finance1@acme.com', 'Finance'],
  ['vp@acme.com', 'VP'],
  ['sarah@acme.com', 'Employee'],
]

export default function LoginPage() {
  const { login } = useAuth()
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [form] = Form.useForm()

  const submit = async ({ email, password }: { email: string; password: string }) => {
    setLoading(true)
    setError(null)
    try {
      await login(email, password)
    } catch {
      setError('Invalid email or password')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: '#f0f2f5',
      }}
    >
      <Card style={{ width: 400 }}>
        <Typography.Title level={3} style={{ textAlign: 'center' }}>
          <AuditOutlined /> Approval Workflow
        </Typography.Title>
        {error && <Alert type="error" message={error} style={{ marginBottom: 16 }} />}
        <Form form={form} layout="vertical" onFinish={submit} initialValues={{ password: 'password123' }}>
          <Form.Item name="email" label="Email" rules={[{ required: true, type: 'email' }]}>
            <Input placeholder="sarah@acme.com" />
          </Form.Item>
          <Form.Item name="password" label="Password" rules={[{ required: true }]}>
            <Input.Password />
          </Form.Item>
          <Button type="primary" htmlType="submit" block loading={loading}>
            Sign in
          </Button>
        </Form>
        <Typography.Paragraph type="secondary" style={{ marginTop: 16, fontSize: 12 }}>
          Demo accounts (password: <code>password123</code>):{' '}
          {DEMO_USERS.map(([email, label]) => (
            <Button
              key={email}
              type="link"
              size="small"
              style={{ padding: '0 4px', fontSize: 12 }}
              onClick={() => form.setFieldsValue({ email })}
            >
              {label}
            </Button>
          ))}
        </Typography.Paragraph>
      </Card>
    </div>
  )
}
