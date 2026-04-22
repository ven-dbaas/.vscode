import argparse
import os
import sqlalchemy as sa
from sqlalchemy import text
import json

# Connection string may be provided via CLI `--conn` or env `MYSQL_CONN`.
parser = argparse.ArgumentParser()
parser.add_argument('--conn', '-c', help='SQLAlchemy connection string (mysql+pymysql://...)')
parser.add_argument('--database', '-d', default='employees', help='Database name to analyse')
args = parser.parse_args()
conn_str = args.conn or os.environ.get('MYSQL_CONN')
if not conn_str:
    raise SystemExit('Error: connection string required via --conn or MYSQL_CONN environment variable')
engine = sa.create_engine(conn_str)

print("=" * 70)
print("MYSQL DATABASE SIZES AND HEALTH PREDICTION")
print("=" * 70)

with engine.connect() as conn:
    # 1. Get all database sizes
    print("\n1. DATABASE SIZES")
    print("-" * 70)
    
    result = conn.execute(text("""
        SELECT table_schema as database_name, 
               round(sum((data_length + index_length) / 1024 / 1024), 2) as size_mb 
        FROM information_schema.TABLES 
        WHERE table_schema NOT IN ('mysql', 'information_schema', 'performance_schema', 'sys') 
        GROUP BY table_schema 
        ORDER BY size_mb DESC
    """))
    
    databases = []
    for row in result:
        databases.append({"database": row[0], "size_mb": row[1]})
        print(f"  {row[0]:20} {row[1]:>10.2f} MB")
    
    print(f"\n  Total databases: {len(databases)}")
    
    # 2. Health prediction for employees
    print("\n2. HEALTH ANALYSIS - employees DATABASE")
    print("-" * 70)
    
    database_name = args.database
    
    # Table Statistics
    tables_query = text("""
        SELECT TABLE_NAME, TABLE_ROWS, 
               round((DATA_LENGTH / 1024 / 1024), 2) as data_size_mb,
               round((INDEX_LENGTH / 1024 / 1024), 2) as index_size_mb,
               ENGINE
        FROM information_schema.TABLES 
        WHERE TABLE_SCHEMA = :db_name
        ORDER BY DATA_LENGTH DESC
    """)
    tables = list(conn.execute(tables_query, {"db_name": database_name}).mappings())
    
    # Storage Summary
    storage_query = text("""
        SELECT 
            COUNT(*) as table_count,
            round(SUM(DATA_LENGTH) / 1024 / 1024, 2) as data_mb,
            round(SUM(INDEX_LENGTH) / 1024 / 1024, 2) as index_mb,
            round((SUM(DATA_LENGTH) + SUM(INDEX_LENGTH)) / 1024 / 1024, 2) as total_mb,
            SUM(TABLE_ROWS) as total_rows
        FROM information_schema.TABLES 
        WHERE TABLE_SCHEMA = :db_name
    """)
    storage = list(conn.execute(storage_query, {"db_name": database_name}).mappings())
    
    # Index Count
    index_query = text("""
        SELECT COUNT(*) as index_count
        FROM information_schema.STATISTICS 
        WHERE TABLE_SCHEMA = :db_name
    """)
    index_count = list(conn.execute(index_query, {"db_name": database_name}).mappings())[0]['index_count']
    
    # Calculate health score
    storage_data = storage[0] if storage else {}
    health_score = 100
    warnings = []
    
    data_mb = storage_data.get('data_mb') or 0
    index_mb = storage_data.get('index_mb') or 0
    total_rows = storage_data.get('total_rows') or 0
    
    # Index to data ratio analysis
    if data_mb > 0:
        index_ratio = (index_mb / data_mb) * 100
        if index_ratio > 80:
            health_score -= 15
            warnings.append("⚠ High index-to-data ratio (indexes may be oversized)")
        elif index_ratio < 5:
            health_score -= 10
            warnings.append("⚠ Low index-to-data ratio (may lack proper indexes)")
    else:
        index_ratio = 0
    
    if total_rows == 0:
        health_score -= 20
        warnings.append("⚠ No data in tables")
    
    # Display summary
    print(f"\n  Summary:")
    print(f"    Tables: {storage_data.get('table_count')}")
    print(f"    Total Rows: {int(total_rows) if total_rows else 0:,}")
    print(f"    Data Size: {data_mb} MB")
    print(f"    Index Size: {index_mb} MB")
    print(f"    Total Size: {storage_data.get('total_mb')} MB")
    print(f"    Index Count: {index_count}")
    
    print(f"\n  Metrics:")
    print(f"    Index-to-Data Ratio: {round(index_ratio, 2)}%")
    
    print(f"\n  HEALTH SCORE: {health_score}/100")
    
    if warnings:
        print(f"\n  Issues Found:")
        for warning in warnings:
            print(f"    {warning}")
    else:
        print(f"\n  Status: ✓ No issues detected")
    
    print(f"\n  Top Tables by Size:")
    for table in tables[:5]:
        rows = table.get('TABLE_ROWS') if table.get('TABLE_ROWS') else 0
        print(f"    {table['TABLE_NAME']:20} | {rows:>10,} rows | {table['data_size_mb']:>8.2f} MB data | {table['index_size_mb']:>8.2f} MB idx")

print("\n" + "=" * 70)
