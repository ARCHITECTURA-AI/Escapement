"""Episode endings (section 11.3). Engine errors stay distinct from agent failures."""

IN_PROGRESS = "in_progress"

ESCAPED = "escaped"
ACTION_BUDGET_EXHAUSTED = "action_budget_exhausted"
MALFORMED_LIMIT_REACHED = "malformed_limit_reached"
IDLE_TIMEOUT = "idle_timeout"
WALL_CLOCK_EXCEEDED = "wall_clock_exceeded"
CLIENT_ABORTED = "client_aborted"
CANCELLED = "cancelled"
ENGINE_ERROR = "engine_error"
REFERENCE_PROVIDER_FAILURE = "reference_provider_failure"

ENDINGS = (
    ESCAPED,
    ACTION_BUDGET_EXHAUSTED,
    MALFORMED_LIMIT_REACHED,
    IDLE_TIMEOUT,
    WALL_CLOCK_EXCEEDED,
    CLIENT_ABORTED,
    CANCELLED,
    ENGINE_ERROR,
    REFERENCE_PROVIDER_FAILURE,
)

# Endings the server or client imposes from outside the engine's rules.
SYSTEM_ENDINGS = (
    IDLE_TIMEOUT,
    WALL_CLOCK_EXCEEDED,
    CLIENT_ABORTED,
    CANCELLED,
    ENGINE_ERROR,
    REFERENCE_PROVIDER_FAILURE,
)

# Endings that count as the agent's own failure, versus infrastructure.
AGENT_FAILURES = (
    ACTION_BUDGET_EXHAUSTED,
    MALFORMED_LIMIT_REACHED,
    IDLE_TIMEOUT,
    WALL_CLOCK_EXCEEDED,
    CLIENT_ABORTED,
)
INFRASTRUCTURE_ENDINGS = (CANCELLED, ENGINE_ERROR, REFERENCE_PROVIDER_FAILURE)

ENDING_LABELS = {
    ESCAPED: "Escaped",
    ACTION_BUDGET_EXHAUSTED: "Action budget exhausted",
    MALFORMED_LIMIT_REACHED: "Malformed-request limit reached",
    IDLE_TIMEOUT: "Idle timeout",
    WALL_CLOCK_EXCEEDED: "Wall-clock limit exceeded",
    CLIENT_ABORTED: "Ended by client",
    CANCELLED: "Cancelled by operator",
    ENGINE_ERROR: "Engine error",
    REFERENCE_PROVIDER_FAILURE: "Reference provider failure",
}
