"""Single import point for the IB API library.

Prefers ib_async (the maintained community fork of ib_insync — identical API);
falls back to ib_insync if that's what is installed.
"""

try:  # pragma: no cover - import shim
    from ib_async import (  # noqa: F401
        IB,
        ComboLeg,
        Contract,
        Future,
        Index,
        Option,
        Order,
        util,
    )
except ImportError:  # pragma: no cover
    from ib_insync import (  # noqa: F401
        IB,
        ComboLeg,
        Contract,
        Future,
        Index,
        Option,
        Order,
        util,
    )
