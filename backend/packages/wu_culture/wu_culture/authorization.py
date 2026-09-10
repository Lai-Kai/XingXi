from __future__ import annotations

from datetime import UTC, datetime

from .models import AuthorizationStatus, AuthorizedUse, SourceAccessDecision, SourceDocument, VisibilityScope


def evaluate_source_access(
    document: SourceDocument,
    *,
    use: AuthorizedUse,
    now: datetime | None = None,
) -> SourceAccessDecision:
    """Apply the default-deny source authorization policy."""
    checked_at = now or datetime.now(UTC)
    status = document.authorization_status
    if status is not AuthorizationStatus.ACTIVE:
        return SourceAccessDecision(
            use=use,
            allowed=False,
            reason=f"authorization_{status.value}",
            effective_status=status,
        )
    if document.authorization_valid_from is not None and checked_at < document.authorization_valid_from:
        return SourceAccessDecision(
            use=use,
            allowed=False,
            reason="authorization_not_yet_valid",
            effective_status=status,
        )
    if document.authorization_valid_until is not None and checked_at >= document.authorization_valid_until:
        return SourceAccessDecision(
            use=use,
            allowed=False,
            reason="authorization_expired",
            effective_status=AuthorizationStatus.EXPIRED,
        )
    if use not in document.authorized_uses:
        return SourceAccessDecision(
            use=use,
            allowed=False,
            reason="use_not_authorized",
            effective_status=status,
        )
    if use in {AuthorizedUse.PUBLIC_FULL_TEXT, AuthorizedUse.PUBLIC_QUOTE} and document.visibility_scope is not VisibilityScope.PUBLIC:
        return SourceAccessDecision(
            use=use,
            allowed=False,
            reason="visibility_restricted",
            effective_status=status,
        )
    return SourceAccessDecision(
        use=use,
        allowed=True,
        reason="authorized",
        effective_status=status,
    )
