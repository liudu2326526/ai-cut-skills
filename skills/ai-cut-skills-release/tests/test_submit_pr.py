import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "submit_pr.py"
SPEC = importlib.util.spec_from_file_location("submit_pr", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class SubmitPrHelpersTests(unittest.TestCase):
    def test_branch_name_contains_group_scope_and_date(self) -> None:
        self.assertEqual(
            MODULE.build_branch_name("014-code", "fix", "usergrowth", "20260903"),
            "014-code/fix-usergrowth-20260903",
        )

    def test_rejects_unsafe_scope(self) -> None:
        with self.assertRaises(MODULE.ReleaseError):
            MODULE.build_branch_name("014-code", "fix", "../main", "20260903")

    def test_path_allowlist_is_directory_aware(self) -> None:
        allowed = ["skills/demo", "tests/test_demo.py"]
        self.assertTrue(MODULE.path_is_allowed("skills/demo/scripts/run.py", allowed))
        self.assertTrue(MODULE.path_is_allowed("tests/test_demo.py", allowed))
        self.assertFalse(MODULE.path_is_allowed("skills/demo-extra/run.py", allowed))

    def test_normalizes_relative_paths(self) -> None:
        self.assertEqual(MODULE.normalize_relative_path("tests\\test_demo.py"), "tests/test_demo.py")
        with self.assertRaises(MODULE.ReleaseError):
            MODULE.normalize_relative_path("../outside.txt")

    def test_builds_force_with_lease_push_for_existing_managed_branch(self) -> None:
        self.assertEqual(
            MODULE.build_push_args("origin", "014-code/fix-demo-20260903", "a" * 40),
            [
                "git",
                "push",
                "--force-with-lease=refs/heads/014-code/fix-demo-20260903:" + "a" * 40,
                "--set-upstream",
                "origin",
                "014-code/fix-demo-20260903",
            ],
        )

    def test_refuses_existing_remote_branch_without_open_pr(self) -> None:
        with self.assertRaisesRegex(MODULE.ReleaseError, "没有找到.*打开 PR"):
            MODULE.validate_remote_branch_reuse("014-code/fix-demo-20260903", "a" * 40, None)

    def test_allows_existing_remote_branch_only_with_open_pr(self) -> None:
        MODULE.validate_remote_branch_reuse(
            "014-code/fix-demo-20260903",
            "a" * 40,
            {"number": 12, "url": "https://github.com/acme/demo/pull/12"},
        )

    def test_finds_only_matching_open_pr(self) -> None:
        with patch.object(
            MODULE,
            "run_command",
            return_value='[{"number": 12, "url": "https://example.test/pr/12", "headRefName": "demo", "baseRefName": "main"}]',
        ):
            result = MODULE.find_open_pr(Path("."), "acme/demo", "demo", "octocat", "main")

        self.assertEqual(result["number"] if result else None, 12)

    def test_plan_includes_staged_changes_when_repository_has_a_head(self) -> None:
        with patch.object(MODULE, "run_command", side_effect=["staged.py", ""]):
            tracked, untracked = MODULE.list_changed_paths(Path("."), None, ["skills/demo"])

        self.assertEqual(tracked, ["staged.py"])
        self.assertEqual(untracked, [])


if __name__ == "__main__":
    unittest.main()
