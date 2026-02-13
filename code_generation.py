import ast
import subprocess
import tempfile
import time
from typing import Dict, List, Any

class ASTValidator:
    def validate(self, code: str) -> Dict[str, Any]:
        try:
            ast.parse(code)
            return {"valid": True, "errors": []}
        except SyntaxError as e:
            return {"valid": False, "errors": [str(e)]}

class SandboxExecutor:
    def execute(self, code: str, timeout: int = 5) -> Dict[str, Any]:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            f.flush()
            script_path = f.name

        try:
            result = subprocess.run(
                ['python3', script_path],
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "timeout", "stdout": "", "stderr": ""}
        finally:
            import os
            os.unlink(script_path)

class CodeGenerator:
    def generate(self, prompt: str) -> str:
        # Simple template-based generation for now
        if "function" in prompt.lower():
            return f"""
def generated_function():
    print("Hello from generated code")
    return "success"
"""
        elif "class" in prompt.lower():
            return f"""
class GeneratedClass:
    def __init__(self):
        self.value = "generated"

    def get_value(self):
        return self.value
"""
        else:
            return "# Generated code placeholder"

def generate_and_validate(prompt: str) -> Dict[str, Any]:
    generator = CodeGenerator()
    validator = ASTValidator()
    executor = SandboxExecutor()

    code = generator.generate(prompt)
    validation = validator.validate(code)
    
    if validation["valid"]:
        execution = executor.execute(code)
    else:
        execution = {"success": False, "error": "validation_failed"}

    return {
        "code": code,
        "validation": validation,
        "execution": execution
    }
