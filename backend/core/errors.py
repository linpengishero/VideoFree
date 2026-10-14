class JobCancelled(Exception):
    """Raised when a generation job is cancelled cooperatively."""


class AgentCollaborationCancelled(Exception):
    """Raised when an active director collaboration is cancelled."""
