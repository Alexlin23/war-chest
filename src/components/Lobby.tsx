import { useEffect, useState } from 'react';
import { Crown, Play, RefreshCcw } from 'lucide-react';
import { createGame, type NewGameOptions } from '../lib/api';

const seats: Record<string,string>={south:'南境军团',north:'北境守军',south2:'南境友军',north2:'北境友军'};
export function Lobby(){
  const [players,setPlayers]=useState<2|4>(2);
  const [setup,setSetup]=useState<NewGameOptions['setup']|'custom'>('recommended');
  const [seed,setSeed]=useState('');
  const [units,setUnits]=useState<Array<{unit_type:string;name:string}>>([]);
  const [armies,setArmies]=useState<Record<string,string[]>>({});
  const [created,setCreated]=useState<{game_id:string;join_urls:Record<string,string>}|null>(null);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  useEffect(()=>{fetch('/api/v1/rules').then(r=>{if(!r.ok)throw Error('规则服务未连接，请启动后端');return r.json();})
    .then(d=>setUnits(d.units)).catch(e=>setError(String(e.message)));},[]);
  const activeSeats=players===2?['south','north']:['south','north','south2','north2'];
  const size=players===2?4:3;
  const create=async()=>{
    setBusy(true);setError('');
    try{
      const options:NewGameOptions={setup:setup==='custom'?'recommended':setup,player_count:players};
      if(seed.trim()){
        const n=Number(seed);
        if(!Number.isSafeInteger(n))throw Error('种子需要是整数');
        options.seed=n;
      }
      if(setup==='custom'){
        const picked=activeSeats.flatMap(s=>armies[s]||[]);
        if(picked.length!==players*size || new Set(picked).size!==picked.length || picked.includes(''))throw Error('请为每个席位选齐不同的兵种');
        options.rosters=Object.fromEntries(activeSeats.map(s=>[s,armies[s]]));
      }
      setCreated(await createGame(options));
    }catch(e){setError(e instanceof Error?e.message:'创建失败');}
    finally{setBusy(false);}
  };
  return <main className="lobby"><div className="lobby-brand"><Crown size={36}/><span>WAR CHEST</span></div>
    <div className="overline">BASE GAME · 战争之匣基础版</div><h1>布阵，出征。</h1>
    <p className="lobby-intro">16 种兵种，双人对决或四人组队。选定军团，争夺据点。</p>
    <div className="lobby-card"><h2>开始一局</h2>
      <label>对战人数<select value={players} onChange={e=>{setPlayers(Number(e.target.value) as 2|4);setArmies({});setCreated(null);if(e.target.value==='4'&&!['random','draft','custom'].includes(setup))setSetup('random');}}>
        <option value={2}>双人对决 · 控制 6 个据点获胜</option><option value={4}>四人组队 · 控制 8 个据点获胜</option></select></label>
      <label>兵种选择<select value={setup} onChange={e=>{setSetup(e.target.value as typeof setup);setCreated(null);}}>
        {players===2&&<option value="recommended">首次游戏推荐阵容</option>}
        <option value="random">随机阵容</option><option value="draft">轮流选兵</option><option value="custom">自选阵容</option>
        {players===2&&<><option value="gaugamela">高加米拉之战</option><option value="bannockburn">班诺克本之战</option><option value="crecy">克雷西之战</option></>}
      </select></label>
      {setup==='custom'&&<div className="roster-picker">{activeSeats.map(s=><fieldset key={s}><legend>{seats[s]}</legend>{Array.from({length:size},(_,i)=>
        <select key={i} aria-label={`${seats[s]}兵种${i+1}`} value={armies[s]?.[i]||''} onChange={e=>setArmies(prev=>{
          const army=[...(prev[s]||Array(size).fill(''))];army[i]=e.target.value;return {...prev,[s]:army};})}>
          <option value="">选择兵种</option>{units.map(u=><option key={u.unit_type} value={u.unit_type} disabled={Object.values(armies).flat().includes(u.unit_type)&&armies[s]?.[i]!==u.unit_type}>{u.name}</option>)}</select>)}</fieldset>)}</div>}
      <label>对局种子 <small>可留空，同一种子和阵容可复现抽币</small><input inputMode="numeric" value={seed} onChange={e=>setSeed(e.target.value)} placeholder="随机"/></label>
      <p className="lobby-note">采用原始基础版皇家卫队能力。对局自动存档，关闭服务后可继续。</p>
      {error&&<p className="error-banner" role="alert">{error}</p>}
      <button className="submit-action" disabled={busy} onClick={()=>void create()}>{busy?<RefreshCcw size={18}/>:<Play size={18}/>} {busy?'正在准备战场…':'创建对局'}</button>
    </div>
    {created&&<section className="lobby-card" aria-live="polite"><h2>战场已就绪</h2><p>每位玩家使用独立的浏览器会话打开自己的席位链接。收藏链接即可继续本局。</p>
      <div className="join-links">{Object.entries(created.join_urls).map(([s,url])=><div key={s}><a href={url}>{seats[s]} →</a><button onClick={()=>void navigator.clipboard.writeText(new URL(url,window.location.origin).href)}>复制链接</button></div>)}</div>
    </section>}
    <a className="lobby-preview" href="/?demo=1">查看界面预览</a>
  </main>;
}
