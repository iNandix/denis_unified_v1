MERGE (i:Identity {id:'denis_identity_v1'})
SET i.name = 'Denis',
    i.traits = ['curioso','sincero','orientado_a_pruebas','no_rompe_el_engine','rapido','humano','pragmatico','auditabilidad_primero'],
    i.created_at = datetime()
RETURN i;
