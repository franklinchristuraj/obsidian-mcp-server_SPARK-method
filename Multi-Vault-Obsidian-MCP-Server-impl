# Multi-Vault Obsidian MCP Server — Implementation Guide

> **Purpose:** Refactor the existing `obsidian-mcp-server` (Ziksaka) from a single-vault REST API architecture to a multi-vault filesystem-first architecture with SQLite FTS5 index.
>
> **Target vaults:** Personal, Work, Passion
>
> **Key constraint:** One MCP server process, three vaults, vault routing handled by Claude via skills.

---

## 1. Architecture Overview

### Current State

```
Claude (mobile/web) → HTTPS → FastAPI (Ziksaka) → Obsidian REST API → Vault files
                                                    ↑
                                              Obsidian GUI on VPS
                                              (Xvfb + Electron)
```

**Problems:** One Obsidian instance = one vault. REST API requires Obsidian running. Heavy resource footprint.

### Target State

```
Claude (mobile/web) → HTTPS → FastAPI (Ziksaka v2) → Filesystem → Vault files
                                     ↓                               ↑
                                Index Service                   obsidian-headless
                                (SQLite FTS5)                   (sync × 3 vaults)
                                     ↓
                              /vaults/personal/
                              /vaults/work/
                              /vaults/passion/
```

**What changes:**
- Obsidian GUI replaced by `obsidian-headless` (lightweight Node sync)
- REST API calls replaced by direct filesystem access (already partially implemented in `obsidian_client.py` fallback)
- New SQLite FTS5 index for rich search and analytical queries
- Every MCP tool gains a `vault` parameter

**What stays:**
- FastAPI app structure, OAuth 2.0, `/mcp` endpoint
- MCP protocol handler (JSON-RPC 2.0, SSE)
- Template engine (updated for vault-aware configs)
- Auth layer (unchanged)
- Nginx Proxy Manager routing (unchanged)

---

## 2. Infrastructure Setup — obsidian-headless

### 2.1 Install obsidian-headless

```bash
# Requires Node.js 22+
npm install -g obsidian-headless
```

### 2.2 Login and configure vaults

```bash
ob login
# Enter Obsidian account credentials + MFA if enabled

# List available remote vaults
ob sync-list-remote

# Setup each vault
mkdir -p /home/franklinchris/vaults/personal
mkdir -p /home/franklinchris/vaults/work
mkdir -p /home/franklinchris/vaults/passion

cd /home/franklinchris/vaults/personal
ob sync-setup --vault "Personal"    # Use exact vault name from sync-list-remote

cd /home/franklinchris/vaults/work
ob sync-setup --vault "Work"

cd /home/franklinchris/vaults/passion
ob sync-setup --vault "Passion"

# Test one-time sync
cd /home/franklinchris/vaults/personal && ob sync
```

### 2.3 Systemd services for continuous sync

Create a service per vault. Template at `/etc/systemd/system/obsidian-sync@.service`:

```ini
[Unit]
Description=Obsidian Headless Sync - %i vault
After=network-online.target
Wants=network-online.target

[Service]
User=franklinchris
Group=franklinchris
WorkingDirectory=/home/franklinchris/vaults/%i
ExecStart=/usr/local/bin/ob sync --continuous
Restart=on-failure
RestartSec=30s
Environment="PATH=/usr/local/bin:/usr/bin:/bin"
# Node.js 22+ must be on PATH

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now obsidian-sync@personal
sudo systemctl enable --now obsidian-sync@work
sudo systemctl enable --now obsidian-sync@passion

# Verify
sudo systemctl status obsidian-sync@personal
sudo systemctl status obsidian-sync@work
sudo systemctl status obsidian-sync@passion
```

### 2.4 Decommission old Obsidian GUI instance

Once sync is confirmed working on all three vaults:

```bash
# Stop the old Obsidian + Xvfb services
sudo systemctl stop obsidian-headless      # or whatever your current service is named
sudo systemctl stop obsidian-headless-xvfb
sudo systemctl disable obsidian-headless
sudo systemctl disable obsidian-headless-xvfb
```

---

## 3. Server Refactor — Step by Step

### 3.1 New file: `src/vault_config.py`

Central vault configuration. This replaces hardcoded vault path references throughout the codebase.

