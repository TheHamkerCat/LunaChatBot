"""Limits on /luna requests that wait for an answer, so a busy group can't
pile them up."""

# ARQ works on one request per API key and keeps 5 more waiting. The bot
# never has more than that open, so ARQ never has to refuse one.
MAX_WAITING = 6

# WaitingRequests.add() results
ADDED = "added"
USER_WAITING = "user_waiting"
FULL = "full"


class WaitingRequests:
    """At most one open request per user, and at most `limit` in all"""

    def __init__(self, limit: int = MAX_WAITING):
        self.limit = limit
        self.users = set()

    def add(self, user_key: int) -> str:
        """ADDED, or why not: USER_WAITING (this user's last message is
        still open) or FULL. After ADDED, call remove() when done."""
        if user_key in self.users:
            return USER_WAITING
        if len(self.users) >= self.limit:
            return FULL
        self.users.add(user_key)
        return ADDED

    def remove(self, user_key: int):
        self.users.discard(user_key)
