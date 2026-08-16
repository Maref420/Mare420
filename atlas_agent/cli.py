"""
CLI Interface for ATLAS AI Agent
"""
import argparse
import sys
from .models import Requirement, Language
from .orchestrator import Orchestrator

def main():
    parser = argparse.ArgumentParser(description="ATLAS AI Agent - Governance-Driven Code Generation")
    parser.add_argument("--requirement", required=True, help="Description of the requirement")
    parser.add_argument("--language", required=True, choices=["python", "rust", "go"], help="Programming language")
    parser.add_argument("--project-name", required=True, help="Name of the project")
    parser.add_argument("--target-folder", required=True, help="Target folder for generated code")
    parser.add_argument("--architecture", required=True, help="Architecture description")
    parser.add_argument("--modules", nargs="+", required=True, help="List of modules to generate")

    args = parser.parse_args()

    try:
        req = Requirement(
            description=args.requirement,
            language=Language(args.language),
            project_name=args.project_name,
            target_folder=args.target_folder
        )

        orchestrator = Orchestrator()
        artifact = orchestrator.run_pipeline(req, args.architecture, args.modules)

        if artifact.status.value == "approved":
            print("\n✅ Pipeline completed successfully!")
            print(f"Artifact saved to: {args.target_folder}")
        else:
            print("\n❌ Pipeline rejected.")
            sys.exit(1)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)
