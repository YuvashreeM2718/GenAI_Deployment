import psycopg2

password = "Prateek1234"

conn = None
try:
    print("Connection Start")
    conn = psycopg2.connect(
        host='reg-api-db.cajuqiq0k7h4.us-east-1.rds.amazonaws.com',
        port=5432,
        database='postgres',
        user='postgres',
        password=password
    )
    print("Connection Done")
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