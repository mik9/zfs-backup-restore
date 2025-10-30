import configparser
import sys
from dataclasses import dataclass

TIMESTAMP_FORMAT = '%Y-%m-%d_%H-%M-%S'


@dataclass
class BackupConfig:
    """Typed configuration for the backup and restore scripts."""
    # [zfs]
    zfs_dataset: str
    snapshot_prefix: str
    snapshot_retention: int

    # [rclone]
    rclone_remote: str
    bucket_name: str
    rclone_config_path: str

    # [compression]
    compressor: str


def get_config(config_path: str) -> BackupConfig:
    """Read configuration from the specified path and return a typed dataclass."""
    parser = configparser.ConfigParser()
    if not parser.read(config_path):
        print(f"Error: Configuration file not found at {config_path}")
        sys.exit(1)

    try:
        config = BackupConfig(
            # [zfs]
            zfs_dataset=parser.get('zfs', 'dataset'),
            snapshot_prefix=parser.get('zfs', 'snapshot_prefix'),
            snapshot_retention=parser.getint('zfs', 'snapshot_retention'),

            # [rclone]
            rclone_remote=parser.get('rclone', 'remote'),
            bucket_name=parser.get('rclone', 'bucket_name'),
            rclone_config_path=parser.get('rclone', 'config_path'),

            # [compression]
            compressor=parser.get('compression', 'compressor', fallback='pigz')
        )
        return config
    except (configparser.NoSectionError, configparser.NoOptionError) as e:
        print(f"Error: Missing configuration option in '{config_path}': {e}")
        sys.exit(1)
    except ValueError as e:
        print(f"Error: Invalid value in configuration file '{config_path}': {e}")
        sys.exit(1)
