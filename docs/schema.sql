-- Approval Workflow Engine — PostgreSQL schema
-- Generated from app/models.py (single source of truth); do not edit by hand.

CREATE TABLE groups (
	id SERIAL NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	description TEXT, 
	PRIMARY KEY (id), 
	UNIQUE (name)
);

CREATE TABLE users (
	id SERIAL NOT NULL, 
	email VARCHAR(255) NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	password_hash VARCHAR(255) NOT NULL, 
	role VARCHAR(50) NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ix_users_email ON users (email);

CREATE TABLE agent_conversations (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	title VARCHAR(255), 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE INDEX ix_agent_conversations_user_id ON agent_conversations (user_id);

CREATE TABLE delegations (
	id SERIAL NOT NULL, 
	delegator_id INTEGER NOT NULL, 
	delegate_id INTEGER NOT NULL, 
	starts_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	ends_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	reason TEXT, 
	is_active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(delegator_id) REFERENCES users (id), 
	FOREIGN KEY(delegate_id) REFERENCES users (id)
);

CREATE INDEX ix_delegations_delegate ON delegations (delegate_id, is_active);
CREATE INDEX ix_delegations_delegator ON delegations (delegator_id, is_active);

CREATE TABLE user_groups (
	user_id INTEGER NOT NULL, 
	group_id INTEGER NOT NULL, 
	PRIMARY KEY (user_id, group_id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(group_id) REFERENCES groups (id) ON DELETE CASCADE
);

CREATE TABLE workflow_templates (
	id SERIAL NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	description TEXT, 
	category VARCHAR(100), 
	fields JSONB NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	version INTEGER NOT NULL, 
	created_by_id INTEGER, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(created_by_id) REFERENCES users (id)
);

CREATE INDEX ix_workflow_templates_is_active ON workflow_templates (is_active);
CREATE INDEX ix_workflow_templates_name ON workflow_templates (name);

CREATE TABLE agent_messages (
	id SERIAL NOT NULL, 
	conversation_id INTEGER NOT NULL, 
	role VARCHAR(20) NOT NULL, 
	content TEXT, 
	tool_calls JSONB, 
	tool_call_id VARCHAR(100), 
	tool_name VARCHAR(100), 
	tool_args JSONB, 
	tool_result JSONB, 
	latency_ms INTEGER, 
	error TEXT, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(conversation_id) REFERENCES agent_conversations (id) ON DELETE CASCADE
);

CREATE INDEX ix_agent_messages_conversation_id ON agent_messages (conversation_id);

CREATE TABLE approval_requests (
	id SERIAL NOT NULL, 
	template_id INTEGER NOT NULL, 
	requester_id INTEGER NOT NULL, 
	title VARCHAR(255) NOT NULL, 
	description TEXT, 
	amount NUMERIC(14, 2), 
	data JSONB NOT NULL, 
	status VARCHAR(30) NOT NULL, 
	current_step_order INTEGER, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	completed_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(template_id) REFERENCES workflow_templates (id), 
	FOREIGN KEY(requester_id) REFERENCES users (id)
);

CREATE INDEX ix_approval_requests_requester_id ON approval_requests (requester_id);
CREATE INDEX ix_approval_requests_status ON approval_requests (status);
CREATE INDEX ix_approval_requests_template_id ON approval_requests (template_id);

CREATE TABLE template_steps (
	id SERIAL NOT NULL, 
	template_id INTEGER NOT NULL, 
	step_order INTEGER NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	approver_type VARCHAR(20) NOT NULL, 
	approver_user_id INTEGER, 
	approver_group_id INTEGER, 
	approver_role VARCHAR(50), 
	approval_mode VARCHAR(10) NOT NULL, 
	condition JSONB, 
	sla_hours INTEGER, 
	escalation_user_id INTEGER, 
	escalation_role VARCHAR(50), 
	PRIMARY KEY (id), 
	UNIQUE (template_id, step_order), 
	FOREIGN KEY(template_id) REFERENCES workflow_templates (id) ON DELETE CASCADE, 
	FOREIGN KEY(approver_user_id) REFERENCES users (id), 
	FOREIGN KEY(approver_group_id) REFERENCES groups (id), 
	FOREIGN KEY(escalation_user_id) REFERENCES users (id)
);

CREATE INDEX ix_template_steps_template_id ON template_steps (template_id);

CREATE TABLE audit_log (
	id SERIAL NOT NULL, 
	request_id INTEGER, 
	actor_id INTEGER, 
	action VARCHAR(100) NOT NULL, 
	entity_type VARCHAR(50), 
	entity_id INTEGER, 
	details JSONB NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(request_id) REFERENCES approval_requests (id) ON DELETE SET NULL, 
	FOREIGN KEY(actor_id) REFERENCES users (id)
);

CREATE INDEX ix_audit_log_action ON audit_log (action);
CREATE INDEX ix_audit_log_created_at ON audit_log (created_at);
CREATE INDEX ix_audit_request_created ON audit_log (request_id, created_at);

CREATE TABLE step_instances (
	id SERIAL NOT NULL, 
	request_id INTEGER NOT NULL, 
	template_step_id INTEGER, 
	step_order INTEGER NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	approval_mode VARCHAR(10) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	activated_at TIMESTAMP WITH TIME ZONE, 
	completed_at TIMESTAMP WITH TIME ZONE, 
	due_at TIMESTAMP WITH TIME ZONE, 
	escalated BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(request_id) REFERENCES approval_requests (id) ON DELETE CASCADE, 
	FOREIGN KEY(template_step_id) REFERENCES template_steps (id)
);

CREATE INDEX ix_step_instances_request_id ON step_instances (request_id);
CREATE INDEX ix_step_instances_status_due ON step_instances (status, due_at);

CREATE TABLE decisions (
	id SERIAL NOT NULL, 
	request_id INTEGER NOT NULL, 
	step_instance_id INTEGER NOT NULL, 
	approver_id INTEGER NOT NULL, 
	acting_user_id INTEGER NOT NULL, 
	decision VARCHAR(30) NOT NULL, 
	comment TEXT, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(request_id) REFERENCES approval_requests (id) ON DELETE CASCADE, 
	FOREIGN KEY(step_instance_id) REFERENCES step_instances (id) ON DELETE CASCADE, 
	FOREIGN KEY(approver_id) REFERENCES users (id), 
	FOREIGN KEY(acting_user_id) REFERENCES users (id)
);

CREATE INDEX ix_decisions_request_id ON decisions (request_id);

CREATE TABLE step_approvers (
	id SERIAL NOT NULL, 
	step_instance_id INTEGER NOT NULL, 
	request_id INTEGER NOT NULL, 
	approver_id INTEGER NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	is_escalation BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(step_instance_id) REFERENCES step_instances (id) ON DELETE CASCADE, 
	FOREIGN KEY(request_id) REFERENCES approval_requests (id) ON DELETE CASCADE, 
	FOREIGN KEY(approver_id) REFERENCES users (id)
);

CREATE INDEX ix_step_approvers_approver_status ON step_approvers (approver_id, status);
CREATE INDEX ix_step_approvers_request_id ON step_approvers (request_id);
CREATE INDEX ix_step_approvers_step_instance_id ON step_approvers (step_instance_id);

