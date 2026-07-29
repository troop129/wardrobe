# CI/CD: Mac push → Windows host auto-deploy

Goal: push to `main` on the fork ([troop129/wardrobe](https://github.com/troop129/wardrobe))
from the Mac, and the Windows host picks it up, rebuilds, and redeploys on its
own — no manually re-running the steps in
[deployment.md](./deployment.md#4-start-the-stack--✅-done) every time.

See [local-dev.md](./local-dev.md) for the fast local test loop that should
be used *before* pushing, since this pipeline runs the full `docker compose
build` and takes a few minutes.

## Why a self-hosted GitHub Actions runner (not a webhook/polling script)

GitHub Actions is already used for lint/test/build on every push (`ci.yml`).
The natural extension is a second workflow that deploys — but it has to run
**on the Windows host itself** (a "self-hosted runner"), because that's where
Docker Desktop and the repo checkout live.

The one thing that constrains *how* that runner has to be installed: see the
"GUI apps / Docker credential" gotchas in
[deployment.md](./deployment.md#gotchas-hit-doing-this-over-ssh-relevant-again-for-step-4)
and [remote-access.md](./remote-access.md). Short version — Docker Desktop's
credential lookup (needed even for anonymous base-image pulls during
`docker compose build`) is tied to the Windows **interactive logon session**.
Anything that runs in a different session — a plain SSH command, or a normal
Windows *service* (which is what `gh actions-runner` installs as by default,
running in Session 0) — gets `error getting credentials ... A specified logon
session does not exist`.

So the runner is installed to run the same way Docker Desktop/Ollama already
do: as a Scheduled Task with `-LogonType Interactive -UserId troop`, living
inside the real console/RDP session. This is more setup than "install the
service and forget it," but it's the same workaround already proven to work
for this host, rather than a second thing to debug.

**Trade-off to accept**: the runner (and therefore auto-deploy) only works
while `troop`'s interactive session is active. If the PC reboots and nobody
logs in, pushes queue up in GitHub until someone opens an RDP session (or the
console) — they don't get lost, just delayed. This is a personal single-host
setup, not a 24/7 fleet, so that's an acceptable trade rather than reaching
for Windows auto-logon (which trades away meaningfully more security for
convenience — do that yourself if you decide it's worth it, it's not done
here by default).

## How it works

1. Push to `main` → `ci.yml` runs (lint/test/build) on GitHub-hosted runners,
   same as always.
2. If `ci.yml` succeeds, `deploy.yml` fires via a `workflow_run` trigger and
   is picked up by the self-hosted runner on the Windows host.
3. That job, in `C:\Users\troop\wardrowbe`:
   ```powershell
   git fetch origin main
   git reset --hard origin/main
   docker compose build
   docker compose up -d
   docker compose exec -T backend alembic upgrade head
   ```
4. It polls `http://localhost:8000/api/v1/health` for up to a minute; if that
   never returns 200, the job fails loudly (and dumps the last 100 lines of
   backend logs) instead of silently leaving a broken deploy running.

You can also trigger it manually from the Actions tab (`workflow_dispatch`)
without needing a new push — useful the first time, or to redeploy without a
code change (e.g. after editing `.env` on the host).

`concurrency: group: wardrobe-deploy` means if you push twice quickly, the
second deploy waits for the first to finish rather than running two
`docker compose build`s at once.

## One-time setup

### 1. Register the runner (GitHub side)

On `troop129/wardrobe` → **Settings → Actions → Runners → New self-hosted
runner → Windows, x64**. Leave that page open — it shows a one-time
registration token and the exact `config.cmd` command to run.

### 2. Install it on the Windows host

Over SSH (`ssh wardrobe-win`), following the same pattern as the Docker
Desktop/Ollama setup:

```powershell
mkdir C:\actions-runner
cd C:\actions-runner
# URL from the GitHub Actions "download" step for Windows x64
Invoke-WebRequest -Uri <the .zip URL from GitHub> -OutFile actions-runner.zip
Expand-Archive -Path actions-runner.zip -DestinationPath .

# Configure (token from step 1). Custom label is what the workflow's
# `runs-on: [self-hosted, wardrobe-host]` targets.
.\config.cmd --url https://github.com/troop129/wardrobe --token <TOKEN> --labels wardrobe-host --unattended
```

**Do not** run `.\svc.sh install` / install it as a Windows service, and
don't just background `run.cmd` over the raw SSH session — both end up in a
non-interactive logon session and hit the same Docker credential error
documented above. Instead, register a Scheduled Task the same way as the
`LaunchOllamaApp` task described in
[deployment.md](./deployment.md#gotchas-hit-doing-this-over-ssh-relevant-again-for-step-4):

```powershell
$action = New-ScheduledTaskAction -Execute "C:\actions-runner\run.cmd"
$trigger = New-ScheduledTaskTrigger -AtLogOn -User troop
$principal = New-ScheduledTaskPrincipal -UserId troop -LogonType Interactive -RunLevel Highest
Register-ScheduledTask -TaskName "GitHubActionsRunner" -Action $action -Trigger $trigger -Principal $principal

# Start it now instead of waiting for the next login
Start-ScheduledTask -TaskName "GitHubActionsRunner"
```

Confirm it's listening: the GitHub runners page should show it **Idle**
(green), and:

```powershell
Get-ScheduledTask -TaskName "GitHubActionsRunner" | Get-ScheduledTaskInfo
```

### 3. Verify the repo clone matches what the workflow expects

`deploy.yml` hardcodes `working-directory: C:\Users\troop\wardrowbe` — that's
the clone from [deployment.md step 2](./deployment.md#2-get-the-repo-onto-the-windows-host--✅-done).
Confirm `git remote -v` there points at `troop129/wardrobe` (the fork the
runner is registered against), not the upstream `Anyesh/wardrowbe`.

### 4. Push `deploy.yml` and test it

This file only takes effect once it's on `main` of `troop129/wardrobe`. Push
it, then either push a trivial follow-up commit or use **Actions → Deploy to
homelab → Run workflow** to trigger it manually the first time. Watch the run
— it should finish with `Deployed <sha> OK`.

## Rollback

If a deploy goes out with a real bug: on the Windows host (SSH is fine for
`git`/`docker` read-only-ish commands; use the Scheduled Task trick above
only for things that need image pulls/builds),

```powershell
cd C:\Users\troop\wardrowbe
git log --oneline -5          # find the last good commit
git reset --hard <good-sha>
```

Then either wait for the next push (which will re-deploy `main`, so make sure
`main` on GitHub is also reverted/fixed), or run **Actions → Deploy to
homelab → Run workflow** against the branch you just reset to, to force an
immediate rebuild from that state — remembering that `deploy.yml` does
`git reset --hard origin/main`, so a manual `git reset` on the host alone will
get overwritten by the next auto-deploy unless `main` on GitHub matches.

## Troubleshooting

- **Job fails immediately with `running scripts is disabled on this system`
  (`PSSecurityException`)**: Windows PowerShell's default execution policy on
  this host blocks the temp `.ps1` file GitHub Actions generates for each
  `run:` step. `deploy.yml` already works around this by setting
  `shell: powershell -ExecutionPolicy Bypass -Command ". '{0}'"` at the job
  level instead of changing the host's execution policy machine-wide — if
  you add a new self-hosted workflow and forget this, you'll hit the same
  error.
- **Runner shows Offline on GitHub**: `troop`'s interactive session isn't
  active (PC rebooted, nobody logged into console/RDP since). Log in and the
  Scheduled Task's `AtLogOn` trigger should start it; or
  `Start-ScheduledTask -TaskName "GitHubActionsRunner"` manually.
- **Job fails on `docker compose build` with a credentials error**: the
  runner process ended up in the wrong session after all (e.g. someone
  disabled the Scheduled Task and ran `run.cmd` by hand over SSH). Re-check
  it's running via the Scheduled Task, not a raw shell.
- **Health check fails but containers look up**: `docker compose logs
  backend` (the job already dumps the last 100 lines on failure) — usually a
  migration issue or a bad `.env` value merged into `main`.