```python
"""
Multi-vault configuration.
Each vault has its own path, folder structure, template config, and daily note format.
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import os


# Standard SPARK folders shared across vaults
STANDARD_SPARK_FOLDERS = {
    "system": "00_system",
    "seeds": "01_seeds",
    "projects": "02_projects",
    "areas": "03_areas",
    "resources": "04_resources",
    "knowledge": "05_knowledge",
    "daily_notes": "06_daily-notes",
    "archive": "99_archive",
}


@dataclass
class VaultConfig:
    """Configuration for a single vault."""
    name: str
    path: Path
    spark_folders: dict = field(default_factory=lambda: STANDARD_SPARK_FOLDERS.copy())
    has_daily_notes: bool = True
    daily_note_template: str = "personal"  # "personal" | "work" | None
    extra_folders: dict = field(default_factory=dict)
    description: str = ""

    @property
    def all_folders(self) -> dict:
        return {**self.spark_folders, **self.extra_folders}

    def resolve_path(self, relative_path: str) -> Path:
        """Resolve a relative path within this vault, with traversal protection."""
        resolved = (self.path / relative_path).resolve()
        if not str(resolved).startswith(str(self.path.resolve())):
            raise ValueError(f"Path traversal detected: {relative_path}")
        return resolved


# -- Vault Registry ----------------------------------------------------------

VAULT_ROOT = Path(os.getenv("VAULT_ROOT", "/home/franklinchris/vaults"))

VAULTS: dict[str, VaultConfig] = {
    "personal": VaultConfig(
        name="personal",
        path=VAULT_ROOT / "personal",
        has_daily_notes=True,
        daily_note_template="personal",
        description="SPARK PKM: seeds, projects, areas, resources, knowledge, daily journal",
    ),
    "work": VaultConfig(
        name="work",
        path=VAULT_ROOT / "work",
        has_daily_notes=True,
        daily_note_template="work",
        extra_folders={
            "meetings": "11_work-meeting-notes",
        },
        description="Work context: meetings, OKRs, stakeholders, sprints, Jira refs",
    ),
    "passion": VaultConfig(
        name="passion",
        path=VAULT_ROOT / "passion",
        has_daily_notes=False,
        daily_note_template=None,
        extra_folders={
            "blueprints": "07_blueprints",
        },
        description="Side projects, infrastructure, YouTube, workshops, content",
    ),
}

VAULT_NAMES = list(VAULTS.keys())


def get_vault(name: str) -> VaultConfig:
    """Get vault config by name. Raises ValueError if not found."""
    if name not in VAULTS:
        raise ValueError(
            f"Unknown vault: '{name}'. Available: {VAULT_NAMES}"
        )
    return VAULTS[name]
```

### 3.2 Refactor: `src/clients/obsidian_client.py`

**Goal:** Remove all REST API code. Promote filesystem mode to the only mode.

#### What to delete
- All `aiohttp` / HTTP client code
- REST API URL construction (`self.api_url`, `self.api_key`)
- Auth header logic and fallback auth formats
- `POST /search/simple/` calls
- `obsidian_command()` method (execute_command)
- REST API health checks

#### What to keep and adapt
- `read_note()` — filesystem read (already exists in fallback)
- `create_note()` — filesystem write with directory creation
- `update_note()` — filesystem write with frontmatter preservation
- `append_note()` — filesystem append
- `delete_note()` — filesystem delete
- `list_notes()` — glob-based listing with metadata
- `get_vault_structure()` — directory tree builder
- Frontmatter parsing logic (`python-frontmatter`)
- Cache layers (adapt to filesystem-only)

#### Key changes

```python
"""
Filesystem-only vault client.
One instance per vault.
"""
from pathlib import Path
from datetime import datetime
import frontmatter
import os
from ..vault_config import VaultConfig


class VaultClient:
    """Filesystem-based client for a single Obsidian vault."""

    def __init__(self, config: VaultConfig):
        self.config = config
        self.vault_path = config.path

    async def read_note(self, path: str) -> dict:
        """Read a note and return parsed content + frontmatter."""
        full_path = self.config.resolve_path(path)
        if not full_path.exists():
            raise FileNotFoundError(f"Note not found: {path}")

        text = full_path.read_text(encoding="utf-8")
        post = frontmatter.loads(text)

        return {
            "path": path,
            "content": post.content,
            "frontmatter": dict(post.metadata),
            "modified": datetime.fromtimestamp(full_path.stat().st_mtime).isoformat(),
        }

    async def create_note(self, path: str, content: str, metadata: dict = None) -> dict:
        """Create a new note with optional YAML frontmatter."""
        full_path = self.config.resolve_path(path)
        if full_path.exists():
            raise FileExistsError(f"Note already exists: {path}")

        full_path.parent.mkdir(parents=True, exist_ok=True)

        if metadata:
            post = frontmatter.Post(content, **metadata)
            full_path.write_text(frontmatter.dumps(post), encoding="utf-8")
        else:
            full_path.write_text(content, encoding="utf-8")

        return {"path": path, "created": True}

    async def update_note(self, path: str, content: str, preserve_format: bool = True) -> dict:
        """Update note content, optionally preserving existing frontmatter."""
        full_path = self.config.resolve_path(path)
        if not full_path.exists():
            raise FileNotFoundError(f"Note not found: {path}")

        if preserve_format:
            existing = frontmatter.loads(full_path.read_text(encoding="utf-8"))
            existing.content = content
            full_path.write_text(frontmatter.dumps(existing), encoding="utf-8")
        else:
            full_path.write_text(content, encoding="utf-8")

        return {"path": path, "updated": True}

    async def append_note(self, path: str, content: str, separator: str = "\n\n---\n\n") -> dict:
        """Append content to an existing note."""
        full_path = self.config.resolve_path(path)
        if not full_path.exists():
            raise FileNotFoundError(f"Note not found: {path}")

        existing = full_path.read_text(encoding="utf-8")
        full_path.write_text(existing + separator + content, encoding="utf-8")
        return {"path": path, "appended": True}

    async def delete_note(self, path: str) -> dict:
        """Delete a note."""
        full_path = self.config.resolve_path(path)
        if not full_path.exists():
            raise FileNotFoundError(f"Note not found: {path}")
        full_path.unlink()
        return {"path": path, "deleted": True}

    async def list_notes(self, folder: str = "") -> list[dict]:
        """List notes in a folder with metadata."""
        search_path = self.config.resolve_path(folder) if folder else self.vault_path
        notes = []

        for md_file in search_path.rglob("*.md"):
            # Skip hidden dirs and .obsidian
            if any(part.startswith(".") for part in md_file.relative_to(self.vault_path).parts):
                continue

            rel_path = str(md_file.relative_to(self.vault_path))
            stat = md_file.stat()

            # Parse frontmatter for metadata (lightweight — just read YAML header)
            try:
                post = frontmatter.loads(md_file.read_text(encoding="utf-8"))
                meta = dict(post.metadata)
            except Exception:
                meta = {}

            notes.append({
                "path": rel_path,
                "title": meta.get("title", md_file.stem),
                "type": meta.get("type", "unknown"),
                "status": meta.get("status", ""),
                "tags": meta.get("tags", []),
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "size": stat.st_size,
            })

        return notes

    async def get_vault_structure(self) -> dict:
        """Get folder tree with note counts."""
        structure = {}
        for item in sorted(self.vault_path.iterdir()):
            if item.name.startswith(".") or item.name == "node_modules":
                continue
            if item.is_dir():
                md_count = len(list(item.rglob("*.md")))
                structure[item.name] = {"type": "folder", "note_count": md_count}
        return structure

    async def check_note_exists(self, path: str) -> dict:
        """Check if a note exists."""
        full_path = self.config.resolve_path(path)
        exists = full_path.exists()
        result = {"path": path, "exists": exists}
        if exists:
            result["modified"] = datetime.fromtimestamp(
                full_path.stat().st_mtime
            ).isoformat()
        return result
```

