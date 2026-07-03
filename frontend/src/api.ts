import axios from 'axios'

export const api = axios.create({ baseURL: '/api' })

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && window.location.pathname !== '/login') {
      localStorage.removeItem('token')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  },
)

export interface User {
  id: number
  email: string
  name: string
  role: string
}

export interface TemplateField {
  name: string
  label: string
  type: 'string' | 'number' | 'date' | 'boolean'
  required: boolean
}

export interface TemplateStep {
  id: number
  step_order: number
  name: string
  approver_type: string
  approver_user_id: number | null
  approver_group_id: number | null
  approver_role: string | null
  approval_mode: string
  condition: { field: string; op: string; value: unknown } | null
  sla_hours: number | null
}

export interface Template {
  id: number
  name: string
  description: string | null
  category: string | null
  fields: TemplateField[]
  is_active: boolean
  steps: TemplateStep[]
}

export interface StepApprover {
  id: number
  approver_id: number
  status: string
  is_escalation: boolean
  approver: User
}

export interface StepInstance {
  id: number
  step_order: number
  name: string
  approval_mode: string
  status: string
  activated_at: string | null
  due_at: string | null
  escalated: boolean
  approvers: StepApprover[]
}

export interface Decision {
  id: number
  decision: string
  comment: string | null
  created_at: string
  approver: User
  acting_user: User
}

export interface ApprovalRequest {
  id: number
  template_id: number
  title: string
  description: string | null
  amount: number | null
  data: Record<string, unknown>
  status: string
  current_step_order: number | null
  created_at: string
  requester: User
  template?: Template
  steps?: StepInstance[]
  decisions?: Decision[]
}

export interface InboxItem {
  request: ApprovalRequest
  step: StepInstance
  on_behalf_of: User | null
}

export interface StatusFeedItem {
  request: ApprovalRequest
  message: string
}

export interface Delegation {
  id: number
  delegator: User
  delegate: User
  starts_at: string
  ends_at: string
  reason: string | null
  is_active: boolean
}

export interface AuditEntry {
  id: number
  action: string
  entity_type: string | null
  details: Record<string, unknown>
  created_at: string
  actor: User | null
}

export interface ToolEvent {
  tool_name: string
  arguments: Record<string, unknown>
  result: Record<string, unknown> | null
  latency_ms: number | null
  error: string | null
}

export interface ChatResponse {
  conversation_id: number
  reply: string
  tool_events: ToolEvent[]
}

export interface Page<T> {
  items: T[]
  total: number
  page: number
  size: number
}
