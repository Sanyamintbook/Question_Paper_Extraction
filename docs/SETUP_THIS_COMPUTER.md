# Setup on this computer

Configured on September 22, 2026.

## Start

Double-click `start_surya_local.cmd` in the project folder. Keep its terminal
open and open `http://127.0.0.1:8502/` in your browser. The local launcher disables
the access token using `--no-token`; remove that flag to restore token protection.
The local interface uses port 8502. Stop it with Ctrl+C before starting another
instance on the same port. For access from other devices on the same Wi-Fi, use
`start_surya_wifi.cmd` or `scripts/start_surya_lan_ui.ps1`. Both listen on all
network interfaces without a token, as requested. Share the printed network URL.

## Python and GPU

The copied Python environment pointed to the previous user's missing Python
installation. It has been repaired using Python 3.12.14 at:

`C:\Users\KITS\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`

The existing project packages were retained. `python -m pip check` reports no
broken requirements. This environment depends on that base Python installation;
if it is removed, repair the environment with another Python 3.12 installation.
The original environment configuration is saved as
`.venv/pyvenv.cfg.before-system-setup.bak`.

The existing CUDA backend detects the Quadro P3000 (6 GB). The runner defaults
to 12 GPU layers. PyTorch is a CPU build; GPU acceleration here is provided by
the separate CUDA-enabled llama.cpp executable.

Surya also writes backend process information and logs under the current user's
`.cache/datalab/surya` directory. Run normally on Windows, with permission to
write there. Model weights remain in the project's `.cache/huggingface` folder.

## Verification

All 14 existing unit tests pass. The recovery test fixture was updated to bypass
blank-page detection so that it actually exercises subdivision recovery.

A fresh one-page sample completed using CUDA with 12 GPU layers in 101.5 seconds
of OCR time. It returned 25 blocks and generated Word and Excel files. Both files
were downloaded through the browser server API and opened successfully with
their document libraries. The sample has one structural review item; this is a
setup check, not a certification of extraction accuracy.

Setup sample and local server logs are under `runtime/setup-check`. Historical
inputs and outputs are retained. Browser uploads force a fresh OCR pass as
configured by the previous demo changes. The page timeout remains 150 seconds.