### 3.3 New file: `src/index_service.py`

SQLite FTS5 index for rich search and analytical queries.

```python
"""
SQLite FTS5 index for multi-vault search and analysis.

Watches vault directories for changes and maintains a searchable index
of all notes with their frontmatter metadata.

The index is the "card catalog" — it enables queries that filesystem
grep cannot: temporal filtering, tag aggregation, status queries,
cross-vault search, and ranked full-text results.
"""
import sqlite3
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional
import frontmatter
import json
import logging

logger = logging.getLogger(__name__)


class IndexService:
    """SQLite FTS5 search index across all vaults."""

    def __init__(self, db_path: str = "/home/franklinchris/vaults/.vault_index.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Create tables if they don't exist."""
        conn = self._connect()
        conn.executescript("""
            -- Main notes table
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vault TEXT NOT NULL,
                path TEXT NOT NULL,
                title TEXT,
                type TEXT,
                status TEXT,
                tags TEXT,           -- JSON array
                folder TEXT,
                created TEXT,
                modified TEXT,
                file_modified REAL,  -- filesystem mtime for change detection
                content TEXT,
                frontmatter TEXT,    -- full YAML as JSON
                UNIQUE(vault, path)
            );

            -- FTS5 virtual table for full-text search
            CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
                vault, path, title, tags, content,
                content='notes',
                content_rowid='id',
                tokenize='porter unicode61'
            );

            -- Triggers to keep FTS in sync
            CREATE TRIGGER IF NOT EXISTS notes_ai AFTER INSERT ON notes BEGIN
                INSERT INTO notes_fts(rowid, vault, path, title, tags, content)
                VALUES (new.id, new.vault, new.path, new.title, new.tags, new.content);
            END;

            CREATE TRIGGER IF NOT EXISTS notes_ad AFTER DELETE ON notes BEGIN
                INSERT INTO notes_fts(notes_fts, rowid, vault, path, title, tags, content)
                VALUES ('delete', old.id, old.vault, old.path, old.title, old.tags, old.content);
            END;

            CREATE TRIGGER IF NOT EXISTS notes_au AFTER UPDATE ON notes BEGIN
                INSERT INTO notes_fts(notes_fts, rowid, vault, path, title, tags, content)
                VALUES ('delete', old.id, old.vault, old.path, old.title, old.tags, old.content);
                INSERT INTO notes_fts(rowid, vault, path, title, tags, content)
                VALUES (new.id, new.vault, new.path, new.title, new.tags, new.content);
            END;

            -- Indexes for common queries
            CREATE INDEX IF NOT EXISTS idx_vault ON notes(vault);
            CREATE INDEX IF NOT EXISTS idx_type ON notes(type);
            CREATE INDEX IF NOT EXISTS idx_status ON notes(status);
            CREATE INDEX IF NOT EXISTS idx_folder ON notes(folder);
            CREATE INDEX IF NOT EXISTS idx_modified ON notes(modified);
        """)
        conn.close()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def rebuild_vault(self, vault_name: str, vault_path: Path):
        """Full rebuild of index for one vault. Run on startup or manually."""
        logger.info(f"Rebuilding index for vault: {vault_name}")
        conn = self._connect()

        # Clear existing entries for this vault
        conn.execute("DELETE FROM notes WHERE vault = ?", (vault_name,))

        count = 0
        for md_file in vault_path.rglob("*.md"):
            # Skip hidden dirs
            if any(part.startswith(".") for part in md_file.relative_to(vault_path).parts):
                continue

            try:
                self._index_file(conn, vault_name, vault_path, md_file)
                count += 1
            except Exception as e:
                logger.warning(f"Failed to index {md_file}: {e}")

        conn.commit()
        conn.close()
        logger.info(f"Indexed {count} notes in {vault_name}")

    def incremental_update(self, vault_name: str, vault_path: Path):
        """Update only changed files (compare filesystem mtime vs stored mtime)."""
        conn = self._connect()

        # Get stored mtimes
        stored = {}
        for row in conn.execute(
            "SELECT path, file_modified FROM notes WHERE vault = ?", (vault_name,)
        ):
            stored[row["path"]] = row["file_modified"]

        # Scan filesystem
        current_files = set()
        updated = 0
        for md_file in vault_path.rglob("*.md"):
            if any(part.startswith(".") for part in md_file.relative_to(vault_path).parts):
                continue

            rel_path = str(md_file.relative_to(vault_path))
            current_files.add(rel_path)
            file_mtime = md_file.stat().st_mtime

            if rel_path not in stored or stored[rel_path] != file_mtime:
                try:
                    self._index_file(conn, vault_name, vault_path, md_file)
                    updated += 1
                except Exception as e:
                    logger.warning(f"Failed to index {md_file}: {e}")

        # Remove deleted files
        deleted_paths = set(stored.keys()) - current_files
        for path in deleted_paths:
            conn.execute(
                "DELETE FROM notes WHERE vault = ? AND path = ?",
                (vault_name, path),
            )
            updated += 1

        if updated:
            conn.commit()
            logger.info(f"Incremental update for {vault_name}: {updated} changes")

        conn.close()

    def _index_file(self, conn: sqlite3.Connection, vault_name: str, vault_path: Path, md_file: Path):
        """Index or re-index a single file."""
        rel_path = str(md_file.relative_to(vault_path))
        text = md_file.read_text(encoding="utf-8")
        post = frontmatter.loads(text)
        meta = dict(post.metadata)

        # Extract folder from path
        parts = Path(rel_path).parts
        folder = parts[0] if len(parts) > 1 else ""

        conn.execute("""
            INSERT INTO notes (vault, path, title, type, status, tags, folder,
                              created, modified, file_modified, content, frontmatter)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(vault, path) DO UPDATE SET
                title=excluded.title, type=excluded.type, status=excluded.status,
                tags=excluded.tags, folder=excluded.folder, created=excluded.created,
                modified=excluded.modified, file_modified=excluded.file_modified,
                content=excluded.content, frontmatter=excluded.frontmatter
        """, (
            vault_name,
            rel_path,
            meta.get("title", md_file.stem),
            meta.get("type", ""),
            meta.get("status", ""),
            json.dumps(meta.get("tags", [])),
            folder,
            meta.get("created", ""),
            datetime.fromtimestamp(md_file.stat().st_mtime).isoformat(),
            md_file.stat().st_mtime,
            post.content,
            json.dumps(meta),
        ))

    # -- Query Methods --------------------------------------------------------

    def search(
        self,
        query: str,
        vault: Optional[str] = None,
        limit: int = 20,
    ) -> list[dict]:
        """Full-text search with FTS5 ranking. Cross-vault by default."""
        conn = self._connect()

        if vault:
            rows = conn.execute("""
                SELECT n.vault, n.path, n.title, n.type, n.status, n.tags,
                       n.folder, n.modified, snippet(notes_fts, 4, '>>>', '<<<', '...', 40) as snippet,
                       rank
                FROM notes_fts f
                JOIN notes n ON n.id = f.rowid
                WHERE notes_fts MATCH ? AND n.vault = ?
                ORDER BY rank
                LIMIT ?
            """, (query, vault, limit)).fetchall()
        else:
            rows = conn.execute("""
                SELECT n.vault, n.path, n.title, n.type, n.status, n.tags,
                       n.folder, n.modified, snippet(notes_fts, 4, '>>>', '<<<', '...', 40) as snippet,
                       rank
                FROM notes_fts f
                JOIN notes n ON n.id = f.rowid
                WHERE notes_fts MATCH ?
                ORDER BY rank
                LIMIT ?
            """, (query, limit)).fetchall()

        conn.close()
        return [dict(row) for row in rows]

    def query_by_metadata(
        self,
        vault: Optional[str] = None,
        note_type: Optional[str] = None,
        status: Optional[str] = None,
        folder: Optional[str] = None,
        tag: Optional[str] = None,
        modified_after: Optional[str] = None,
        modified_before: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        """Structured query by frontmatter fields. The analytical powerhouse."""
        conn = self._connect()

        conditions = []
        params = []

        if vault:
            conditions.append("vault = ?")
            params.append(vault)
        if note_type:
            conditions.append("type = ?")
            params.append(note_type)
        if status:
            conditions.append("status = ?")
            params.append(status)
        if folder:
            conditions.append("folder LIKE ?")
            params.append(f"{folder}%")
        if tag:
            conditions.append("tags LIKE ?")
            params.append(f'%"{tag}"%')
        if modified_after:
            conditions.append("modified >= ?")
            params.append(modified_after)
        if modified_before:
            conditions.append("modified <= ?")
            params.append(modified_before)

        where = " AND ".join(conditions) if conditions else "1=1"
        params.append(limit)

        rows = conn.execute(f"""
            SELECT vault, path, title, type, status, tags, folder, modified
            FROM notes
            WHERE {where}
            ORDER BY modified DESC
            LIMIT ?
        """, params).fetchall()

        conn.close()
        return [dict(row) for row in rows]

    def get_stats(self, vault: Optional[str] = None) -> dict:
        """Vault analytics — note counts by type, status, folder, recent activity."""
        conn = self._connect()
        vault_filter = "WHERE vault = ?" if vault else ""
        params = (vault,) if vault else ()

        stats = {
            "total_notes": conn.execute(
                f"SELECT COUNT(*) FROM notes {vault_filter}", params
            ).fetchone()[0],
            "by_type": {
                row[0] or "untyped": row[1]
                for row in conn.execute(
                    f"SELECT type, COUNT(*) FROM notes {vault_filter} GROUP BY type",
                    params,
                ).fetchall()
            },
            "by_status": {
                row[0] or "no status": row[1]
                for row in conn.execute(
                    f"SELECT status, COUNT(*) FROM notes {vault_filter} GROUP BY status",
                    params,
                ).fetchall()
            },
            "by_folder": {
                row[0] or "root": row[1]
                for row in conn.execute(
                    f"SELECT folder, COUNT(*) FROM notes {vault_filter} GROUP BY folder",
                    params,
                ).fetchall()
            },
            "recently_modified": [
                dict(row)
                for row in conn.execute(
                    f"SELECT vault, path, title, modified FROM notes {vault_filter} ORDER BY modified DESC LIMIT 10",
                    params,
                ).fetchall()
            ],
        }
        conn.close()
        return stats
```

