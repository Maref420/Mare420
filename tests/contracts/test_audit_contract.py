import json
import unittest
from pathlib import Path

CONTRACT_PATH = Path(
    "contracts/schemas/audit/audit-contract-v1.json"
)


class TestAuditContract(unittest.TestCase):
    def load_contract(self) -> dict:
        return json.loads(CONTRACT_PATH.read_text())

    def test_contract_exists(self) -> None:
        self.assertTrue(CONTRACT_PATH.exists())

    def test_contract_identity(self) -> None:
        contract = self.load_contract()

        self.assertEqual(contract["version"], "1.0")
        self.assertEqual(contract["type"], "audit-contract")
        self.assertEqual(
            contract["ownership"]["owner"],
            "Agent Control Plane",
        )

    def test_required_traceability_fields(self) -> None:
        contract = self.load_contract()

        required = set(contract["required_fields"])

        self.assertTrue(
            {
                "event_id",
                "operation_id",
                "agent_id",
                "timestamp",
            }.issubset(required)
        )

    def test_security_rules(self) -> None:
        contract = self.load_contract()

        rules = contract["rules"]

        self.assertTrue(rules["schema_validation_required"])
        self.assertTrue(rules["immutable_record_required"])
        self.assertTrue(rules["agent_identity_required"])
        self.assertTrue(rules["operation_traceability_required"])
        self.assertTrue(rules["timestamp_validation_required"])
        self.assertTrue(rules["unknown_fields_rejected"])
        self.assertTrue(rules["sensitive_data_logging_prohibited"])

    def test_direct_database_access_is_forbidden(self) -> None:
        contract = self.load_contract()

        self.assertTrue(
            contract["storage"]["direct_database_access_forbidden"]
        )

    def test_audit_operations_are_controlled(self) -> None:
        contract = self.load_contract()

        self.assertEqual(
            contract["operations"],
            ["record", "retrieve"],
        )


if __name__ == "__main__":
    unittest.main()
