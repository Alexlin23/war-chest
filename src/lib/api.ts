import type { GameView, ActionResponse } from '../types';

export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message); this.name = 'ApiError'; }
}
function guard(v: unknown): GameView {
  if (!v || typeof v !== 'object') throw new Error('服务端返回的视图不是对象');
  const a = v as Partial<GameView>;
  if (a.schema_version !== 1 || typeof a.game_id !== 'string' ||
      typeof a.revision !== 'number' || !Array.isArray(a.board) ||
      !Array.isArray(a.players) || !Array.isArray(a.hand) ||
      !Array.isArray(a.legal_actions) || !Array.isArray(a.events)) {
    throw new Error('服务端视图协议不兼容：需要 GameView schema_version=1');
  }
  return a as GameView;
}
function path(gameId: string): string {
  return `/api/v1/games/${encodeURIComponent(gameId)}`;
}
async function jsonResponse(res: Response): Promise<unknown> {
  if (!res.ok) throw new ApiError(`请求失败（HTTP ${res.status}）`, res.status);
  return res.json();
}
export async function loadView(gameId: string, signal?: AbortSignal): Promise<GameView> {
  const res = await fetch(`${path(gameId)}/view`, {
    credentials: 'include', cache: 'no-store', signal,
    headers: { Accept: 'application/json' },
  });
  return guard(await jsonResponse(res));
}
export async function submitAction(gameId: string, actionId: string, revision: number): Promise<GameView> {
  const res = await fetch(`${path(gameId)}/actions`, {
    method: 'POST', credentials: 'include', cache: 'no-store',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ action_id: actionId, expected_revision: revision }),
  });
  const data = await jsonResponse(res) as ActionResponse;
  return guard(data.view);
}

export interface NewGameOptions {
  setup: 'recommended' | 'random' | 'draft' | 'gaugamela' | 'bannockburn' | 'crecy';
  player_count: 2 | 4;
  seed?: number;
  rosters?: Record<string,string[]>;
}
export async function createGame(options: NewGameOptions): Promise<{game_id:string;join_urls:Record<string,string>}> {
  const res=await fetch('/api/v1/dev/games',{
    method:'POST',credentials:'include',cache:'no-store',
    headers:{'Content-Type':'application/json',Accept:'application/json'},
    body:JSON.stringify(options),
  });
  return await jsonResponse(res) as {game_id:string;join_urls:Record<string,string>};
}
