"""Control Room — Task lifecycle, approval policies, and background worker.

Fail-open for reads (visibility). Fail-closed for dangerous mutations (require approval).
Graph is the SSoT for all Task/Run/Step/Approval state.
"""
