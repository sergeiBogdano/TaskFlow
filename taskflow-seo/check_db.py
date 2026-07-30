import sqlite3
c = sqlite3.connect(r'C:\Dashboard\TG\taskflow-seo\data\taskflow.db')
tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print('Tables:', tables)
rows = c.execute('SELECT id, title, status FROM tasks').fetchall()
print('Tasks:', rows)
c.close()
