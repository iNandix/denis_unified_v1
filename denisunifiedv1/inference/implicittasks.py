IMPLICITTASKS = {
    "crea_endpoint": [
        "validate_input_schema",
        "add_cors_headers",
        "add_request_logging",
        "handle_errors_gracefully",
    ],
    "crea_tests": [
        "setup_test_environment",
        "teardown_after_tests",
        "assert_response_status",
        "assert_json_schema",
    ],
    "crea_db_model": ["validate_foreign_keys", "add_timestamps", "add_soft_delete"],
    "crea_api_client": ["add_retry_logic", "add_timeout", "validate_response"],
    "crea_middleware": ["log_request_id", "add_cors", "handle_auth"],
}


def get_implicit_tasks(intent: str) -> list:
    intent_lower = intent.lower()

    for key, tasks in IMPLICITTASKS.items():
        if key in intent_lower:
            return tasks

    return []
