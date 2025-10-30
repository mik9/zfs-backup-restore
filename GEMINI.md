# Project Overview

This project provides Python scripts for backing up and restoring ZFS datasets to/from a cloud storage provider using `rclone`. It supports both full and incremental backups and restores.

### Backup Script (`backup.py`)
The backup script performs the following actions:
1.  Creates a new ZFS snapshot.
2.  Streams the snapshot data using `zfs send`. The stream is compressed.
3.  Uploads the compressed stream to the configured `rclone` remote.
4.  If the backup is successful, it prunes old local snapshots based on a configurable retention policy.
5.  If the backup fails or is interrupted, it automatically deletes the newly created snapshot to ensure cleanup.

### Restore Script (`restore.py`)
The restore script performs the following actions:
1.  Lists available backups on the `rclone` remote.
2.  Identifies the latest full backup and subsequent incremental backups for a specified dataset.
3.  Streams the backup data from the `rclone` remote, decompresses it, and pipes it to `zfs receive` to restore the dataset.
4.  Includes a user confirmation step before initiating the restore to prevent accidental data loss.

## Key Technologies

*   Python 3
*   ZFS
*   rclone
*   gzip/pigz/zstd
*   systemd

## Architecture

The project consists of two main executable Python files (`main.py` for backup, `restore.py` for restore) and a shared configuration module (`config.py`). The configuration is read from `config.ini` and loaded into a `BackupConfig` dataclass for type-safe access. Example `systemd` unit and timer files are provided for automated execution of the backup script.

# Building and Running

## Dependencies

The script requires the following dependencies to be installed:

*   Python 3
*   `rclone`
*   `zfs`

## Running the Backup Script

The backup script (`main.py`) is executable. To run it manually, use the following command. It must be run with `sudo` to have the necessary permissions for ZFS operations.

```bash
sudo ./main.py --config config.ini
```

Use the `--full` flag to force a full backup:

```bash
sudo ./main.py --config config.ini --full
```

## Running the Restore Script

The restore script (`restore.py`) is executable. To run it manually, use the following command. It must be run with `sudo` to have the necessary permissions for ZFS operations.

```bash
sudo ./restore.py --config config.ini --target-dataset pool/data-restored
```

**WARNING**: The restore process will destroy any existing data in the `--target-dataset`.

## Configuration

The scripts are configured through the `config.ini` file, which is parsed into a `BackupConfig` dataclass defined in `config.py`. This provides type-safe access to configuration parameters.

```ini
[zfs]
dataset = pool/data
snapshot_prefix = glacier-backup-
snapshot_retention = 7

[rclone]
remote = s3-backup
bucket_name = s3-backup-bucket
config_path = /home/{user}/.config/rclone/rclone.conf

[compression]
compressor = pigz
```

*   `zfs.dataset`: The ZFS dataset to back up (e.g., `pool/data`).
*   `zfs.snapshot_prefix`: The prefix for the ZFS snapshot names (e.g., `glacier-backup-`).
*   `zfs.snapshot_retention`: The number of recent local snapshots to keep after a successful backup. Set to `0` to disable local pruning.
*   `rclone.remote`: The `rclone` remote to use for the backup (e.g., `s3-backup`).
*   `rclone.bucket_name`: The bucket name on the `rclone` remote (e.g., `s3-backup-bucket`).
*   `rclone.config_path`: The absolute path to the `rclone` configuration file (e.g., `/home/{user}/.config/rclone/rclone.conf`).
*   `compression.compressor`: The compression tool to use. Supported values are `gzip`, `pigz` (default), and `zstd`.

Example `systemd` service and timer files are provided to automate the backup process.

*   `glacier-backup.service.example`: The service unit that runs the backup script.
*   `glacier-backup.timer.example`: The timer unit that triggers the service daily.

To install and enable the service:
1.  Copy the files to the systemd directory, removing the `.example` suffix:
    ```bash
    sudo cp glacier-backup.service.example /etc/systemd/system/glacier-backup.service
    sudo cp glacier-backup.timer.example /etc/systemd/system/glacier-backup.timer
    ```
2.  Reload the systemd daemon to recognize the new files:
    ```bash
    sudo systemctl daemon-reload
    ```
3.  Enable and start the timer:
    ```bash
    sudo systemctl enable glacier-backup.timer
    sudo systemctl start glacier-backup.timer
    ```
You can check the status of the timer with `systemctl status glacier-backup.timer` and view logs with `journalctl -u glacier-backup.service`.