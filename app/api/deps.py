from collections.abc import Callable

from fastapi import Depends

from app.core.errors import ForbiddenError
from app.security.principal import Principal, get_current_principal


def require_roles(*allowed_roles: str) -> Callable[[Principal], Principal]:
    def _check(principal: Principal = Depends(get_current_principal)) -> Principal:
        if principal.role not in allowed_roles:
            raise ForbiddenError(
                f"This action requires one of roles {list(allowed_roles)}; "
                f"caller has role '{principal.role}'."
            )
        return principal

    return _check


require_owner = require_roles("owner")
require_admin_or_owner = require_roles("admin", "owner")
