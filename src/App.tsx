import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Activity, AlertCircle, ArrowDownUp, ArrowRight, BookOpen, Check, ChevronDown, CircleHelp, Crown, Flag, History, Layers, LocateFixed, LockKeyhole, Menu, MoveUpRight, Play, RefreshCcw, ScrollText, Shield, ShieldPlus, Swords, Target, X } from 'lucide-react';
import type { ActionView, GameView, HexView, PlayerView } from './types';
import { previewView } from './demo';
import { loadView, submitAction, ApiError } from './lib/api';
import { HexBoard } from './components/HexBoard';
import { Coin } from './components/Coin';
import { Lobby } from './components/Lobby';
import './styles/app.css';

const query=new URLSearchParams(window.location.search);
const explicitGame=query.get('game');
const preview=query.get('demo')==='1';
const gameId=explicitGame||'';
const groupLabels:Record<string,string>={deploy:'部署 / 增援',maneuver:'棋盘行动',recruit:'招募 / 物资',initiative:'先手',special:'战术 / 特殊',other:'其他行动'};
const groupOrder=['maneuver','special','deploy','recruit','initiative','other'];
const actionIcons={move:MoveUpRight,attack:Swords,deploy:Layers,shield:ShieldPlus,recruit:ScrollText,flag:Flag,pass:ArrowRight,tactic:Target};

function PlayerBanner({player,active,initiative,compact=false}:{player:PlayerView,active:boolean,initiative:boolean,compact?:boolean}){
  return <div className={`player-banner ${player.side} ${active?'active':''} ${compact?'compact':''}`}>
    <div className="player-crest"><Shield size={22} strokeWidth={1.5}/><span>{player.side==='north'?'北':'南'}</span></div>
    <div className="player-detail"><span className="eyebrow">{player.is_viewer?'你的军团':player.is_ally?'友方军团':'对方军团'} {initiative?'· 持有先手':''}</span><strong>{player.name}</strong><span className="player-sub">{player.color_name}军 · 手牌 {player.hand_count} 枚</span></div>
    <div className="player-progress"><span>控制点</span><div className="control-markers" aria-label={`${player.control_count}/${player.control_target} 个控制点`}>
      {Array.from({length:player.control_target},(_,i)=><span key={i} className={i<player.control_count?'earned':''}/>)}</div>
      <strong>{player.control_count}<small> / {player.control_target}</small></strong>
    </div>
  </div>;
}
function Badge({children,kind='regular'}:{children:React.ReactNode,kind?:string}){return <span className={`badge badge-${kind}`}>{children}</span>;}
function PlayerSupply({player}:{player:PlayerView}){return <div className="army-supply">
  <div className="section-heading"><span>兵种编成</span><small>公开信息</small></div>
  <div className="army-list">{player.army.map((a,i)=><div className="army-row" key={`${a.unit_type}-${i}`}>
    <span className="army-token">{a.symbol||a.short_name}</span><span className="army-name"><strong>{a.name}</strong>{a.description&&<small>{a.description}</small>}</span><span className="army-count">{a.available===null?'—':a.available}</span>
  </div>)}</div>
  {!!player.faceup_discard?.length&&<div className="open-discard-info"><small>公开弃币：</small>{player.faceup_discard.map(c=><span key={c.unit_type}>{c.name}×{c.count} </span>)}</div>}
  <div className="resource-strip">
    <div><span>牌袋</span><strong>{player.bag_count??'?'}</strong></div>
    <div><span>弃币</span><strong>{player.discard_count??'?'}</strong></div>
    <div><span>供应</span><strong>{player.supply_count??'?'}</strong></div>
  </div>
</div>;}
function GameLog({events}: {events:GameView['events']}) {return <div className="log-content">{events.length===0?<p className="empty-state">暂无公开事件</p>:events.slice(0,8).map((e,i)=><div className="log-row" key={e.id}><span className={`log-dot ${e.type||'info'}`}/><div><p>{e.text}</p><small>{e.time_label}</small></div>{i===0&&<span className="log-new">NEW</span>}</div>)}</div>;}

export default function App(){return !explicitGame&&!preview?<Lobby/>:<GameApp/>;}

