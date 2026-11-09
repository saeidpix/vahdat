# Vahdat Windows 1.5.7 — GitHub-built installer

This branch contains the exact ZIP of the 1.5.7 source package supplied for the five-branch prototype, alongside a **Windows GitHub Actions build pipeline**. It does not contain production branch keys, passwords or live database data.

Workflow: `.github/workflows/build-windows-1.5.7.yml`

Source: `build-source/Vahdat-v1.5.7.zip`

CI unpacks the archive, corrects stale `1.5.6` version labels, removes the mandatory pip-upgrade step from the extracted Windows build helper, runs Python and JavaScript checks, exercises a browser, packages a portable server EXE, tests its HTTP assets and builds an Inno Setup Windows installer.

When CI succeeds, download artifact **Vahdat-Setup-Windows-v1.5.7-beta** from its GitHub Actions run. Each artifact is a ZIP that contains the executable setup, not a ready link to a raw EXE.

Do **not** install on an operational Windows Server 2019 that runs ticket-selling software until backup, virus scan, functional testing and load checks are complete. Do not connect to live company systems with demo keys.
