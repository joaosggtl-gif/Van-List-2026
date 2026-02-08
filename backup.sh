#!/bin/bash
# Backup script for Van List 2026
# Creates a timestamped copy of the SQLite database
#
# Usage: ./backup.sh
# Restore: cp backups/<backup_file> data/vanlist.db

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DB_FILE="$SCRIPT_DIR/data/vanlist.db"
BACKUP_DIR="$SCRIPT_DIR/backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="$BACKUP_DIR/vanlist_backup_${TIMESTAMP}.db"

mkdir -p "$BACKUP_DIR"

if [ ! -f "$DB_FILE" ]; then
    echo "ERROR: Database file not found at $DB_FILE"
    exit 1
fi

# Use SQLite backup command for safe hot backup (works even if app is running)
sqlite3 "$DB_FILE" ".backup '$BACKUP_FILE'"

# Verify backup
if [ -f "$BACKUP_FILE" ]; then
    SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    echo "Backup created successfully: $BACKUP_FILE ($SIZE)"

    # Keep only last 30 backups
    cd "$BACKUP_DIR"
    ls -1t vanlist_backup_*.db 2>/dev/null | tail -n +31 | xargs -r rm --
    echo "Old backups cleaned (keeping last 30)"
else
    echo "ERROR: Backup failed!"
    exit 1
fi