### 3.4 Background index updater

Add to `main.py` — a periodic task that runs incremental updates.

```python
from src.index_service import IndexService
from src.vault_config import VAULTS

index = IndexService()


async def index_update_loop():
    """Periodic incremental index update. Runs every 60 seconds."""
    # Full rebuild on startup
    for name, config in VAULTS.items():
        index.rebuild_vault(name, config.path)

    while True:
        await asyncio.sleep(60)
        for name, config in VAULTS.items():
            try:
                index.incremental_update(name, config.path)
            except Exception as e:
                logger.error(f"Index update failed for {name}: {e}")


# Add to FastAPI lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(index_update_loop())
    yield
    task.cancel()

app = FastAPI(lifespan=lifespan)
```

### 3.5 Refactor: `src/tools/obsidian_tools.py`

Every tool gains a `vault` parameter (enum: `personal`, `work`, `passion`). Remove `obs_execute_command`.

#### Vault client router

```python
from src.vault_config import VAULTS, get_vault, VAULT_NAMES
from src.clients.obsidian_client import VaultClient
from src.index_service import IndexService

# Initialize one client per vault
vault_clients: dict[str, VaultClient] = {
    name: VaultClient(config) for name, config in VAULTS.items()
}

# Shared index service
index = IndexService()


def get_client(vault: str) -> VaultClient:
    """Get the vault client for a given vault name."""
    if vault not in vault_clients:
        raise ValueError(f"Unknown vault: '{vault}'. Available: {VAULT_NAMES}")
    return vault_clients[vault]
```

