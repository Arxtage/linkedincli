class LinkedInCliError(RuntimeError):
    """Base error for linkedincli."""


class AuthenticationError(LinkedInCliError):
    """Raised when the current browser session is not authenticated."""


class DiscoveryError(LinkedInCliError):
    """Raised when managed company pages cannot be discovered."""


class BrowserAutomationError(LinkedInCliError):
    """Raised when browser automation fails."""
