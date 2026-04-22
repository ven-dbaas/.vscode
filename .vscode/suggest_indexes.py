import argparse
import os
import sqlalchemy as sa
from sqlalchemy import text

# Connection string may be provided via CLI `--conn` or env `MYSQL_CONN`.
parser = argparse.ArgumentParser()
parser.add_argument('--conn', '-c', help='SQLAlchemy connection string (mysql+pymysql://...)')
parser.add_argument('--database', '-d', default='employees', help='Database name to inspect')
args = parser.parse_args()
conn_str = args.conn or os.environ.get('MYSQL_CONN')
if not conn_str:
    raise SystemExit('Error: connection string required via --conn or MYSQL_CONN environment variable')
engine = sa.create_engine(conn_str)

with engine.connect() as conn:
    # Get top tables by size
    tops = conn.execute(text("""
        SELECT TABLE_NAME, round((DATA_LENGTH + INDEX_LENGTH) / 1024 / 1024, 2) as size_mb
        FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = DATABASE()
        ORDER BY (DATA_LENGTH + INDEX_LENGTH) DESC
        LIMIT 5
    """)).fetchall()

    for tbl, size in tops:
        print(f"\nTable: {tbl} ({size} MB)")
        cols = [r[0] for r in conn.execute(text("SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=:t ORDER BY ORDINAL_POSITION"), {"t": tbl}).fetchall()]
        idxs = [r[0] for r in conn.execute(text("SELECT DISTINCT INDEX_NAME FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=:t"), {"t": tbl}).fetchall()]
        idx_map = {}
        for row in conn.execute(text("SELECT INDEX_NAME, COLUMN_NAME, SEQ_IN_INDEX FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=:t ORDER BY INDEX_NAME, SEQ_IN_INDEX"), {"t": tbl}).fetchall():
            idx_map.setdefault(row[0], []).append(row[1])

        print(f"  Columns: {', '.join(cols)}")
        print(f"  Existing Indexes: {len(idxs)} -> {', '.join(idxs)}")

        suggestions = []
        # common foreign key pattern
        if 'emp_no' in cols:
            # check if any index covers emp_no
            emp_indexed = any('emp_no' in cols_list for cols_list in idx_map.values())
            if not emp_indexed:
                suggestions.append((f"CREATE INDEX idx_{tbl}_emp_no ON {tbl}(emp_no);", "Index emp_no for joins/filters"))
            else:
                # find if composite with from_date exists
                if 'from_date' in cols:
                    composite = any(cols_list[:2] == ['emp_no', 'from_date'] or cols_list[:2] == ['emp_no', 'to_date'] for cols_list in idx_map.values())
                    if not composite:
                        suggestions.append((f"CREATE INDEX idx_{tbl}_emp_from ON {tbl}(emp_no, from_date);", "Composite index for emp_no + from_date queries"))
        if 'dept_no' in cols:
            dept_indexed = any('dept_no' in cols_list for cols_list in idx_map.values())
            if not dept_indexed:
                suggestions.append((f"CREATE INDEX idx_{tbl}_dept_no ON {tbl}(dept_no);", "Index dept_no for joins/filters"))
        # if table is big and has date ranges, consider partitioning (suggest only)
        if size > 50 and ('from_date' in cols or 'to_date' in cols):
            suggestions.append((f"-- Consider partitioning {tbl} by RANGE (YEAR(from_date)) if historical data is large", "Partition suggestion"))

        if not suggestions:
            print("  Suggestions: No immediate index additions detected; review slow queries for targeted tuning.")
        else:
            print("  Suggestions:")
            for sql, reason in suggestions:
                print(f"    - {reason}: {sql}")

print('\nDone.')
