#!/usr/bin/env -S python3 -u

import os
import subprocess
from datetime import datetime
import signal
import sys
import time
import argparse

from config import get_config, BackupConfig, TIMESTAMP_FORMAT
from compression import get_compressor_by_name


def get_snapshots(config: BackupConfig):
    """Get a list of ZFS snapshots for the dataset."""
    cmd = f"zfs list -t snapshot -o name -s creation -r {config.zfs_dataset}"
    result = subprocess.run(cmd, shell=True, check=True, stdout=subprocess.PIPE, text=True)
    snapshots = result.stdout.strip().split('\n')
    return [s for s in snapshots if f'{config.zfs_dataset}@{config.snapshot_prefix}' in s]


def create_snapshot(snapshot_name):
    """Create a new ZFS snapshot."""
    cmd = f'zfs snapshot {snapshot_name}'
    subprocess.run(cmd, shell=True, check=True)


def backup_snapshot(config: BackupConfig, snapshot_name, last_snapshot=None):
    """Backup a ZFS snapshot to S3 Glacier."""
    compressor = get_compressor_by_name(config.compressor)

    if last_snapshot:
        # Incremental backup
        print(f'Creating incremental backup from {last_snapshot} to {snapshot_name}')
        zfs_cmd = f'zfs send -v -c -i {last_snapshot} {snapshot_name}'
        remote_path = f'{config.rclone_remote}:{config.bucket_name}/{snapshot_name}-incremental.{compressor.extension}'
    else:
        # Full backup
        print(f'Creating full backup of {snapshot_name}')
        zfs_cmd = f'zfs send -v -c {snapshot_name}'
        remote_path = f'{config.rclone_remote}:{config.bucket_name}/{snapshot_name}-full.{compressor.extension}'

    rclone_cmd = f'rclone --config {config.rclone_config_path} rcat {remote_path} --stats-one-line'

    full_cmd = f'set -o pipefail; {zfs_cmd} | {compressor.compress_cmd} | {rclone_cmd}'

    print(f'Running backup: {full_cmd}')

    process = subprocess.Popen(full_cmd, shell=True, executable='/bin/bash', preexec_fn=os.setsid)
    return process


def prune_snapshots(config: BackupConfig):
    """Prune old snapshots, keeping the N most recent ones."""
    if config.snapshot_retention <= 0:
        print("Snapshot retention must be a positive number. Skipping pruning.")
        return

    snapshots = get_snapshots(config)

    # The new snapshot is included, so we keep retention_count
    if len(snapshots) > config.snapshot_retention:
        snapshots_to_prune = snapshots[:len(snapshots) - config.snapshot_retention]
        print(f"Pruning {len(snapshots_to_prune)} old snapshots...")
        for snapshot in snapshots_to_prune:
            destroy_snapshot(snapshot, silent=True)


def destroy_snapshot(snapshot_name, silent=False):
    """Destroy a ZFS snapshot, with retries on busy error."""
    if not snapshot_name:
        return

    if not silent:
        print(f"Destroying snapshot: {snapshot_name}")

    retries = 5
    delay = 2  # seconds

    for attempt in range(retries):
        try:
            cmd = f'zfs destroy {snapshot_name}'
            subprocess.run(cmd, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if not silent:
                print(f"Successfully destroyed snapshot {snapshot_name}")
            return  # Success
        except subprocess.CalledProcessError as e:
            stderr_output = e.stderr.decode().strip()
            if 'dataset is busy' in stderr_output and attempt < retries - 1:
                if not silent:
                    print(f"Snapshot is busy, retrying in {delay}s ({attempt + 1}/{retries - 1})...")
                time.sleep(delay)
            else:
                if not silent:
                    print(f"Failed to destroy snapshot {snapshot_name}: {stderr_output}")
                break  # Failed for good


def main():
    """Main function to run the backup."""

    parser = argparse.ArgumentParser(description="ZFS backup script with rclone.")
    parser.add_argument("--full", action="store_true", help="Force a full backup, even if previous snapshots exist.")
    parser.add_argument("--config", default="config.ini", help="Path to the configuration file.")
    args = parser.parse_args()

    def signal_handler(signum, frame):
        """Handle signals by raising KeyboardInterrupt."""
        print(f"\nReceived signal {signum}, shutting down gracefully...")
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, signal_handler)

    config = get_config(args.config)
    new_snapshot = None
    backup_process = None
    try:
        snapshots = get_snapshots(config)
        latest_snapshot = snapshots[-1] if snapshots else None

        if args.full:
            print("Full backup forced by command-line argument.")
            latest_snapshot = None

        timestamp = datetime.now().strftime(TIMESTAMP_FORMAT)
        new_snapshot = f'{config.zfs_dataset}@{config.snapshot_prefix}{timestamp}'

        create_snapshot(new_snapshot)

        backup_process = backup_snapshot(config, new_snapshot, latest_snapshot)
        backup_process.wait()

        if backup_process.returncode == 0:
            print("Backup successful!")
            prune_snapshots(config)
        else:
            print(f"Backup failed with exit code {backup_process.returncode}")
            destroy_snapshot(new_snapshot)

    except KeyboardInterrupt:
        print("\nBackup interrupted by user or system.")
        if backup_process and backup_process.poll() is None:
            print("Terminating backup process group...")
            try:
                os.killpg(os.getpgid(backup_process.pid), signal.SIGTERM)
                backup_process.wait()
            except ProcessLookupError:
                print("Backup process already finished.")
        destroy_snapshot(new_snapshot)
        sys.exit(1)


if __name__ == '__main__':
    main()
