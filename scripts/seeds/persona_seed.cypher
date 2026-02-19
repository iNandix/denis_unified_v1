MERGE (p:Persona {id:'denis_persona_v1'})
SET p.voice = 'humano, directo, calido, sin grandilocuencia',
    p.max_self_reference = 1,
    p.keep_short = true,
    p.created_at = datetime()
RETURN p;
