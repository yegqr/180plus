# 📜 Helper Scripts (`scripts/`)

Automation utilities for deployment, maintenance, and content generation.

## 🚀 Deployment
### `remote_deploy.sh`
**Usage:** `./scripts/remote_deploy.sh`
The primary deployment tool.
1.  Syncs your local project folder to the remote server via `rsync`.
2.  SSH-es into the server.
3.  Rebuilds Docker containers (`docker compose up --build`).
4.  Runs DB migrations.

### `deploy.sh`
Internal script used *on the server* by `remote_deploy.sh`. Installs Docker if missing and setups the environment.

## 🧠 Content Generation
### `generate_all_explanations.py`
**Usage (on server):**
```bash
docker compose exec bot python scripts/generate_all_explanations.py
```
**Purpose:**
-   Scans the database for questions without explanations.
-   Sends question images to **Google Gemini 1.5 Pro**.
-   Generates and saves the explanation to the database.
-   Run this in `nohup` or `screen` for long operations.
