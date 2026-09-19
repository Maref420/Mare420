"""
CLI Interface for ATLAS AI Agent
"""
import argparse
import os
import sys

from .models import Language, Requirement
from .orchestrator import Orchestrator


def main() -> None:
    parser = argparse.ArgumentParser(description="ATLAS AI Agent - Governance-Driven Code Generation")
    parser.add_argument("--requirement", required=True, help="Description of the requirement")
    parser.add_argument("--language", required=True, choices=["python", "rust", "go"], help="Programming language")
    parser.add_argument("--project-name", required=True, help="Name of the project")
    parser.add_argument("--target-folder", required=True, help="Target folder for generated code")
    parser.add_argument("--architecture", required=True, help="Architecture description")
    parser.add_argument("--modules", nargs="+", required=True, help="List of modules to generate")
    parser.add_argument("--auto-approve", action="store_true", help="Skip human approval (for CI/non-interactive use)")
    parser.add_argument(
        "--pipeline-version",
        choices=["v1", "v2"],
        default=None,
        help="Pipeline version to use (default: env ATLAS_PIPELINE_VERSION or v1)",
    )

    args = parser.parse_args()

    try:
        req = Requirement(
            description=args.requirement,
            language=Language(args.language),
            project_name=args.project_name,
            target_folder=args.target_folder
        )

        orchestrator = Orchestrator(auto_approve=True if args.auto_approve else None)

        # Resolve pipeline version: CLI flag > env var > default v1
        pipeline_version = args.pipeline_version or os.environ.get("ATLAS_PIPELINE_VERSION", "v1")

        if pipeline_version == "v2":
            artifact = orchestrator.run_pipeline_v2(req, args.architecture, args.modules)
        else:
            artifact = orchestrator.run_pipeline(req, args.architecture, args.modules)

        if artifact.status.value == "approved":
            print("\n✅ Pipeline completed successfully!")
            print(f"Artifact saved to: {args.target_folder}")
        else:
            print("\n❌ Pipeline rejected.")
            sys.exit(1)

except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"\n❌  Pipeline Error: {e}", file=sys.stderr)
        print(f"\n🔍 Traceback:\n{error_details}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