#### Updated tool definitions

Here's the complete tool list with their schemas. Each tool adds `vault` as a required string enum parameter.

```python
TOOLS = [
    {
        "name": "obs_read_note",
        "description": "Read the complete content of a note from a vault.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "vault": {
                    "type": "string",
                    "enum": VAULT_NAMES,
                    "description": "Which vault to read from: personal (SPARK PKM, daily journal), work (meetings, OKRs, stakeholders), passion (side projects, infra, content)"
                },
                "path": {
                    "type": "string",
                    "description": "Path to note relative to vault root (e.g., '01_seeds/skill-paradox.md')"
                }
            },
            "required": ["vault", "path"]
        }
    },
    {
        "name": "obs_create_note",
        "description": "Create a new note with YAML frontmatter. Uses vault-aware SPARK templates.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "vault": {
                    "type": "string",
                    "enum": VAULT_NAMES,
                    "description": "Target vault"
                },
                "path": {
                    "type": "string",
                    "description": "Path for new note (e.g., '01_seeds/new-idea.md')"
                },
                "content": {
                    "type": "string",
                    "description": "Note body content (markdown)"
                },
                "frontmatter": {
                    "type": "object",
                    "description": "YAML frontmatter fields. Merged with template defaults."
                },
                "template": {
                    "type": "string",
                    "enum": ["seed", "project", "area", "resource", "knowledge", "daily", "meeting", "blueprint-project", "blueprint-tool"],
                    "description": "Optional template to apply. Auto-detected from path if not specified."
                }
            },
            "required": ["vault", "path", "content"]
        }
    },
    {
        "name": "obs_update_note",
        "description": "Update the content of an existing note, preserving YAML frontmatter.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "vault": {"type": "string", "enum": VAULT_NAMES},
                "path": {"type": "string"},
                "content": {"type": "string", "description": "New content (replaces body, frontmatter preserved)"},
                "preserve_format": {"type": "boolean", "default": True}
            },
            "required": ["vault", "path", "content"]
        }
    },
    {
        "name": "obs_append_note",
        "description": "Append content to an existing note (e.g., adding to daily notes, meeting notes).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "vault": {"type": "string", "enum": VAULT_NAMES},
                "path": {"type": "string"},
                "content": {"type": "string", "description": "Content to append"},
                "separator": {"type": "string", "default": "\n\n", "description": "Separator before appended content"}
            },
            "required": ["vault", "path", "content"]
        }
    },
    {
        "name": "obs_delete_note",
        "description": "Delete a note from a vault.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "vault": {"type": "string", "enum": VAULT_NAMES},
                "path": {"type": "string"}
            },
            "required": ["vault", "path"]
        }
    },
    {
        "name": "obs_list_notes",
        "description": "List notes in a vault folder with metadata (type, status, tags, modified date).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "vault": {"type": "string", "enum": VAULT_NAMES},
                "folder": {"type": "string", "default": "", "description": "Folder to list (e.g., '01_seeds'). Empty for all."}
            },
            "required": ["vault"]
        }
    },
    {
        "name": "obs_search_notes",
        "description": "Full-text search across one or all vaults. Returns ranked results with context snippets.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query (supports FTS5 syntax: AND, OR, NOT, phrase matching)"},
                "vault": {
                    "type": "string",
                    "enum": VAULT_NAMES,
                    "description": "Scope to one vault. Omit for cross-vault search."
                },
                "limit": {"type": "integer", "default": 20, "maximum": 50}
            },
            "required": ["query"]
        }
    },
    {
        "name": "obs_query_notes",
        "description": "Structured query by metadata: type, status, tags, folder, date range. The analytical tool for questions like 'what seeds are still raw?' or 'meetings from last 2 weeks'.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "vault": {"type": "string", "enum": VAULT_NAMES, "description": "Omit for cross-vault."},
                "type": {"type": "string", "description": "Note type: seed, project, area, resource, knowledge, daily-note, meeting-note, blueprint-project, blueprint-tool"},
                "status": {"type": "string", "description": "Status field value (e.g., raw, active, completed)"},
                "folder": {"type": "string", "description": "Folder prefix (e.g., '01_seeds', '11_work-meeting-notes')"},
                "tag": {"type": "string", "description": "Tag to filter by"},
                "modified_after": {"type": "string", "description": "ISO date — notes modified after this date"},
                "modified_before": {"type": "string", "description": "ISO date — notes modified before this date"},
                "limit": {"type": "integer", "default": 50}
            }
        }
    },
    {
        "name": "obs_get_vault_structure",
        "description": "Get folder tree with note counts for a vault.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "vault": {"type": "string", "enum": VAULT_NAMES}
            },
            "required": ["vault"]
        }
    },
    {
        "name": "obs_check_note_exists",
        "description": "Check if a note exists in a vault.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "vault": {"type": "string", "enum": VAULT_NAMES},
                "path": {"type": "string"}
            },
            "required": ["vault", "path"]
        }
    },
    {
        "name": "obs_list_daily_notes",
        "description": "List daily notes between two dates.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "vault": {
                    "type": "string",
                    "enum": ["personal", "work"],
                    "description": "Only personal and work vaults have daily notes."
                },
                "start_date": {"type": "string", "description": "Start date (YYYY-MM-DD)"},
                "end_date": {"type": "string", "description": "End date (YYYY-MM-DD)"}
            },
            "required": ["vault", "start_date", "end_date"]
        }
    },
    {
        "name": "obs_vault_stats",
        "description": "Get analytics for a vault: note counts by type/status/folder, recent activity. Useful for vault health checks and reviews.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "vault": {"type": "string", "enum": VAULT_NAMES, "description": "Omit for cross-vault stats."}
            }
        }
    },
]
```

