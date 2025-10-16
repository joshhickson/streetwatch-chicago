#!/usr/bin/env python3
"""
CSV backup and versioning system for StreetWatch Chicago.
Creates timestamped backups before any write operations.
"""
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from src.logger import log

BACKUP_DIR = Path("data/backups")
RETENTION_DAYS = 30
MAX_BACKUPS = 100

def create_backup(source_file: str) -> str | None:
    """Creates a timestamped backup of the CSV file."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    
    source_path = Path(source_file)
    if not source_path.exists():
        log.warning(f"Source file does not exist: {source_file}")
        return None
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"map_data_backup_{timestamp}.csv"
    backup_path = BACKUP_DIR / backup_name
    
    try:
        shutil.copy2(source_path, backup_path)
        log.info(f"Created backup: {backup_path}")
        cleanup_old_backups()
        return str(backup_path)
    except Exception as e:
        log.error(f"Failed to create backup: {e}", exc_info=True)
        return None

def cleanup_old_backups():
    """Removes backups older than RETENTION_DAYS."""
    try:
        backups = sorted(BACKUP_DIR.glob("map_data_backup_*.csv"))
        
        if len(backups) > MAX_BACKUPS:
            for old_backup in backups[:-MAX_BACKUPS]:
                old_backup.unlink()
                log.info(f"Deleted old backup (max limit): {old_backup}")
        
        cutoff_date = datetime.now() - timedelta(days=RETENTION_DAYS)
        for backup in backups:
            try:
                timestamp_str = backup.stem.replace("map_data_backup_", "")
                backup_date = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
                if backup_date < cutoff_date:
                    backup.unlink()
                    log.info(f"Deleted old backup (retention): {backup}")
            except ValueError:
                continue
    except Exception as e:
        log.error(f"Error during backup cleanup: {e}", exc_info=True)

def rollback_to_backup(backup_file: str, target_file: str):
    """Restores CSV from a specific backup."""
    backup_path = Path(backup_file)
    if not backup_path.exists():
        raise FileNotFoundError(f"Backup not found: {backup_file}")
    
    try:
        shutil.copy2(backup_path, target_file)
        log.info(f"Restored from backup: {backup_file} -> {target_file}")
    except Exception as e:
        log.error(f"Failed to restore backup: {e}", exc_info=True)
        raise

def list_available_backups() -> list[str]:
    """Returns a list of all available backup files."""
    if not BACKUP_DIR.exists():
        return []
    return [str(backup) for backup in sorted(BACKUP_DIR.glob("map_data_backup_*.csv"), reverse=True)]
