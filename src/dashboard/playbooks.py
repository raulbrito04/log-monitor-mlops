from __future__ import annotations

PLAYBOOKS: dict[str, dict[str, object]] = {
    "brute_force": {
        "title": "Brute Force Response",
        "summary": "Validate if the source IP is repeatedly targeting the login flow.",
        "steps": [
            "Review the related login attempts and targeted usernames.",
            "Check whether the source IP matches an internal test runner or automation.",
            "Block or throttle the IP if the behavior is malicious.",
            "Reset impacted credentials if a valid account was exposed.",
        ],
    },
    "sql_injection": {
        "title": "SQL Injection Response",
        "summary": "Confirm whether the request path or query string contains injection probes.",
        "steps": [
            "Inspect the raw endpoint and request metadata for payload patterns.",
            "Verify if the request reached a sensitive route or caused a server error.",
            "Block the source IP and preserve logs for incident follow-up.",
            "Review application sanitization coverage for the affected endpoint.",
        ],
    },
    "port_scanning": {
        "title": "Scanning Response",
        "summary": "Assess broad endpoint discovery or reconnaissance behavior.",
        "steps": [
            "Inspect the list of unique endpoints touched in the selected time window.",
            "Correlate with user-agent and response codes to confirm reconnaissance.",
            "Apply temporary IP controls if the behavior is sustained.",
            "Review whether newly exposed endpoints need tighter access control.",
        ],
    },
    "path_traversal": {
        "title": "Path Traversal Response",
        "summary": "Investigate attempts to access files outside the expected document root.",
        "steps": [
            "Validate whether the endpoint contains traversal markers or file disclosure probes.",
            "Confirm that the request did not return protected system file content.",
            "Block the source and preserve request context for further analysis.",
            "Review route sanitization and path normalization defenses.",
        ],
    },
    "suspicious_user_agent": {
        "title": "Suspicious Tooling Response",
        "summary": "Identify whether the source is using known offensive tooling.",
        "steps": [
            "Confirm the user-agent and endpoints touched by the request set.",
            "Check if the IP overlaps with approved test infrastructure.",
            "Escalate repeated activity to incident handling if it targets sensitive endpoints.",
        ],
    },
    "time_anomaly": {
        "title": "Off-hours Activity Response",
        "summary": "Assess unusual request bursts outside expected business hours.",
        "steps": [
            "Review whether the IP or user pattern has a legitimate operational reason.",
            "Correlate with other alerts or anomaly scores around the same time.",
            "Escalate only if the activity is sustained or combined with other indicators.",
        ],
    },
}

DEFAULT_PLAYBOOK = {
    "title": "Generic Investigation",
    "summary": "Use the related logs and anomaly signals to determine whether escalation is required.",
    "steps": [
        "Review timestamps, IP, endpoint, and severity for the selected item.",
        "Pivot into related logs and anomaly scores to understand surrounding behavior.",
        "Escalate if multiple indicators align or if the affected asset is sensitive.",
    ],
}


def get_playbook(alert_type: str) -> dict[str, object]:
    return PLAYBOOKS.get(alert_type, DEFAULT_PLAYBOOK)
