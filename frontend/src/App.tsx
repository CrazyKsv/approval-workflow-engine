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
        <Route path="/" element={<Navigate to="/inbox" replace />} />
        <Route path="/login" element={<Navigate to="/inbox" replace />} />
        <Route path="/inbox" element={<InboxPage />} />
        <Route path="/requests" element={<RequestsPage />} />
        <Route path="/requests/:id" element={<RequestDetailPage />} />
        <Route path="/templates" element={<TemplatesPage />} />
        <Route path="/delegations" element={<DelegationsPage />} />
        <Route path="/assistant" element={<ChatPage />} />
      </Routes>
    </Layout>
  )
}
