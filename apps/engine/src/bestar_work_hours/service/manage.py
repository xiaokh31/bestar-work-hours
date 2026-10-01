"""Explicit, versioned schema setup."""
import argparse

from .config import Settings
from .database import Database


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["migrate"])
    parser.parse_args()
    db = Database(Settings.from_env().database_url)
    db.migrate()
    print("Schema version 2 ready")


if __name__ == "__main__":
    main()
