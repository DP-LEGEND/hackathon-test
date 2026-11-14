"""Smoke test: the physics modules import. Replace with real tests as you build."""


def test_modules_import() -> None:
    from physics import ball, faults, ghost, metrics  # noqa: F401
