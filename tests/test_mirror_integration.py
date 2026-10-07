import subprocess

from harness.engine.mirror import GitMirror


def _git(*args, cwd=None) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def _source_repo(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    _git("init", "-b", "main", cwd=source)
    _git("config", "user.email", "test@example.gov", cwd=source)
    _git("config", "user.name", "Test User", cwd=source)
    (source / "file.txt").write_text("first\n")
    _git("add", "file.txt", cwd=source)
    _git("commit", "-m", "first", cwd=source)
    first = _git("rev-parse", "HEAD", cwd=source)
    (source / "file.txt").write_text("second\n")
    _git("commit", "-am", "second", cwd=source)
    second = _git("rev-parse", "HEAD", cwd=source)
    return source, first, second


def test_detached_head_pushes_checked_out_commit_not_stale_main(tmp_path):
    source, first, second = _source_repo(tmp_path)
    destination = tmp_path / "destination.git"
    _git("init", "--bare", str(destination))
    _git("checkout", "--detach", first, cwd=source)

    result = GitMirror({"mirror": str(destination)}, cwd=str(source)).push(
        "HEAD", "main", ["mirror"], dry_run=False
    )[0]

    assert result.ok
    assert _git("rev-parse", "refs/heads/main", cwd=destination) == first
    assert first != second


def test_existing_destination_requires_explicit_override(tmp_path):
    source, first, second = _source_repo(tmp_path)
    destination = tmp_path / "destination.git"
    _git("init", "--bare", str(destination))
    _git("push", str(destination), f"{first}:refs/heads/main", cwd=source)

    blocked = GitMirror({"mirror": str(destination)}, cwd=str(source)).push(
        "HEAD", "main", ["mirror"], dry_run=False
    )[0]
    assert not blocked.ok
    assert _git("rev-parse", "refs/heads/main", cwd=destination) == first

    allowed = GitMirror({"mirror": str(destination)}, cwd=str(source)).push(
        "HEAD", "main", ["mirror"], dry_run=False, allow_existing=True
    )[0]
    assert allowed.ok
    assert _git("rev-parse", "refs/heads/main", cwd=destination) == second


def test_review_branch_preserves_unrelated_default_branch(tmp_path):
    source, _, second = _source_repo(tmp_path)
    destination = tmp_path / "destination.git"
    _git("init", "--bare", str(destination))
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    _git("init", "-b", "main", cwd=unrelated)
    _git("config", "user.email", "test@example.gov", cwd=unrelated)
    _git("config", "user.name", "Test User", cwd=unrelated)
    (unrelated / "seed.txt").write_text("seed\n")
    _git("add", "seed.txt", cwd=unrelated)
    _git("commit", "-m", "seed", cwd=unrelated)
    seed = _git("rev-parse", "HEAD", cwd=unrelated)
    _git("push", str(destination), "HEAD:refs/heads/main", cwd=unrelated)

    result = GitMirror({"mirror": str(destination)}, cwd=str(source)).push(
        "HEAD", "mirror/source", ["mirror"], dry_run=False
    )[0]

    assert result.ok
    assert _git("rev-parse", "refs/heads/main", cwd=destination) == seed
    assert _git("rev-parse", "refs/heads/mirror/source", cwd=destination) == second
