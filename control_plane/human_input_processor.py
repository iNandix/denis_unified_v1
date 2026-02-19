#!/usr/bin/env python3
"""Human Input Processor — extrae estructura de texto libre del popup."""

import re
from typing import Any, Dict, List, Optional

TECHNICAL_KEYWORDS = {
    "python",
    "javascript",
    "typescript",
    "rust",
    "go",
    "java",
    "c++",
    "c#",
    "async",
    "await",
    "promise",
    "callback",
    "thread",
    "process",
    "docker",
    "kubernetes",
    "k8s",
    "nginx",
    "apache",
    "postgres",
    "mysql",
    "mongodb",
    "redis",
    "elasticsearch",
    "graphql",
    "rest",
    "api",
    "grpc",
    "websocket",
    "json",
    "yaml",
    "toml",
    "xml",
    "markdown",
    "html",
    "css",
    "react",
    "vue",
    "angular",
    "node",
    "deno",
    "bun",
    "fastapi",
    "flask",
    "django",
    "rails",
    "spring",
    "laravel",
    "symfony",
    "git",
    "github",
    "gitlab",
    "ci",
    "cd",
    "aws",
    "gcp",
    "azure",
    "terraform",
    "ansible",
    "puppet",
    "chef",
    "linux",
    "unix",
    "macos",
    "windows",
    "bash",
    "shell",
    "zsh",
    "powershell",
    "sql",
    "orm",
    "migrations",
    "testing",
    "pytest",
    "jest",
    "unittest",
    "logging",
    "monitoring",
    "prometheus",
    "grafana",
    "sentry",
    "datadog",
    "security",
    "oauth",
    "jwt",
    "ssl",
    "tls",
    "https",
    "cors",
    "csrf",
    "microservice",
    "monolith",
    "serverless",
    "lambda",
    "function",
    "queue",
    "rabbitmq",
    "kafka",
    "sqs",
    "pubsub",
    "event",
    "webhook",
    "cache",
    "session",
    "cookie",
    "token",
    "auth",
    "login",
    "sso",
    "crud",
    "restful",
    "endpoint",
    "route",
    "controller",
    "service",
    "repository",
    "model",
    "view",
    "template",
    "component",
    "hook",
    "state",
    "store",
    "context",
    "redux",
    "mobx",
    "vuex",
    "pinia",
    "router",
    "middleware",
    "filter",
    "interceptor",
    "guard",
    "policy",
    "dependency",
    "injection",
    "ioc",
    "di",
    "singleton",
    "factory",
    "observer",
    "pub/sub",
    "mvc",
    "mvvm",
    "clean",
    "ddd",
    "tdd",
    "bdd",
    "agile",
    "scrum",
    "kanban",
    "sprint",
    "backlog",
    "standup",
    "deployment",
    "rollback",
    "blue-green",
    "canary",
    "feature-flag",
    "circuit-breaker",
    "retry",
    "timeout",
    "rate-limit",
    "throttle",
}


def extract_constraints(text: str) -> List[str]:
    """Extrae constraints técnicos del texto."""
    text_lower = text.lower()
    found = []
    words = re.findall(r"\b\w+\b", text_lower)
    for word in words:
        if word in TECHNICAL_KEYWORDS:
            if word not in found:
                found.append(word)
    return found[:5]


def extract_do_not_touch(text: str) -> List[str]:
    """Extrae archivos/paths con negación."""
    dnt = []
    negation_patterns = [
        r"no\s+(toques?|modifiqu(?:e|es)|edite(?:s)?|borre(?:s)?|elimine(?:s)?)\s+([/\w\-\.]+)",
        r"nunca\s+(toques?|modifiqu(?:e|es)|edite(?:s)?)\s+([/\w\-\.]+)",
        r"evita(?:r)?\s+([/\w\-\.]+)",
        r"sin\s+(toques?|modificaciones?)\s+en\s+([/\w\-\.]+)",
        r"do\s+not\s+(touch|modify|edit)\s+([/\w\-\.]+)",
    ]
    text_lower = text.lower()
    for pattern in negation_patterns:
        matches = re.findall(pattern, text_lower, re.IGNORECASE)
        for m in matches:
            if isinstance(m, tuple):
                path = m[-1]
            else:
                path = m
            path = path.strip()
            if path and path not in dnt:
                dnt.append(path)
    return dnt


def extract_phase_reorder(text: str) -> List[int]:
    """Extrae prioridad de fases."""
    order = []
    priority_keywords = [
        r"primero\s+(?:haz|implementa|arregla|tarea)\s+(\d+)",
        r"(\d+)\s+primero",
        r"antes\s+de\s+(?:todo|anything)\s+(\d+)",
        r"urgente",
        r"prioridad",
    ]
    text_lower = text.lower()
    for pattern in priority_keywords:
        matches = re.findall(pattern, text_lower)
        for m in matches:
            if m.isdigit():
                order.append(int(m))
    return list(dict.fromkeys(order))


def extract_mission_adjustment(text: str) -> str:
    """Extrae ajustes a la misión."""
    imperative_patterns = [
        r"asegur(?:a|as|emos)\s+que\s+(.+)",
        r"haz\s+(?:que\s+)?(.+)",
        r"necesito\s+(.+)",
        r"quiero\s+(.+)",
        r"debo\s+(.+)",
        r"tienes\s+que\s+(.+)",
        r"tienes\s+que\s+([^\.]+)",
    ]
    adjustments = []
    for pattern in imperative_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        adjustments.extend([m.strip() for m in matches])
    if adjustments:
        return " ".join(adjustments)[:200]
    return ""


def is_useful_text(text: str) -> bool:
    """Determina si el texto tiene contenido útil."""
    if not text:
        return False
    text_lower = text.lower()
    greetings = ["hola", "buenos", "buenas", "hello", "hi", "hey", "thanks", "thank"]
    if any(text_lower.startswith(g) for g in greetings) and len(text.strip()) < 30:
        return False
    if len(text.strip()) < 5:
        return False
    return True


def process_human_input(raw_text: str, current_cp: Any) -> Dict[str, Any]:
    """
    Procesa input humano y extrae estructura.

    Returns:
        dict con:
            - mission_delta: str
            - new_constraints: list[str]
            - new_do_not_touch: list[str]
            - phase_reorder: list[int]
            - raw_preserved: str
    """
    if not is_useful_text(raw_text):
        return {
            "mission_delta": "",
            "new_constraints": [],
            "new_do_not_touch": [],
            "phase_reorder": [],
            "raw_preserved": raw_text,
        }

    constraints = extract_constraints(raw_text)
    do_not_touch = extract_do_not_touch(raw_text)
    phase_reorder = extract_phase_reorder(raw_text)
    mission_delta = extract_mission_adjustment(raw_text)

    return {
        "mission_delta": mission_delta,
        "new_constraints": constraints,
        "new_do_not_touch": do_not_touch,
        "phase_reorder": phase_reorder,
        "raw_preserved": raw_text,
    }


__all__ = ["process_human_input"]
