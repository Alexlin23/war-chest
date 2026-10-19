"""Small local SQLite store. Rules/simulation never depend on database I/O."""
from pathlib import Path
import sqlite3
from threading import RLock
from .state import dumps, loads, action_dict, state_digest, RULESET_VERSION


class GameStore:
    def __init__(self,path):
        if path != ':memory:': Path(path).parent.mkdir(parents=True,exist_ok=True)
        self.lock=RLock()
        self.db=sqlite3.connect(path,check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS games(
                id TEXT PRIMARY KEY, state TEXT NOT NULL, invites TEXT NOT NULL, secret BLOB NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions(
                token TEXT PRIMARY KEY, game_id TEXT NOT NULL, seat TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS initial_states(
                game_id TEXT PRIMARY KEY, state TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS decisions(
                game_id TEXT NOT NULL, revision INTEGER NOT NULL, actor TEXT NOT NULL,
                action TEXT NOT NULL, digest TEXT NOT NULL, PRIMARY KEY(game_id,revision));
            INSERT OR IGNORE INTO initial_states SELECT id,state FROM games;
        ''')
        self.db.commit()

    def save_game(self,gid,game,invites,secret,*,action=None,actor=None):
        import json
        payload=dumps(game)
        with self.lock,self.db:
            self.db.execute('INSERT OR IGNORE INTO initial_states VALUES(?,?)',(gid,payload))
            self.db.execute('INSERT INTO games VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET state=excluded.state',
                (gid,payload,json.dumps(invites),secret))
            if action is not None:
                self.db.execute('INSERT INTO decisions VALUES(?,?,?,?,?)',
                    (gid,game.revision,actor,json.dumps(action_dict(action)),state_digest(game)))

    def load_game(self,gid):
        import json
        with self.lock:
            row=self.db.execute('SELECT state,invites,secret FROM games WHERE id=?',(gid,)).fetchone()
        return (loads(row[0]),json.loads(row[1]),row[2]) if row else None

    def save_session(self,token,gid,seat):
        with self.lock,self.db:
            self.db.execute('INSERT INTO sessions VALUES(?,?,?)',(token,gid,seat))

    def load_session(self,token):
        with self.lock:
            row=self.db.execute('SELECT game_id,seat FROM sessions WHERE token=?',(token,)).fetchone()
        return tuple(row) if row else None

    def load_trace(self,gid,game):
        import json
        with self.lock:
            initial=self.db.execute('SELECT state FROM initial_states WHERE game_id=?',(gid,)).fetchone()
            rows=self.db.execute('SELECT revision,actor,action,digest FROM decisions WHERE game_id=? ORDER BY revision',(gid,)).fetchall()
        if initial is None: raise ValueError('no saved trace')
        return {'schema_version':1,'ruleset_version':RULESET_VERSION,
            'initial_state':json.loads(initial[0]),
            'decisions':[{'revision':r,'actor':a,'action':json.loads(v),'state_digest':d} for r,a,v,d in rows],
            'winner':game.winner,'terminated':bool(game.winner),'truncated':False,'max_decisions':None}
