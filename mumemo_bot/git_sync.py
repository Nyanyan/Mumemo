from dataclasses import dataclass
import subprocess

from mumemo_bot.config import PROJECT_ROOT


SITE_PATHSPEC = "docs"


@dataclass(frozen=True)
class GitSyncResult:
    committed: bool
    pushed: bool
    commit_hash: str | None
    commit_message: str


class GitSyncError(RuntimeError):
    pass


def commit_and_push_site_changes(action: str, title: str) -> GitSyncResult:
    commit_message = _commit_message(action, title)
    _run_git(["add", "-A", SITE_PATHSPEC])

    diff_result = _run_git(
        ["diff", "--cached", "--quiet", "--", SITE_PATHSPEC],
        check=False,
    )
    if diff_result.returncode == 0:
        return GitSyncResult(
            committed=False,
            pushed=False,
            commit_hash=None,
            commit_message=commit_message,
        )
    if diff_result.returncode != 1:
        raise GitSyncError(_format_git_error("diff --cached --quiet", diff_result))

    _run_git(["commit", "-m", commit_message, "--", SITE_PATHSPEC])
    commit_hash = _run_git(["rev-parse", "--short", "HEAD"]).stdout.strip() or None
    _run_git(["push", "origin", "main"])
    return GitSyncResult(
        committed=True,
        pushed=True,
        commit_hash=commit_hash,
        commit_message=commit_message,
    )


def _commit_message(action: str, title: str) -> str:
    clean_action = " ".join(action.split()) or "update"
    clean_title = " ".join(title.split()) or "memo"
    return f"{clean_action} {clean_title}"


def _run_git(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and result.returncode != 0:
        raise GitSyncError(_format_git_error(" ".join(args), result))
    return result


def _format_git_error(command: str, result: subprocess.CompletedProcess[str]) -> str:
    output = (result.stderr or result.stdout).strip()
    if len(output) > 1000:
        output = output[:997] + "..."
    detail = f": {output}" if output else ""
    return f"git {command} failed with exit code {result.returncode}{detail}"
