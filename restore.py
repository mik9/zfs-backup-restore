#!/usr/bin/env -S python3 -u

import argparse
import subprocess
import sys
from datetime import datetime
import json

from dataclasses import dataclass, fields
from enum import Enum
from config import get_config, BackupConfig, TIMESTAMP_FORMAT
from compression import get_compressor_by_filename


class BackupType(Enum):
    FULL = 'full'
    INCREMENTAL = 'incremental'


@dataclass
class RcloneFile:
    """Represents a file listed by 'rclone lsjson'."""
    Path: str
    Name: str
    Size: int
    MimeType: str
    ModTime: str
    IsDir: bool


@dataclass
class BackupInfo:
    """Represents a parsed backup file with its metadata."""
    path: str
    snapshot_name: str
    timestamp: datetime
    type: BackupType
    size: int

def human_readable_size(size, decimal_places=2):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f"{size:.{decimal_places}f}{unit}"
        size /= 1024.0


def list_backups(config: BackupConfig) -> list[RcloneFile]:
    """List all backup files in the rclone remote."""
    remote_path = f'{config.rclone_remote}:{config.bucket_name}'
    cmd = f'rclone --config {config.rclone_config_path} lsjson --recursive  --include "{config.zfs_dataset}*" --files-only {remote_path}'
    
    try:
        result = subprocess.run(cmd, shell=True, check=True, stdout=subprocess.PIPE, text=True)
        files_json = json.loads(result.stdout)
        
        rclone_file_fields = {f.name for f in fields(RcloneFile)}
        
        files = []
        for f_json in files_json:
            filtered_data = {k: v for k, v in f_json.items() if k in rclone_file_fields}
            files.append(RcloneFile(**filtered_data))
        return files
    except subprocess.CalledProcessError as e:
        print(f"Error listing backups: {e}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error parsing rclone output: {e}")
        sys.exit(1)


def find_backup_chain(backups: list[RcloneFile], config: BackupConfig) -> tuple[BackupInfo | None, list[BackupInfo]]:
    """Find the latest full backup and subsequent incremental backups."""
    dataset_backups: list[BackupInfo] = []
    for b in backups:
        # Expected format: pool/dataset@prefix-YYYY-MM-DD_HH-MM-SS-full.ext
        # or pool/dataset@prefix-YYYY-MM-DD_HH-MM-SS-incremental.ext
        path: str = b.Path
        if not path.startswith(f'{config.zfs_dataset}@{config.snapshot_prefix}'):
            continue

        parts = path.rsplit('-', 1)
        if len(parts) != 2:
            continue
            
        backup_type_str, _ = (parts[1].split('.', 1) + [''])[0:2]

        try:
            backup_type = BackupType(backup_type_str)
        except ValueError:
            print(f"Could not parse backup type from: {path}")
            continue
            
        # Extract timestamp from snapshot name
        try:
            snapshot_name = parts[0]
            timestamp_str = snapshot_name.split(config.snapshot_prefix)[1]
            timestamp = datetime.strptime(timestamp_str, TIMESTAMP_FORMAT)
            dataset_backups.append(BackupInfo(
                path=path,
                snapshot_name=snapshot_name,
                timestamp=timestamp,
                type=backup_type,
                size=b.Size
            ))
        except (ValueError, IndexError):
            print(f"Could not parse timestamp from: {path}")
            continue

    if not dataset_backups:
        return None, []

    # Sort by timestamp
    dataset_backups.sort(key=lambda x: x.timestamp)
    
    # Find the last full backup
    last_full_backup = None
    for backup in reversed(dataset_backups):
        if backup.type == BackupType.FULL:
            last_full_backup = backup
            break
            
    if not last_full_backup:
        return None, []
        
    # Find all incremental backups after the last full backup
    incremental_backups = []
    for backup in dataset_backups:
        if backup.type == BackupType.INCREMENTAL and backup.timestamp > last_full_backup.timestamp:
            incremental_backups.append(backup)
            
    return last_full_backup, incremental_backups


def restore_backup(config: BackupConfig, backup_path: str, target_dataset: str):
    """Restore a single backup file to the target dataset."""
    remote_path = f'{config.rclone_remote}:{config.bucket_name}/{backup_path}'

    compressor = get_compressor_by_filename(backup_path)
    decompress_cmd = compressor.decompress_cmd if compressor else None

    rclone_cmd = f'rclone --config {config.rclone_config_path} cat {remote_path}'
    zfs_cmd = f'zfs receive -F {target_dataset}'
    
    if decompress_cmd:
        full_cmd = f'set -o pipefail; {rclone_cmd} | {decompress_cmd} | {zfs_cmd}'
    else:
        print(f"Warning: Unknown compression for {backup_path}, attempting to restore without decompression.")
        full_cmd = f'set -o pipefail; {rclone_cmd} | {zfs_cmd}'

    print(f"\nRunning restore for {backup_path}:")
    print(f"  {full_cmd}")

    try:
        subprocess.run(full_cmd, shell=True, check=True, executable='/bin/bash')
        print(f"Successfully restored {backup_path}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error restoring {backup_path}: {e}")
        return False


def main():
    """Main function to run the restore."""
    parser = argparse.ArgumentParser(description="ZFS restore script from rclone.")
    parser.add_argument("--config", required=True, help="Path to the configuration file.")
    parser.add_argument("--target-dataset", required=True, help="The target ZFS dataset to restore to.")
    args = parser.parse_args()

    config = get_config(args.config)
    print("Configuration loaded.")
    print(f"Target dataset: {args.target_dataset}")

    backups = list_backups(config)
    print(f"Found {len(backups)} remote files.")

    last_full, incrementals = find_backup_chain(backups, config)

    if not last_full:
        print("No full backup found. Cannot proceed with restore.")
        sys.exit(1)

    print("\nBackup chain to be restored:")
    print(f"  Full: {last_full.path} ({last_full.timestamp}) - {human_readable_size(last_full.size)}")
    total_size = last_full.size
    for inc in incrementals:
        print(f"  Inc:  {inc.path} ({inc.timestamp}) - {human_readable_size(inc.size)}")
        total_size += inc.size

    print(f"\nTotal estimated size to download: {human_readable_size(total_size)}")
    print(f"This will restore the backups to '{args.target_dataset}'.")
    print("WARNING: This will destroy any existing data in the target dataset.")
    
    confirm = input("Are you sure you want to continue? (yes/no): ")
    if confirm.lower() != 'yes':
        print("Restore cancelled.")
        sys.exit(0)

    # Restore the full backup
    if not restore_backup(config, last_full.path, args.target_dataset):
        print("Aborting due to error in full backup restore.")
        sys.exit(1)

    # Restore incremental backups
    for inc in incrementals:
        if not restore_backup(config, inc.path, args.target_dataset):
            print(f"Aborting due to error in incremental backup restore: {inc.path}")
            sys.exit(1)
            
    print("\nRestore completed successfully!")


if __name__ == '__main__':
    main()
