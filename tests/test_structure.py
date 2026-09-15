from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_architecture_baseline_directories_exist() -> None:
    required = [
        "apps/extension",
        "apps/web",
        "services/api/app",
        "services/api/domains",
        "services/api/platform",
        "services/worker",
        "services/worker-renderer",
        "packages/contracts-py",
        "packages/contracts-ts",
        "contracts",
        "migrations",
        "config",
        "tests/contract",
        "tests/golden",
        "tests/e2e",
        "tests/security",
    ]
    missing = [path for path in required if not (ROOT / path).exists()]
    assert missing == []
