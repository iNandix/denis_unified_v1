CREATE CONSTRAINT intent_id_unique IF NOT EXISTS
  FOR (i:Intent) REQUIRE i.id IS UNIQUE;

CREATE CONSTRAINT session_id_unique IF NOT EXISTS
  FOR (s:Session) REQUIRE s.id IS UNIQUE;

CREATE CONSTRAINT human_input_id_unique IF NOT EXISTS
  FOR (h:HumanInput) REQUIRE h.id IS UNIQUE;

CREATE INDEX intent_status IF NOT EXISTS
  FOR (i:Intent) ON (i.status);

CREATE INDEX intent_created_at IF NOT EXISTS
  FOR (i:Intent) ON (i.created_at);

CREATE INDEX intent_risk_score IF NOT EXISTS
  FOR (i:Intent) ON (i.risk_score);

CREATE INDEX session_created_at IF NOT EXISTS
  FOR (s:Session) ON (s.created_at);

CREATE INDEX session_status IF NOT EXISTS
  FOR (s:Session) ON (s.status);
