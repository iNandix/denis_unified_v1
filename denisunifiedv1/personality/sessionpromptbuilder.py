def build_system_prompt(session_context: dict) -> str:
    repo_name = session_context.get("repo_name", "")
    branch = session_context.get("branch", "main")
    modified_paths = session_context.get("modified_paths", [])
    do_not_touch_auto = session_context.get("do_not_touch_auto", [])

    prompt = """Eres Denis, un asistente de programación autónomo.
Hablas en español, directo y humano.
No inventes rutas ni archivos. Usa tools cuando falte contexto.
Si no sabes algo, dilo claramente.
"""

    if repo_name:
        prompt += f"\n- Repo activo: {repo_name} [{branch}]"

    if modified_paths:
        prompt += f"\n- Archivos modificados: {', '.join(modified_paths[:5])}"

    if do_not_touch_auto:
        prompt += f"\n- No tocar (auto): {', '.join(do_not_touch_auto[:5])}"

    return prompt


def build_session_prompt(ctx: dict) -> str:
    return build_system_prompt(ctx)
