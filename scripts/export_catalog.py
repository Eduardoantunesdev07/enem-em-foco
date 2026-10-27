"""Export only the public exam catalog; never export study attempts or notes."""
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
TABLES = ('exams', 'questions')


def sql_literal(value):
    if value is None:
        return 'NULL'
    if isinstance(value, int):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def export_catalog(source, destination):
    connection = sqlite3.connect(f'{Path(source).resolve().as_uri()}?mode=ro', uri=True)
    try:
        lines = ['-- ENEM em Foco: public exam catalog only.',
                 '-- This file deliberately excludes attempts, answers and error_notes.', 'BEGIN;']
        for table in TABLES:
            columns = [row[1] for row in connection.execute(f'PRAGMA table_info({table})')]
            rows = connection.execute(f'SELECT * FROM {table} ORDER BY id').fetchall()
            if not columns or not rows:
                raise ValueError(f'Catalog table is empty: {table}')
            for row in rows:
                lines.append(f'INSERT INTO {table} ({",".join(columns)}) VALUES ({",".join(sql_literal(v) for v in row)});')
        lines.append('COMMIT;')
        Path(destination).write_text('\n'.join(lines) + '\n', encoding='utf-8')
    finally:
        connection.close()


if __name__ == '__main__':
    export_catalog(ROOT / 'data/enem.sqlite3', ROOT / 'database/catalog.sql')
    print('Exported only exams and questions to database/catalog.sql')
