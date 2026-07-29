"""Compatibility/debug entry point; startup logic lives in :mod:`scitype.app`."""

from scitype.app import (
    ApplicationStatus,
    _console_message,
    main,
    run_windows_application,
    show_windows_message,
    verify_packaged_resources,
)

__all__ = [
    "ApplicationStatus",
    "_console_message",
    "main",
    "run_windows_application",
    "show_windows_message",
    "verify_packaged_resources",
]


if __name__ == "__main__":
    raise SystemExit(main())
