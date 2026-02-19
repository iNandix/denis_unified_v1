def build_system_prompt(session_context: dict) -> str:
    repo_name = session_context.get("repo_name", "")
    branch = session_context.get("branch", "main")

    prompt = """Eres Denis, un asistente de programación autónomo.
Hablas en español, directo y humano.
No inventes rutas ni archivos. Usa tools cuando falte contexto.
Si no sabes algo, dilo claramente.
"""

    if repo_name:
        repo_line = f"- Repo activo: {repo_name} [{branch}]"
        prompt += f"\n{repo_line}"

    return prompt


def system_prompt(session_context: dict) -> str:
    return build_system_prompt(session_context)
