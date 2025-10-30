# ZFS Glacier Backup Script

This project provides Python scripts for backing up and restoring ZFS datasets to/from a cloud storage provider using `rclone`. It supports both full and incremental backups and restores.

## Key Technologies

*   Python 3
*   ZFS
*   rclone
*   gzip/pigz/zstd
*   systemd

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