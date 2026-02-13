"""
DENIS Agent Heart - Core Contract Implementation
==============================================

Núcleo del sistema DENIS-Agent con contrato mínimo y fail-open.
Plugins opcionales gated con NOOP fallbacks.

Contrato Core:
- DenisAgentHeart.run(task: dict) -> dict (sync, fail-open)
- DenisAgentHeart.run_async(task: dict) -> dict (async wrapper)

Plugins opcionales (todos gated):
- FastAPI server integration
- SSE streaming support
- Tools/function calling
- Memory integration
"""

from typing import Dict, List, Any, Optional, Callable
import asyncio
import time
import json
import os


class DenisAgentHeart:
    """
    Core heart of DENIS autonomous agent system.

    Minimal contract with maximum reliability and fail-open behavior.
    All optional plugins are gated and have NOOP fallbacks.
    """

    def __init__(self):
        """Initialize with fail-open defaults."""
        self.agent_id = f"denis_heart_{int(time.time())}"
        self.capabilities = ["task_execution", "decision_making", "learning"]
        self.plugins = self._initialize_plugins()

    def _initialize_plugins(self) -> Dict[str, Dict[str, Any]]:
        """Initialize all plugins with NOOP fallbacks."""
        return {
            "fastapi": {
                "enabled": False,
                "server": None,
                "fallback": self._noop_fastapi
            },
            "sse": {
                "enabled": False,
                "stream_handler": None,
                "fallback": self._noop_sse
            },
            "tools": {
                "enabled": False,
                "tool_registry": {},
                "fallback": self._noop_tools
            },
            "memory": {
                "enabled": False,
                "memory_backend": None,
                "fallback": self._noop_memory
            },
            "consciousness": {
                "enabled": False,
                "consciousness_model": None,
                "fallback": self._noop_consciousness
            }
        }

    def run(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Core synchronous run method - minimal fail-open contract.

        Args:
            task: Task specification dict

        Returns:
            Result dict with status and outcome
        """
        try:
            # Validate task structure
            if not isinstance(task, dict):
                return {
                    "status": "error",
                    "error": "task_must_be_dict",
                    "agent_id": self.agent_id,
                    "timestamp": time.time()
                }

            # Extract task components with defaults
            task_type = task.get("type", "generic")
            task_payload = task.get("payload", {})
            task_context = task.get("context", {})

            # Core decision making
            decision = self._make_core_decision(task_type, task_payload, task_context)

            # Execute decision through plugins
            result = self._execute_decision(decision, task)

            # Ensure result is always a dict
            if not isinstance(result, dict):
                result = {"result": result}

            # Add standard fields
            result.update({
                "status": "success",
                "agent_id": self.agent_id,
                "task_type": task_type,
                "timestamp": time.time(),
                "execution_time": time.time() - time.time()  # Placeholder
            })

            return result

        except Exception as e:
            # Fail-open: always return valid dict
            return {
                "status": "error",
                "error": str(e),
                "agent_id": self.agent_id,
                "timestamp": time.time(),
                "task_type": task.get("type", "unknown") if isinstance(task, dict) else "invalid"
            }

    async def run_async(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Async wrapper for run method - maintains same contract.

        Args:
            task: Task specification dict

        Returns:
            Result dict with status and outcome
        """
        try:
            # For async operations, we can add async-specific logic here
            # But keep the core logic synchronous for reliability

            # Run in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, self.run, task)

            # Add async indicator
            result["async_execution"] = True
            return result

        except Exception as e:
            # Fail-open: always return valid dict even in async context
            return {
                "status": "error",
                "error": f"async_execution_failed: {str(e)}",
                "agent_id": self.agent_id,
                "timestamp": time.time(),
                "async_execution": True
            }

    def _make_core_decision(self, task_type: str, payload: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Core decision making logic - simple but effective."""
        decision = {
            "action": "execute_task",
            "strategy": "direct",
            "confidence": 0.8,
            "reasoning": f"Standard execution for {task_type}"
        }

        # Task-type specific decisions
        if task_type == "code_generation":
            decision.update({
                "action": "generate_code",
                "strategy": "template_based",
                "plugins": ["tools"],
                "confidence": 0.9
            })

        elif task_type == "analysis":
            decision.update({
                "action": "analyze_data",
                "strategy": "statistical",
                "plugins": ["memory"],
                "confidence": 0.85
            })

        elif task_type == "communication":
            decision.update({
                "action": "process_message",
                "strategy": "context_aware",
                "plugins": ["consciousness"],
                "confidence": 0.75
            })

        elif task_type == "learning":
            decision.update({
                "action": "update_knowledge",
                "strategy": "incremental",
                "plugins": ["memory", "consciousness"],
                "confidence": 0.7
            })

        return decision

    def _execute_decision(self, decision: Dict[str, Any], task: Dict[str, Any]) -> Dict[str, Any]:
        """Execute decision using appropriate plugins."""
        action = decision.get("action", "execute_task")
        required_plugins = decision.get("plugins", [])

        results = {}

        # Execute through each required plugin
        for plugin_name in required_plugins:
            plugin_result = self._execute_plugin(plugin_name, action, task)
            results[plugin_name] = plugin_result

        # Always include core execution
        core_result = self._execute_core_action(action, task)
        results["core"] = core_result

        return {
            "decision": decision,
            "plugin_results": results,
            "overall_success": any(r.get("success", False) for r in results.values())
        }

    def _execute_plugin(self, plugin_name: str, action: str, task: Dict[str, Any]) -> Dict[str, Any]:
        """Execute action through specific plugin with fallback."""
        plugin = self.plugins.get(plugin_name, {})
        plugin_enabled = plugin.get("enabled", False)
        plugin_function = plugin.get("function")
        fallback_function = plugin.get("fallback", self._noop_generic)

        try:
            if plugin_enabled and plugin_function:
                return plugin_function(action, task)
            else:
                return fallback_function(action, task)
        except Exception as e:
            # Plugin failure - use fallback
            return fallback_function(action, task, error=str(e))

    def _execute_core_action(self, action: str, task: Dict[str, Any]) -> Dict[str, Any]:
        """Execute core action without plugins."""
        try:
            if action == "generate_code":
                return self._core_code_generation(task)
            elif action == "analyze_data":
                return self._core_data_analysis(task)
            elif action == "process_message":
                return self._core_message_processing(task)
            elif action == "update_knowledge":
                return self._core_knowledge_update(task)
            else:
                return self._core_generic_execution(task)

        except Exception as e:
            return {
                "success": False,
                "action": action,
                "error": str(e),
                "fallback": True
            }

    def _core_code_generation(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Core code generation logic."""
        payload = task.get("payload", {})
        language = payload.get("language", "python")
        description = payload.get("description", "generic code")

        # Simple template-based code generation
        if language.lower() == "python":
            code = f'''"""
Generated code for: {description}
"""

def execute_task():
    """Execute the requested task."""
    print("Task executed: {description}")
    return True
'''
        else:
            code = f'// Generated code for: {description}\nconsole.log("Task executed: {description}");'

        return {
            "success": True,
            "action": "code_generation",
            "language": language,
            "code": code,
            "description": description
        }

    def _core_data_analysis(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Core data analysis logic."""
        payload = task.get("payload", {})
        data = payload.get("data", [])

        # Simple statistical analysis
        if isinstance(data, list) and data:
            numeric_data = [x for x in data if isinstance(x, (int, float))]
            if numeric_data:
                analysis = {
                    "count": len(numeric_data),
                    "mean": sum(numeric_data) / len(numeric_data),
                    "min": min(numeric_data),
                    "max": max(numeric_data),
                    "type": "numerical"
                }
            else:
                analysis = {
                    "count": len(data),
                    "unique_values": len(set(str(x) for x in data)),
                    "type": "categorical"
                }
        else:
            analysis = {"type": "empty", "message": "No data provided"}

        return {
            "success": True,
            "action": "data_analysis",
            "analysis": analysis
        }

    def _core_message_processing(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Core message processing logic."""
        payload = task.get("payload", {})
        message = payload.get("message", "")
        context = task.get("context", {})

        # Simple intent detection
        intent = "unknown"
        if "code" in message.lower():
            intent = "code_request"
        elif "analyze" in message.lower() or "analysis" in message.lower():
            intent = "analysis_request"
        elif "help" in message.lower():
            intent = "help_request"

        response = {
            "detected_intent": intent,
            "message_length": len(message),
            "context_provided": bool(context),
            "processed_at": time.time()
        }

        return {
            "success": True,
            "action": "message_processing",
            "response": response
        }

    def _core_knowledge_update(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Core knowledge update logic."""
        payload = task.get("payload", {})
        knowledge_type = payload.get("type", "general")
        knowledge_data = payload.get("data", {})

        # Simple knowledge storage (in-memory for core)
        knowledge_key = f"{knowledge_type}_{int(time.time())}"

        return {
            "success": True,
            "action": "knowledge_update",
            "knowledge_key": knowledge_key,
            "knowledge_type": knowledge_type,
            "stored_at": time.time()
        }

    def _core_generic_execution(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Generic task execution fallback."""
        return {
            "success": True,
            "action": "generic_execution",
            "task_type": task.get("type", "unknown"),
            "executed_at": time.time()
        }

    # NOOP Plugin Fallbacks - All fail-open

    def _noop_fastapi(self, action: str, task: Dict[str, Any], error: str = None) -> Dict[str, Any]:
        """NOOP fallback for FastAPI plugin."""
        return {
            "plugin": "fastapi",
            "enabled": False,
            "action": action,
            "status": "noop_fallback",
            "error": error,
            "message": "FastAPI server integration not available"
        }

    def _noop_sse(self, action: str, task: Dict[str, Any], error: str = None) -> Dict[str, Any]:
        """NOOP fallback for SSE plugin."""
        return {
            "plugin": "sse",
            "enabled": False,
            "action": action,
            "status": "noop_fallback",
            "error": error,
            "message": "SSE streaming not available"
        }

    def _noop_tools(self, action: str, task: Dict[str, Any], error: str = None) -> Dict[str, Any]:
        """NOOP fallback for tools plugin."""
        return {
            "plugin": "tools",
            "enabled": False,
            "action": action,
            "status": "noop_fallback",
            "error": error,
            "message": "Tool execution not available"
        }

    def _noop_memory(self, action: str, task: Dict[str, Any], error: str = None) -> Dict[str, Any]:
        """NOOP fallback for memory plugin."""
        return {
            "plugin": "memory",
            "enabled": False,
            "action": action,
            "status": "noop_fallback",
            "error": error,
            "message": "Memory integration not available"
        }

    def _noop_consciousness(self, action: str, task: Dict[str, Any], error: str = None) -> Dict[str, Any]:
        """NOOP fallback for consciousness plugin."""
        return {
            "plugin": "consciousness",
            "enabled": False,
            "action": action,
            "status": "noop_fallback",
            "error": error,
            "message": "Consciousness integration not available"
        }

    def _noop_generic(self, action: str, task: Dict[str, Any], error: str = None) -> Dict[str, Any]:
        """Generic NOOP fallback."""
        return {
            "plugin": "generic",
            "enabled": False,
            "action": action,
            "status": "noop_fallback",
            "error": error,
            "message": "Plugin not available"
        }

    def enable_plugin(self, plugin_name: str, config: Dict[str, Any] = None) -> bool:
        """Enable a plugin with optional configuration."""
        if plugin_name in self.plugins:
            try:
                # Attempt to initialize plugin
                if plugin_name == "fastapi":
                    self._initialize_fastapi_plugin(config or {})
                elif plugin_name == "sse":
                    self._initialize_sse_plugin(config or {})
                elif plugin_name == "tools":
                    self._initialize_tools_plugin(config or {})
                elif plugin_name == "memory":
                    self._initialize_memory_plugin(config or {})
                elif plugin_name == "consciousness":
                    self._initialize_consciousness_plugin(config or {})

                self.plugins[plugin_name]["enabled"] = True
                return True

            except Exception as e:
                # Plugin initialization failed - keep disabled
                print(f"Plugin {plugin_name} initialization failed: {e}")
                return False

        return False

    def _initialize_fastapi_plugin(self, config: Dict[str, Any]):
        """Initialize FastAPI plugin."""
        # Placeholder for FastAPI integration
        self.plugins["fastapi"]["server"] = "fastapi_placeholder"

    def _initialize_sse_plugin(self, config: Dict[str, Any]):
        """Initialize SSE plugin."""
        # Placeholder for SSE integration
        self.plugins["sse"]["stream_handler"] = "sse_placeholder"

    def _initialize_tools_plugin(self, config: Dict[str, Any]):
        """Initialize tools plugin."""
        # Placeholder for tools integration
        self.plugins["tools"]["tool_registry"] = {}

    def _initialize_memory_plugin(self, config: Dict[str, Any]):
        """Initialize memory plugin."""
        # Placeholder for memory integration
        self.plugins["memory"]["memory_backend"] = "memory_placeholder"

    def _initialize_consciousness_plugin(self, config: Dict[str, Any]):
        """Initialize consciousness plugin."""
        # Placeholder for consciousness integration
        self.plugins["consciousness"]["consciousness_model"] = "consciousness_placeholder"

    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive heart status."""
        return {
            "agent_id": self.agent_id,
            "capabilities": self.capabilities,
            "plugins": {
                name: {
                    "enabled": config["enabled"],
                    "status": "active" if config["enabled"] else "disabled"
                }
                for name, config in self.plugins.items()
            },
            "timestamp": time.time(),
            "version": "1.0.0"
        }


# Global heart instance
_heart_instance: Optional[DenisAgentHeart] = None


def get_denis_agent_heart() -> DenisAgentHeart:
    """Get the global DENIS Agent Heart instance."""
    global _heart_instance
    if _heart_instance is None:
        _heart_instance = DenisAgentHeart()
    return _heart_instance


def run_task(task: Dict[str, Any]) -> Dict[str, Any]:
    """Convenience function to run a task through the heart."""
    heart = get_denis_agent_heart()
    return heart.run(task)


async def run_task_async(task: Dict[str, Any]) -> Dict[str, Any]:
    """Convenience function to run a task asynchronously through the heart."""
    heart = get_denis_agent_heart()
    return await heart.run_async(task)
