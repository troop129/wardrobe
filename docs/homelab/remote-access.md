# Remote shell access (Mac dev machine → Windows host)

This Cursor session runs on the Mac, but the app is hosted on the Windows PC.
To let the agent (or you) run commands directly on the Windows host over SSH,
we set up key-based OpenSSH access. This doc records exactly how, so it can be
redone/debugged without re-deriving it.

## Why SSH instead of something else

Both machines are already on the same home LAN, so plain OpenSSH (built into
Windows 10/11) is the simplest option — no extra software, no VPN, no cloud
relay. This is purely for **dev/setup convenience**; it is unrelated to how end
users (tablet, phone, eventually a second person) access the *app* itself — see
[deployment.md](./deployment.md) and [roadmap.md](./roadmap.md) for that.

## Current setup

| Item | Value |
|---|---|
| Windows host | `10.0.0.246` (hostname `desktop-lms2bct`), home WiFi `RasheedFamily 4` |
| Windows user | `troop` (member of local `Administrators`) |
| SSH alias (Mac side) | `wardrobe-win` — defined in `~/.ssh/config` on the Mac |
| Key pair (Mac side) | `~/.ssh/wardrobe_win_ed25519` (private) / `~/.ssh/wardrobe_win_ed25519.pub` (public) — dedicated key, separate from any personal SSH key |
| Authorized key file (Windows side) | `C:\ProgramData\ssh\administrators_authorized_keys` (required for admin accounts — see below) |

`~/.ssh/config` entry on the Mac:

```
Host wardrobe-win
  HostName 10.0.0.246
  User troop
  IdentityFile ~/.ssh/wardrobe_win_ed25519
  IdentitiesOnly yes
```

With this in place, `ssh wardrobe-win` connects with no password prompt.

The **public** key currently authorized (safe to share/back up — never commit
the private half anywhere):

```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIL3bd82/pMxhYW6wG9h8q0yF2Hyhz1KMtVcoXFc2oOVY cursor-agent@wardrobe-setup
```

## How it was set up (for redoing on a fresh machine, or a second dev machine)

On the **Windows host**, in an Administrator PowerShell:

```powershell
# Install and start the OpenSSH server
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
Start-Service sshd
Set-Service -Name sshd -StartupType Automatic

# Confirm the firewall rule exists and is enabled
Get-NetFirewallRule -Name 'OpenSSH-Server-In-TCP'
```

On the machine that needs access (e.g. the Mac):

```bash
ssh-keygen -t ed25519 -f ~/.ssh/wardrobe_win_ed25519 -N "" -C "cursor-agent@wardrobe-setup"
cat ~/.ssh/wardrobe_win_ed25519.pub   # copy this
```

Back on the **Windows host**, authorize that public key. Because `troop` is a
local Administrator, Windows requires the *admin-specific* authorized_keys
file (a plain per-user `~/.ssh/authorized_keys` is ignored for admin accounts):

```powershell
$key = "ssh-ed25519 AAAA...your-public-key... cursor-agent@wardrobe-setup"
Add-Content -Path C:\ProgramData\ssh\administrators_authorized_keys -Value $key

# Required: lock down permissions or sshd will refuse to use the file
icacls.exe "C:\ProgramData\ssh\administrators_authorized_keys" /inheritance:r
icacls.exe "C:\ProgramData\ssh\administrators_authorized_keys" /grant "Administrators:F"
icacls.exe "C:\ProgramData\ssh\administrators_authorized_keys" /grant "SYSTEM:F"

Restart-Service sshd
```

Then from the client machine, accept the host key and connect:

```bash
ssh -o StrictHostKeyChecking=accept-new wardrobe-win "whoami"
```

## Problems hit during setup (and fixes)

1. **`ssh: connect ... Operation timed out`** even though `sshd` was
   `Running` and listening on `0.0.0.0:22`.
   - Cause: `Get-NetConnectionProfile` showed the WiFi network as
     `NetworkCategory: Public`. Windows' auto-created `OpenSSH-Server-In-TCP`
     firewall rule only applies to the `Private`/`Domain` profiles by default,
     so inbound connections were silently dropped on a `Public` profile.
   - Fix: reclassify the trusted home network as Private:
     ```powershell
     Set-NetConnectionProfile -InterfaceAlias "Wi-Fi" -NetworkCategory Private
     ```
2. **`Host key verification failed`** on the very first connection attempt.
   - Cause: `ssh -o BatchMode=yes` refuses unknown host keys non-interactively.
   - Fix: one-time `-o StrictHostKeyChecking=accept-new` to trust the key, then
     normal `ssh` works from then on (key is cached in `~/.ssh/known_hosts` on
     the Mac).
3. **`troop` being a local Administrator** meant the normal per-user
   `authorized_keys` file is ignored — OpenSSH on Windows only reads
   `administrators_authorized_keys` from `C:\ProgramData\ssh\` for accounts in
   the `Administrators` group, and that file must have restricted ACLs
   (`icacls`) or `sshd` will reject it outright.
4. A previously-active ProtonVPN connection on the Mac was suspected as a
   possible cause of the timeout (default route went through a VPN
   tun-interface), but turned out not to be the issue once tested — routing to
   the `10.0.0.0/24` LAN correctly stayed on the local interface even with the
   VPN up. Turning it off first (as we did) removes it as a variable, but the
   real fix was the network-profile change above.

## Verifying the connection still works

```bash
ssh wardrobe-win "whoami"
ssh wardrobe-win "hostname"
```

Windows' default SSH shell is `cmd.exe`, not PowerShell — semicolon-chained
commands (`a; b`) won't work as one command. Either run one command at a time,
or explicitly invoke PowerShell:

```bash
ssh wardrobe-win "powershell -Command \"Get-Service sshd\""
```