#### Tool executor routing

```python
async def execute_tool(name: str, arguments: dict) -> dict:
    """Route tool calls to the appropriate vault client and method."""

    vault_name = arguments.get("vault")

    # Tools that don't require a vault (cross-vault)
    if name == "obs_search_notes":
        return index.search(
            query=arguments["query"],
            vault=vault_name,  # None = cross-vault
            limit=arguments.get("limit", 20),
        )

    if name == "obs_query_notes":
        return index.query_by_metadata(
            vault=vault_name,
            note_type=arguments.get("type"),
            status=arguments.get("status"),
            folder=arguments.get("folder"),
            tag=arguments.get("tag"),
            modified_after=arguments.get("modified_after"),
            modified_before=arguments.get("modified_before"),
            limit=arguments.get("limit", 50),
        )

    if name == "obs_vault_stats":
        return index.get_stats(vault=vault_name)

    # All other tools require a vault
    if not vault_name:
        return {"error": f"Tool '{name}' requires a 'vault' parameter."}

    client = get_client(vault_name)

    handlers = {
        "obs_read_note": lambda: client.read_note(arguments["path"]),
        "obs_create_note": lambda: client.create_note(
            path=arguments["path"],
            content=arguments["content"],
            metadata=arguments.get("frontmatter"),
        ),
        "obs_update_note": lambda: client.update_note(
            path=arguments["path"],
            content=arguments["content"],
            preserve_format=arguments.get("preserve_format", True),
        ),
        "obs_append_note": lambda: client.append_note(
            path=arguments["path"],
            content=arguments["content"],
            separator=arguments.get("separator", "\n\n"),
        ),
        "obs_delete_note": lambda: client.delete_note(arguments["path"]),
        "obs_list_notes": lambda: client.list_notes(arguments.get("folder", "")),
        "obs_get_vault_structure": lambda: client.get_vault_structure(),
        "obs_check_note_exists": lambda: client.check_note_exists(arguments["path"]),
        "obs_list_daily_notes": lambda: client.list_daily_notes(
            arguments["start_date"], arguments["end_date"]
        ),
    }

    handler = handlers.get(name)
    if not handler:
        return {"error": f"Unknown tool: {name}"}

    return await handler()
```

