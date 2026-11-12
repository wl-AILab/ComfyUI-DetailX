from .store import RequestStore


class PostgresRequestStore(RequestStore):
    """Transactional snapshots for deployments spanning multiple ephemeral runners."""
    def __init__(self, dsn):
        import psycopg
        from psycopg.types.json import Jsonb
        self.psycopg = psycopg
        self.Jsonb = Jsonb
        self.dsn = dsn
        with self.psycopg.connect(self.dsn) as db:
            db.execute("CREATE TABLE IF NOT EXISTS detailx_requests(scope TEXT, kind TEXT, id TEXT, value JSONB NOT NULL, PRIMARY KEY(scope,kind,id))")

    def get(self, scope, kind, request_id):
        with self.psycopg.connect(self.dsn) as db:
            row = db.execute("SELECT value FROM detailx_requests WHERE scope=%s AND kind=%s AND id=%s", (scope, kind, request_id)).fetchone()
            return row[0] if row else None

    def put_once(self, scope, kind, request_id, value):
        with self.psycopg.connect(self.dsn) as db:
            db.execute("INSERT INTO detailx_requests VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING", (scope, kind, request_id, self.Jsonb(value)))
            return db.execute("SELECT value FROM detailx_requests WHERE scope=%s AND kind=%s AND id=%s", (scope, kind, request_id)).fetchone()[0]

    def update(self, scope, kind, request_id, value):
        with self.psycopg.connect(self.dsn) as db:
            db.execute("UPDATE detailx_requests SET value=%s WHERE scope=%s AND kind=%s AND id=%s", (self.Jsonb(value), scope, kind, request_id))