function GameApp(){
  const [view,setView]=useState<GameView|null>(preview?previewView:null);
  const [error,setError]=useState<string|null>(null);
  const [busy,setBusy]=useState(false);
  const [loading,setLoading]=useState(!preview);
  const [selectedCoin,setSelectedCoin]=useState<string|null>(null);
  const [selectedHex,setSelectedHex]=useState<string|null>(null);
  const [selectedActionId,setSelectedActionId]=useState<string|null>(null);
  const [panel,setPanel]=useState<'actions'|'log'|'army'>('actions');
  const [mobileMenu,setMobileMenu]=useState(false);
  const [showHelp,setShowHelp]=useState(false);
  const lastAppliedRevision=useRef(-1);
  const currentRequest=useRef(0);
  const submitting=useRef(false);

  const acceptView=useCallback((next:GameView)=>{
    if(next.revision<lastAppliedRevision.current)return;
    lastAppliedRevision.current=next.revision;
    setView(next);setSelectedActionId(null);setSelectedCoin(null);setSelectedHex(null);setError(null);
  },[]);
  const refresh=useCallback(async(silent=false)=>{
    if(preview || submitting.current)return;
    const seq=++currentRequest.current;
    if(!silent)setLoading(true);
    try{
      const next=await loadView(gameId);
      if(seq!==currentRequest.current)return;
      if(lastAppliedRevision.current<=next.revision){
        // Same-revision responses should update public log / decisions but preserve selection.
        if(lastAppliedRevision.current===next.revision)setView(next);
        else acceptView(next);
      }
      setError(null);
    }catch(e){if(seq===currentRequest.current)setError(e instanceof Error?e.message:'无法连接服务端');}
    finally{if(seq===currentRequest.current)setLoading(false);}
  },[acceptView]);
  useEffect(()=>{if(preview)return;void refresh();const timer=setInterval(()=>void refresh(true),3500);return()=>{clearInterval(timer);currentRequest.current++;};},[refresh]);

  const viewer=view?.players.find(p=>p.id===view.viewer_player_id);
  const opponent=view?.players.find(p=>p.id!==view.viewer_player_id&&!p.is_ally);
  const decision=view?.decision_player_id===view?.viewer_player_id;
  const chosenCoin=selectedCoin?view?.hand.find(c=>c.id===selectedCoin):null;
  const filteredActions=useMemo(()=>{
    if(!view)return [];
    let a=view.legal_actions;
    if(chosenCoin) a=a.filter(x=>x.payment_coin_type===chosenCoin.unit_type);
    if(selectedHex) {
      const b=a.filter(x=>x.source_hex_id===selectedHex || x.target_hex_ids?.includes(selectedHex) || x.highlight_hex_ids?.includes(selectedHex));
      if(b.length)a=b; // UI filter only, no local legality calculation.
    }
    return a;
  },[view,chosenCoin,selectedHex]);
  const presentGroups=[...groupOrder,...new Set(filteredActions.map(a=>a.group).filter(g=>!groupOrder.includes(g)))];
  const grouped=presentGroups.map(g=>({g,items:filteredActions.filter(a=>a.group===g)})).filter(g=>g.items.length);
  const selectedAction=view?.legal_actions.find(a=>a.id===selectedActionId)||null;
  const selectedHexView=view?.board.find(h=>h.id===selectedHex)||null;
  const submit=async()=>{
    if(preview||busy||!decision||!view||!selectedActionId||!view.legal_actions.some(a=>a.id===selectedActionId))return;
    const old=view;
    // Lock before async; do not optimistic-update the game state.
    submitting.current=true;setBusy(true);setError(null);
    currentRequest.current++;
    try{acceptView(await submitAction(old.game_id,selectedActionId,old.revision));}
    catch(e){
      setError(e instanceof ApiError&&e.status===409?'局面已更新，正在重新同步…':e instanceof Error?e.message:'提交失败');
      try{const latest=await loadView(old.game_id);acceptView(latest);}catch{ /* Preserve error and last verified state. */ }
    }finally{submitting.current=false;setBusy(false);}
  };
  const selectCoin=(id:string)=>{setSelectedCoin(prev=>prev===id?null:id);setSelectedActionId(null);setPanel('actions');};
  const selectHex=(id:string)=>{setSelectedHex(prev=>prev===id?null:id);setSelectedActionId(null);setPanel('actions');};
  const sideOf=(id:string|null|undefined)=>view?.players.find(p=>p.id===id)?.side||'unknown';
  return <div className="app-layout">
    <aside className={`sidebar ${mobileMenu?'open':''}`}>
      <div className="brand"><div className="brand-mark"><Crown size={23}/></div><div><div className="brand-title">WAR CHEST</div><div className="brand-kicker">战 争 之 匣 · 战 场 终 端</div></div></div>
      <div className="sidebar-section-caption">对局中心</div>
      <button className="nav-item active" onClick={()=>{setPanel('actions');setMobileMenu(false);}}><LocateFixed size={18}/>战场 <span className="nav-number">01</span></button>
      <button className={`nav-item ${panel==='army'?'sub-active':''}`} onClick={()=>{setPanel('army');setMobileMenu(false);}}><Shield size={18}/>兵团总览</button>
      <button className={`nav-item ${panel==='log'?'sub-active':''}`} onClick={()=>{setPanel('log');setMobileMenu(false);}}><History size={18}/>行动记录</button>
      <div className="sidebar-rule"><div className="side-rule-inner"/></div>
      <div className="sidebar-section-caption">指挥信息</div>
      <div className="sidebar-data"><small>本局规则</small><strong>{view?.ruleset_label||'载入中'}</strong></div>
      <div className="sidebar-data"><small>局面版本</small><strong>#{view?.revision ?? '—'}</strong></div>
      <div className="sidebar-data"><small>连接状态</small><strong className={preview?'demo-indicator':'online-indicator'}>{preview?'静态展示 / 无逻辑':error?'连接异常':'已连接'}</strong></div>
      <div className="side-note"><LockKeyhole size={17}/><p>选择手牌或棋盘上的单位，查看可执行的行动。</p></div>
      <div className="side-bottom"><span className="pulse-dot"/> WAR CHEST DISPLAY <small>v0.3</small></div>
    </aside>
    <div className="main-area">
      <header className="topbar"><button className="mobile-menu-btn" aria-label="展开菜单" onClick={()=>setMobileMenu(!mobileMenu)}><Menu size={22}/></button><div className="breadcrumbs"><a href="/" className="lobby-return">对局中心</a><span className="slash">/</span><strong>{view?.player_count===4?'四人战场':'双人战场'}</strong><span className="slash">/</span><span className="crumb-id">{view?.game_id||gameId}</span></div><div className="top-actions"><Badge kind={preview?'preview':'live'}><span className="status-dot"/>{preview?'界面预览':'游戏连接'}</Badge><button className="icon-button" title="刷新局面" aria-label="刷新局面" disabled={preview||busy} onClick={()=>void refresh()}><RefreshCcw size={17} className={loading?'rotating':''}/></button><button className="icon-button" title="界面说明" aria-label="界面说明" onClick={()=>setShowHelp(true)}><CircleHelp size={18}/></button></div></header>
      <main className="content">
        <div className="overview"><div><div className="overline"><span className="line"/> THE BATTLEFIELD · <span>01</span></div><div className="page-title-wrap"><h1>战争之匣</h1><span className="page-title-en">War Chest</span></div><p>兵临棋局，一币定势。争夺据点，赢得战场。</p></div><div className="round-card"><div className="round-icon"><ArrowDownUp size={19}/></div><div><small>当前轮次</small><strong>{String(view?.round??0).padStart(2,'0')}</strong></div><span className="round-divider"/><div><small>行动阶段</small><strong className="round-phase">{view?.phase_label||'载入中'}</strong></div></div></div>
        {preview&&<div className="preview-banner"><AlertCircle size={16}/><span><strong>静态界面预览：</strong>示例棋盘与行动仅用于检验布局，不代表正式规则；不会执行游戏动作。</span><span className="preview-link">正式连接：?game=游戏ID</span></div>}
        {error&&<div className="error-banner" role="alert"><AlertCircle size={17}/><span>{error}</span><button onClick={()=>void refresh()}>重试</button></div>}
        {!view?<div className="center-loading"><RefreshCcw className="rotating"/>正在向引擎请求对局视图…</div>:<>
          {view.players.length>2?<section className="team-banners">{view.players.map(p=><PlayerBanner key={p.id} player={p} active={view.decision_player_id===p.id} initiative={view.initiative_player_id===p.id}/>)}</section>:<section className="status-duel"><PlayerBanner player={opponent||view.players[0]} active={view.decision_player_id===opponent?.id} initiative={view.initiative_player_id===opponent?.id}/><div className="status-mid"><span>VS</span><small>{view.status==='finished'?'对局结束':view.status==='paused'?'对局暂停':decision?'等待你行动':'等待对方行动'}</small></div><PlayerBanner player={viewer||view.players[view.players.length-1]} active={decision} initiative={view.initiative_player_id===viewer?.id}/></section>}
          <section className="workspace">
            <div className="board-column"><div className="surface-head"><div><span className="overline small">TACTICAL MAP</span><h2>战术地图 <small>· 六角战场</small></h2></div><div className="board-legend"><span><i className="legend-circle neutral"/>中立据点</span><span><i className="legend-circle north"/>北境</span><span><i className="legend-circle south"/>南境</span></div></div>
              <div className="board-panel"><HexBoard board={view.board} selectedHexId={selectedHex} selectedAction={selectedAction} viewerId={view.viewer_player_id} viewerTeamId={view.viewer_team_id} onSelectHex={selectHex}/>
                <div className="board-foot"><span><LocateFixed size={14}/> {selectedHexView?`选中 ${selectedHexView.id}${selectedHexView.unit?` · ${selectedHexView.unit.name} ×${selectedHexView.unit.count}`:''}`:'点击棋盘格查看单位'}</span><span>{view.board.length} 个有效棋盘格 <ChevronDown size={13}/></span></div>
              </div>
              <div className="lower-dashboard"><div className="hand-panel"><div className="hand-title"><div><span className="overline small">YOUR HAND</span><h3>作战手牌 <small>· {view.hand.length}枚</small></h3></div><span className="hint">点击棋币查看可用行动</span></div><div className="hand-content"><div className="hand-tray">{view.hand.length?view.hand.map(c=><Coin key={c.id} coin={c} selected={selectedCoin===c.id} disabled={view.status!=='active'} onClick={()=>selectCoin(c.id)}/>):<div className="empty-state">当前没有可见手牌</div>}</div><div className="hand-footnote"><LockKeyhole size={13}/> 仅展示当前账号被授权查看的手牌</div></div></div>
                <div className="battle-detail"><div className="hand-title"><div><span className="overline small">BATTLE STATUS</span><h3>战场概况</h3></div></div><div className="battle-metrics"><div><span className="metric-icon">♜</span><strong>{viewer?.control_count??0}</strong><small>我方据点</small></div><div><span className="metric-icon">⚔</span><strong>{viewer?.board_unit_count??'?'}</strong><small>场上单位</small></div><div><span className="metric-icon">♛</span><strong>{viewer?.bag_count??'?'}</strong><small>袋内棋币</small></div></div><p className="detail-note">留意据点与棋币的分配，把握下一次出手时机。</p></div>
              </div>
            </div>
            <aside className="decision-panel"><div className="decision-tabs"><button className={panel==='actions'?'active':''} onClick={()=>setPanel('actions')}><Target size={16}/>可用指令</button><button className={panel==='log'?'active':''} onClick={()=>setPanel('log')}><History size={16}/>事件</button><button className={panel==='army'?'active':''} onClick={()=>setPanel('army')}><Layers size={16}/>兵种</button></div>
              {panel==='actions'?<><div className="decision-head"><div className="decision-state-icon"><Activity size={20}/></div><div><span>当前阶段 · {view.phase_label}</span><strong>{view.status==='finished'?'胜负已定':decision?'等待你的指令':'正在等待对手'}</strong></div></div><div className="instruction-card"><span className="instruction-rule"/>{view.instruction}</div><div className="action-toolbar"><span>当前可用行动</span><Badge>{filteredActions.length} 项</Badge></div>
                {chosenCoin&&<div className="filter-chip">棋币筛选：{chosenCoin.label}<button aria-label="清除棋币筛选" onClick={()=>setSelectedCoin(null)}><X size={13}/></button></div>}
                <div className="action-list">{grouped.length?grouped.map(group=><div className="action-group" key={group.g}><h4>{groupLabels[group.g]||group.g}<span>{group.items.length}</span></h4>{group.items.map(action=>{const Icon=actionIcons[action.presentation_icon||'move']||Target;return <button key={action.id} disabled={preview||busy||!decision||view.status!=='active'} aria-pressed={selectedActionId===action.id} className={`action-option ${selectedActionId===action.id?'chosen':''}`} onClick={()=>setSelectedActionId(action.id)}><span className="action-emblem"><Icon size={17}/></span><span className="action-copy"><strong>{action.label}</strong><small>{action.description}</small></span>{selectedActionId===action.id?<Check size={17} className="option-check"/>:<ArrowRight size={15} className="action-chevron"/>}</button>})}</div>):<p className="empty-state">当前没有可用行动，或正在等待其他玩家。</p>}</div>
                <div className="action-footer">{selectedAction&&<div className="submit-context"><span>将提交</span><strong>{selectedAction.confirm_text||selectedAction.label}</strong></div>}<button className="submit-action" disabled={preview||busy||!selectedAction||!decision||view.status!=='active'} onClick={()=>void submit()}>{busy?<RefreshCcw size={18} className="rotating"/>:<Play size={17} fill="currentColor"/>}{busy?'正在执行…':preview?'展示模式不可操作':!decision?'等待对方行动':selectedAction?'执行行动':'请先选择一项行动'}</button><p><LockKeyhole size={12}/> 选择行动后确认执行</p></div>
              </>:panel==='log'?<div className="decision-secondary"><div className="secondary-intro"><History size={21}/><h3>公开行动记录</h3><p>只展示服务端允许当前玩家查看的事件。</p></div><GameLog events={view.events}/></div>:<div className="decision-secondary"><div className="secondary-intro"><Layers size={21}/><h3>军团情报</h3><p>资源和兵种清单由后端生成。</p></div>{view.players.map(p=><div className="supply-section" key={p.id}><h4>{p.name}</h4><PlayerSupply player={p}/></div>)}</div>}
            </aside>
          </section>
          <div className="bottom-status">
            <div><span className="status-light"/> WAR CHEST <span className="bottom-separator">·</span> 游戏状态 v{view.revision}</div>
            {view.status==='finished'&&<a className="replay-link" href={`/api/v1/games/${encodeURIComponent(view.game_id)}/replay`} download="war-chest-replay.json">下载完整回放</a>}
            <div>{view.status==='finished'?`获胜方：${view.winner_team_id==='north'?'北境':view.winner_team_id==='south'?'南境':view.players.find(p=>p.id===view.winner_player_id)?.name||'待定'}`:`当前决策方：${view.players.find(p=>p.id===view.decision_player_id)?.name||'自动结算'}`}</div>
          </div>
        </>}
      </main>
    </div>
    {showHelp&&<div className="modal-shade" role="presentation" onClick={()=>setShowHelp(false)}><div className="help-modal" role="dialog" aria-modal="true" aria-label="使用说明" onClick={e=>e.stopPropagation()}><button className="modal-close" onClick={()=>setShowHelp(false)}><X size={20}/></button><span className="overline">HOW TO PLAY</span><h2>如何进行对局</h2><p>每轮抽取棋币后，依次使用手牌。点击一枚手牌或棋盘格，可以筛选相关行动。选定行动后，点击「执行行动」。</p><p>部署与增援会把棋币留在棋盘；移动、攻击、控制和战术需要弃置对应棋币。优先完成据点控制目标的一方获胜。特殊能力触发时，按当前阶段的提示继续选择。</p><div className="help-api">双人：控制 6 个据点<br/>四人：同队合计控制 8 个据点</div><button className="help-ok" onClick={()=>setShowHelp(false)}>明白了</button></div></div>}
  </div>;
}
