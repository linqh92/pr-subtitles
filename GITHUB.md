# GitHub setup

## Repository root

Use the `pr-subtitles` folder as the Git repository root. `run.py`, `subtitle.py`, `requirements.txt`, and `.github/` must be at the root, rather than inside another `pr-subtitles` folder.

The local default branch is `main`. `.gitattributes` keeps source line endings consistent on Windows and macOS; `.editorconfig` sets editor defaults. These settings apply only to this project.

## Upload scope

Commit the Python scripts, tests, requirements, guides, and GitHub configuration. `.gitignore` excludes environments, downloaded models, output captions/reports, audio/video, and local credentials. Store private TXT narration in `inputs/`, which is ignored. TXT files in the repository root are not automatically ignored, because `requirements.txt` and the usage guide are project sources.

Before each upload, inspect `git status --short` and `git diff --cached`. Do not force-add ignored data. Do not upload `.venv`, `.cache`, `output`, or original client materials.

## Connect to GitHub

1. Sign in using `gh auth login --hostname github.com --web`, then verify with `gh auth status`. Alternatively use GitHub Desktop to authenticate and publish this local repository.
2. Create an empty GitHub repository under the intended account. When connecting this existing project, do not initialize the remote with another README, license, or `.gitignore`.
3. Copy the repository URL and add it as the local remote:

```text
git remote add origin <repository-url>
git remote -v
```

If `origin` already exists, inspect it first. Change it only if it points to the wrong repository.

4. Review the proposed files and commit message, then commit and upload:

```text
git add .
git diff --cached --stat
git diff --cached
git commit -m "Initial cross-platform Python subtitle tool"
git push -u origin main
```

These commands assume an empty remote repository. If the remote already has commits, fetch and review its history first; do not force-push.

## Automated checks

`.github/workflows/checks.yml` runs on pushes and pull requests to `main`, or manually from the Actions page. It installs the speech dependencies, checks imports/CPU support, runs unit checks, and verifies the Python help entry point on Windows and macOS with Python 3.12. It does not download a speech model or run private narration through recognition.

The workflow has not run on GitHub until the repository has been uploaded. Passing checks demonstrate the covered behaviors and dependency installation, not frame-accurate alignment for every audio file.

## License

No open-source license is selected automatically. Choose a license deliberately before distributing the project as open-source. Public visibility and an open-source license are separate choices.
