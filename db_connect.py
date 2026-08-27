import psycopg2
import boto3

password = "Yuvashree2718"

conn = None
try:
    print("Connection start")
    conn = psycopg2.connect(
        host='cloud-rag-apis.cqvqyakecocp.us-east-1.rds.amazonaws.com',
        port=5432,
        database='postgres',
        user='postgres',
        password=password
    )
    print("Connection done")
    cur = conn.cursor()
    cur.execute('SELECT version();')
    print(cur.fetchone()[0])
    cur.close()
except Exception as e:
    print(f"Database error: {e}")
    raise
finally:
    if conn:
        conn.close()