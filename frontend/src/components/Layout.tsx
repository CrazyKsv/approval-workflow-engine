import {
  AuditOutlined,
  FileTextOutlined,
  InboxOutlined,
  LogoutOutlined,
  MessageOutlined,
  PartitionOutlined,
  UserSwitchOutlined,
} from '@ant-design/icons'
import { Layout as AntLayout, Menu, Space, Tag, Typography } from 'antd'
import { useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'

const { Header, Content, Sider } = AntLayout

const ROLE_COLORS: Record<string, string> = {
  admin: 'red',
  manager: 'blue',
  finance: 'gold',
  vp: 'purple',
  employee: 'green',
}

export default function Layout({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const items = [
    { key: '/inbox', icon: <InboxOutlined />, label: 'Approval Inbox' },
    { key: '/requests', icon: <FileTextOutlined />, label: 'My Requests' },
    { key: '/assistant', icon: <MessageOutlined />, label: 'AI Assistant' },
    { key: '/delegations', icon: <UserSwitchOutlined />, label: 'Delegations' },
    ...(user?.role === 'admin'
      ? [{ key: '/templates', icon: <PartitionOutlined />, label: 'Workflow Templates' }]
      : []),
    { key: 'logout', icon: <LogoutOutlined />, label: 'Sign out' },
  ]

  return (
    <AntLayout style={{ minHeight: '100vh' }}>
      <Sider theme="dark" width={220}>
        <div style={{ color: '#fff', padding: 20, fontWeight: 700, fontSize: 16 }}>
          <AuditOutlined /> Approvals
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={items}
          onClick={({ key }) => (key === 'logout' ? logout() : navigate(key))}
        />
      </Sider>
      <AntLayout>
        <Header
          style={{
            background: '#fff',
            display: 'flex',
            justifyContent: 'flex-end',
            alignItems: 'center',
            paddingRight: 24,
          }}
        >
          <Space>
            <Typography.Text strong>{user?.name}</Typography.Text>
            <Tag color={ROLE_COLORS[user?.role ?? ''] || 'default'}>{user?.role}</Tag>
          </Space>
        </Header>
        <Content style={{ margin: 24 }}>{children}</Content>
      </AntLayout>
    </AntLayout>
  )
}
