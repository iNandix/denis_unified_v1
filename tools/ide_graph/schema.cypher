// Schema for DENIS IDE Graph
// Constraints for uniqueness

CREATE CONSTRAINT unique_workspace_id IF NOT EXISTS FOR (w:Workspace) REQUIRE w.id IS UNIQUE;
CREATE CONSTRAINT unique_file_path IF NOT EXISTS FOR (f:File) REQUIRE f.path IS UNIQUE;
CREATE CONSTRAINT unique_component_name IF NOT EXISTS FOR (c:Component) REQUIRE c.name IS UNIQUE;
CREATE CONSTRAINT unique_phase_name IF NOT EXISTS FOR (p:Phase) REQUIRE p.name IS UNIQUE;
CREATE CONSTRAINT unique_service_name IF NOT EXISTS FOR (s:Service) REQUIRE s.name IS UNIQUE;
CREATE CONSTRAINT unique_test_name IF NOT EXISTS FOR (t:Test) REQUIRE t.name IS UNIQUE;
CREATE CONSTRAINT unique_proposal_id IF NOT EXISTS FOR (pr:Proposal) REQUIRE pr.id IS UNIQUE;
CREATE CONSTRAINT unique_external_name IF NOT EXISTS FOR (e:ExternalResource) REQUIRE e.name IS UNIQUE;
CREATE CONSTRAINT unique_agent_run_trace_id IF NOT EXISTS FOR (r:AgentRun) REQUIRE r.trace_id IS UNIQUE;
CREATE CONSTRAINT unique_agent_task_task_id IF NOT EXISTS FOR (t:AgentTask) REQUIRE t.task_id IS UNIQUE;
CREATE CONSTRAINT unique_agent_result_task_id IF NOT EXISTS FOR (res:AgentResult) REQUIRE res.task_id IS UNIQUE;

// Indexes for performance
CREATE INDEX workspace_path IF NOT EXISTS FOR (w:Workspace) ON (w.path);
CREATE INDEX component_kind IF NOT EXISTS FOR (c:Component) ON (c.kind);
CREATE INDEX service_type IF NOT EXISTS FOR (s:Service) ON (s.type);
CREATE INDEX test_type IF NOT EXISTS FOR (t:Test) ON (t.type);
CREATE INDEX proposal_status IF NOT EXISTS FOR (pr:Proposal) ON (pr.status);