### 3.6 Update: `src/utils/template_utils.py`

The template detector becomes vault-aware. Pass the vault config to determine folder mappings and daily note templates.

**Key changes:**
- `TemplateDetector.__init__()` accepts a `VaultConfig`
- Folder normalization uses `config.all_folders` instead of hardcoded mapping
- Daily note template selection based on `config.daily_note_template`
- Work daily notes get standup/log structure; personal daily notes keep the reflection/journal format

```python
# Work daily note template (different from personal)
WORK_DAILY_TEMPLATE = {
    "frontmatter": {
        "type": "daily-note",
        "creation-date": "",  # filled at creation time
        "tags": ["journal/daily", "work"],
    },
    "body": """# Work Log — {date}

### Priorities Today
- 

### Completed
- 

### Blockers / Escalations
- 

### Key Decisions
- 

### Tomorrow
- 
"""
}
```

### 3.7 Update: `src/mcp_server.py`

Minimal changes needed:
- Remove `obs_execute_command` from tool routing
- Add `obs_query_notes` and `obs_vault_stats` to tool routing
- Update resource URI scheme: `obsidian://{vault}/notes/{path}`

### 3.8 Update: `src/resources/obsidian_resources.py`

Resources become vault-scoped:
- `obsidian://personal/notes/` → personal vault root
- `obsidian://work/notes/11_work-meeting-notes/` → work meetings folder
- `obsidian://passion/notes/07_blueprints/tool-n8n.md` → specific blueprint

---

## 4. Dependencies Update

### 4.1 `requirements.txt` changes

```diff
  fastapi
  uvicorn
  pydantic
+ python-frontmatter    # YAML frontmatter parsing (if not already present)
- aiohttp               # REMOVE — no more REST API calls
```

`sqlite3` is part of Python stdlib — no additional dependency needed.

### 4.2 System dependency: ripgrep (optional, fallback for raw text search)

```bash
sudo apt install ripgrep
```

Not strictly needed with FTS5, but useful as a fast fallback for exact-match searches or debugging.

---

## 5. Environment Variables

Update your `.env` or `config.yaml`:

```bash
# -- Remove these --
# OBSIDIAN_API_KEY=...
# OBSIDIAN_API_URL=...
# OBSIDIAN_HOST=...
# OBSIDIAN_PORT=...

# -- Add these --
VAULT_ROOT=/home/franklinchris/vaults
INDEX_DB_PATH=/home/franklinchris/vaults/.vault_index.db

# -- Keep these --
MCP_API_KEY=...          # if using static API key auth
# All OAuth config stays unchanged
```

---

## 6. Migration Checklist

Execute in this order. Each step is independently testable.

### Phase 1: Infrastructure (no code changes)
- [ ] Install `obsidian-headless` on VPS
- [ ] Login and configure 3 vaults
- [ ] Run `ob sync` for each vault — verify files appear
- [ ] Create systemd services for continuous sync
- [ ] Verify sync works end-to-end (edit on phone → appears on VPS within ~30s)
- [ ] Keep old Obsidian instance running in parallel until Phase 2 is verified

