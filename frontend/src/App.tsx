import { Spin } from 'antd'
import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './auth'
import Layout from './components/Layout'
import ChatPage from './pages/ChatPage'
import DelegationsPage from './pages/DelegationsPage'
import InboxPage from './pages/InboxPage'
import LoginPage from './pages/LoginPage'
import RequestDetailPage from './pages/RequestDetailPage'
import RequestsPage from './pages/RequestsPage'
import TemplatesPage from './pages/TemplatesPage'

// UI access control (product clarification):
// admin -> templates + assistant only; employee -> inbox/requests/assistant;
// manager/finance/vp -> inbox/requests/assistant/delegations.
export const ROUTE_ROLES: Record<string, string[]> = {
  '/inbox': ['employee', 'manager', 'finance', 'vp'],
  '/requests': ['employee', 'manager', 'finance', 'vp'],
  '/delegations': ['manager', 'finance', 'vp'],
  '/templates': ['admin'],
  '/assistant': ['admin', 'employee', 'manager', 'finance', 'vp'],
}

export const defaultRouteFor = (role: string | undefined) =>
  role === 'admin' ? '/templates' : '/inbox'

function RequireRole({ route, children }: { route: string; children: React.ReactElement }) {
  const { user } = useAuth()
  if (!user || !ROUTE_ROLES[route]?.includes(user.role)) {
    return <Navigate to={defaultRouteFor(user?.role)} replace />
  }
  return children
}

export default function App() {
  const { user, loading } = useAuth()

  if (loading) {
    return <Spin size="large" style={{ display: 'block', marginTop: '20vh', textAlign: 'center' }} />
  }
  if (!user) {
    return (
      <Routes>
        <Route path="*" element={<LoginPage />} />
      </Routes>
    )
  }
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Navigate to={defaultRouteFor(user.role)} replace />} />
        <Route path="/login" element={<Navigate to={defaultRouteFor(user.role)} replace />} />
        <Route path="/inbox" element={<RequireRole route="/inbox"><InboxPage /></RequireRole>} />
        <Route path="/requests" element={<RequireRole route="/requests"><RequestsPage /></RequireRole>} />
        <Route path="/requests/:id" element={<RequireRole route="/requests"><RequestDetailPage /></RequireRole>} />
        <Route path="/templates" element={<RequireRole route="/templates"><TemplatesPage /></RequireRole>} />
        <Route
          path="/delegations"
          element={<RequireRole route="/delegations"><DelegationsPage /></RequireRole>}
        />
        <Route path="/assistant" element={<ChatPage />} />
        <Route path="*" element={<Navigate to={defaultRouteFor(user.role)} replace />} />
      </Routes>
    </Layout>
  )
}
