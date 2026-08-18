import unittest
from pathlib import Path

import yaml

POLICY_PATH = Path(
    "governance/policies/memory/lifecycle-policy.yaml"
)


def load_policy() -> dict:
    return yaml.safe_load(POLICY_PATH.read_text())


class TestMemoryLifecyclePolicy(unittest.TestCase):

    def test_lifecycle_policy_exists(self) -> None:
        self.assertTrue(POLICY_PATH.exists())

    def test_only_validated_memory_may_persist(self) -> None:
        policy = load_policy()

        self.assertFalse(
            policy["validation"]["pending_memory"]["persistence_allowed"]
        )
        self.assertFalse(
            policy["validation"]["rejected_memory"]["persistence_allowed"]
        )
        self.assertTrue(
            policy["validation"]["validated_memory"]["persistence_allowed"]
        )

    def test_forgetting_requires_kernel_and_audit(self) -> None:
        policy = load_policy()

        self.assertTrue(
            policy["operations"]["forget"]["kernel_required"]
        )
        self.assertTrue(
            policy["operations"]["forget"]["audit_required"]
        )

    def test_uncontrolled_deletion_is_forbidden(self) -> None:
        policy = load_policy()

        self.assertEqual(
            policy["security"]["uncontrolled_deletion"],
            "prohibited",
        )
        self.assertEqual(
            policy["security"]["direct_database_access"],
            "prohibited",
        )

    def test_all_memory_types_have_lifecycle_policy(self) -> None:
        policy = load_policy()

        for memory_type in (
            "working",
            "episodic",
            "semantic",
            "procedural",
        ):
            self.assertIn(
                memory_type,
                policy["memory_types"],
            )


if __name__ == "__main__":
    unittest.main()
