from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / 'data/enem.sqlite3'


class Connection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


def connect(path=None):
    connection = sqlite3.connect(path or DB_PATH, timeout=15, factory=Connection)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys = ON')
    return connection


def initialize(path=None):
    target = Path(path or DB_PATH)
    target.parent.mkdir(parents=True, exist_ok=True)
    with connect(target) as connection:
        connection.executescript((ROOT / 'database/schema.sql').read_text(encoding='utf-8'))
        if connection.execute('SELECT COUNT(*) FROM exams').fetchone()[0] == 0:
            seed = ROOT / 'database/catalog.sql'
            if seed.is_file():
                connection.executescript(seed.read_text(encoding='utf-8'))
