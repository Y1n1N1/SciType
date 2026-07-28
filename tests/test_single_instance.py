"""Tests for single-instance decisions without creating a real mutex."""

import unittest

from scitype.single_instance import (
    ERROR_ALREADY_EXISTS,
    MutexCreation,
    SingleInstanceLock,
    build_mutex_name,
    mutex_already_exists,
)


class _FakeMutexBackend:
    def __init__(self, *, already_exists: bool) -> None:
        self.creation = MutexCreation(
            handle=2468,
            already_exists=already_exists,
        )
        self.created_names: list[str] = []
        self.closed_handles: list[int] = []

    def create_mutex(self, name: str) -> MutexCreation:
        self.created_names.append(name)
        return self.creation

    def close_handle(self, handle: int) -> None:
        self.closed_handles.append(handle)


class SingleInstanceTests(unittest.TestCase):
    def test_mutex_name_is_local_stable_and_hides_user_identity(self) -> None:
        name = build_mutex_name("EXAMPLE\\alice")

        self.assertTrue(name.startswith("Local\\SciType-"))
        self.assertEqual(name, build_mutex_name("EXAMPLE\\alice"))
        self.assertNotIn("alice", name)

    def test_already_exists_error_is_interpreted_explicitly(self) -> None:
        self.assertTrue(mutex_already_exists(ERROR_ALREADY_EXISTS))
        self.assertFalse(mutex_already_exists(0))
        self.assertFalse(mutex_already_exists(5))

    def test_first_instance_is_primary_and_releases_handle(self) -> None:
        backend = _FakeMutexBackend(already_exists=False)

        with SingleInstanceLock(
            name="Local\\SciType-test",
            backend=backend,
        ) as instance:
            self.assertTrue(instance.is_primary)

        self.assertEqual(backend.created_names, ["Local\\SciType-test"])
        self.assertEqual(backend.closed_handles, [2468])
        self.assertFalse(instance.is_primary)

    def test_existing_instance_is_rejected_and_handle_is_released(self) -> None:
        backend = _FakeMutexBackend(already_exists=True)

        with SingleInstanceLock(
            name="Local\\SciType-test",
            backend=backend,
        ) as instance:
            self.assertFalse(instance.is_primary)

        self.assertEqual(backend.closed_handles, [2468])

    def test_context_releases_handle_when_body_raises(self) -> None:
        backend = _FakeMutexBackend(already_exists=False)

        with self.assertRaisesRegex(RuntimeError, "simulated"):
            with SingleInstanceLock(
                name="Local\\SciType-test",
                backend=backend,
            ):
                raise RuntimeError("simulated")

        self.assertEqual(backend.closed_handles, [2468])


if __name__ == "__main__":
    unittest.main()