### Phase 2: Server refactor
- [ ] Create `src/vault_config.py`
- [ ] Create `src/index_service.py` — test independently with `python -c "from src.index_service import IndexService; idx = IndexService(); idx.rebuild_vault('personal', Path('/home/franklinchris/vaults/personal'))"`
- [ ] Refactor `src/clients/obsidian_client.py` → `VaultClient` (filesystem only)
- [ ] Update `src/tools/obsidian_tools.py` — new tool schemas + executor
- [ ] Update `src/mcp_server.py` — tool routing changes
- [ ] Update `src/resources/obsidian_resources.py` — vault-scoped URIs
- [ ] Update `src/utils/template_utils.py` — vault-aware templates
- [ ] Add index update loop to `main.py`
- [ ] Update environment variables

### Phase 3: Testing
- [ ] Start server locally, test each tool with curl/MCP inspector
- [ ] Test cross-vault search: `obs_search_notes(query="Sara")` → results from both personal + work
- [ ] Test analytical queries: `obs_query_notes(vault="personal", type="seed", status="raw")`
- [ ] Test daily note creation in both personal and work vaults
- [ ] Test from Claude mobile app — create a seed via voice
- [ ] Test from Claude mobile app — search for a meeting note
- [ ] Test from Claude mobile app — append to today's daily note

### Phase 4: Cleanup
- [ ] Stop and disable old Obsidian GUI services
- [ ] Remove old REST API environment variables
- [ ] Update `franklin-obsidian-vault` Claude skill with vault routing rules (see Section 7)
- [ ] Update the Obsidian MCP blueprint in `07_blueprints/tool-obsidian-mcp.md`

---

## 7. Claude Skill Update

Update the `franklin-obsidian-vault` skill description and add vault routing rules. The skill is what tells Claude which vault to target — the server just executes.

### Updated skill description

```
Franklin's Obsidian system spans three vaults accessible via MCP:
- personal: SPARK PKM (seeds, projects, areas, resources, knowledge), daily journal, personal reflections
- work: Meeting notes, OKRs, stakeholders, sprints, Jira references, work daily log
- passion: Side projects, VPS infrastructure, blueprints, YouTube/content, workshops
```

### Vault routing rules (add to skill)

```markdown
## Vault Routing

Every MCP tool call requires a `vault` parameter. Use these rules:

| Signal | Vault |
|--------|-------|
| Seeds, SPARK system, personal reflections, gratitude, family | `personal` |
| Daily journal / morning reflection | `personal` |
| Weekly review | `personal` |
| Knowledge, resources, areas (personal growth) | `personal` |
| Meeting notes, standups, sprint planning | `work` |
| Stakeholders, OKRs, Jira, roadmap | `work` |
| Work daily log (priorities, blockers, decisions) | `work` |
| Sara, Miriwa, Samurai, Make, Celonis references | `work` |
| YouTube, Frank About AI, workshops | `passion` |
| VPS, Docker, infrastructure, blueprints, tool cards | `passion` |
| Side projects (Voice PKM, Intelligence Radar, SPARK Coach) | `passion` |
| Content pipeline, LinkedIn posts | `passion` |

**Cross-vault search:** Use `obs_search_notes` without vault param to search all vaults.
**Ambiguous?** Ask Franklin which vault.
**Explicit override:** If Franklin says "save to work vault", always honor it.
```

---

## 8. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| `obsidian-headless` sync lag (>30s) | Medium | Medium | Test empirically. Fallback: cron `ob sync` every 60s instead of `--continuous` |
| `obsidian-headless` crashes / memory leaks | Medium | Medium | Systemd `Restart=on-failure`. Monitor with `journalctl -f -u obsidian-sync@*` |
| FTS5 index goes stale | Low | Low | 60-second incremental update loop. Manual rebuild endpoint for emergencies |
| Sync conflict (phone edit + Claude write) | Low | Medium | `obsidian-headless` uses last-write-wins. Mitigate by appending (not overwriting) for daily notes |
| Path traversal via MCP tool call | Low | High | `VaultConfig.resolve_path()` validates all paths stay within vault boundary |
| Frontmatter parsing failure on edge cases | Low | Low | `try/except` with fallback to empty metadata. Log warnings for manual review |

---

## 9. File Changes Summary

| File | Action | What changes |
|------|--------|-------------|
| `src/vault_config.py` | **NEW** | Vault registry, config dataclass, path resolver |
| `src/index_service.py` | **NEW** | SQLite FTS5 index, search, metadata queries, stats |
| `src/clients/obsidian_client.py` | **REWRITE** | Remove REST API, filesystem-only `VaultClient` |
| `src/tools/obsidian_tools.py` | **MAJOR** | All tools gain `vault` param, new `obs_query_notes` + `obs_vault_stats`, drop `obs_execute_command` |
| `src/mcp_server.py` | **MINOR** | Update tool routing, remove execute_command |
| `src/resources/obsidian_resources.py` | **MODERATE** | Vault-scoped URIs: `obsidian://{vault}/notes/{path}` |
| `src/utils/template_utils.py` | **MODERATE** | Vault-aware template detection, work daily note template |
| `main.py` | **MODERATE** | Add index update loop to lifespan, remove REST API health checks |
| `requirements.txt` | **MINOR** | Remove `aiohttp`, ensure `python-frontmatter` |
| `.env` / `config.yaml` | **MINOR** | Remove REST API vars, add `VAULT_ROOT` |