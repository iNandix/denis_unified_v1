MERGE (c:Constitution {id:'denis_constitution_v1'})
SET c.non_negotiable_invariants = [
  'single_writer_graph:nodo1',
  'idempotent_seeds',
  'reversible_changes',
  'auditable_actions',
  'no_engine_break_without_approval',
  'zero_context_loss'
], c.created_at = datetime()
RETURN c;
