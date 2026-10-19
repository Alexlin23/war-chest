import { useMemo } from 'react';
import type { HexView, ActionView } from '../types';

const R = 46;
const HW = Math.sqrt(3)*R;
const polygon = Array.from({length:6},(_,i)=>{
  const a=(Math.PI/180)*(60*i-30);
  return `${(Math.cos(a)*R).toFixed(2)},${(Math.sin(a)*R).toFixed(2)}`;
}).join(' ');
function xy(h:HexView){return {x:HW*(h.q+h.r/2),y:1.5*R*h.r};}

type Props={
  board:HexView[];selectedHexId:string|null;onSelectHex:(id:string)=>void;
  selectedAction:ActionView|null; viewerId:string;viewerTeamId?:string;
};
export function HexBoard({board,selectedHexId,onSelectHex,selectedAction,viewerId,viewerTeamId}:Props){
  const {ordered,viewBox}=useMemo(()=>{
    const positions=board.map(h=>({...h,...xy(h)}));
    const xs=positions.map(h=>h.x), ys=positions.map(h=>h.y);
    const minX=Math.min(...xs,-100)-R-18,maxX=Math.max(...xs,100)+R+18;
    const minY=Math.min(...ys,-100)-R-28,maxY=Math.max(...ys,100)+R+28;
    return {ordered:positions,viewBox:`${minX} ${minY} ${maxX-minX} ${maxY-minY}`};
  },[board]);
  const targets=new Set(selectedAction?.target_hex_ids||[]);
  const highlights=new Set(selectedAction?.highlight_hex_ids||[]);
  return <div className="hex-board-shell">
    <div className="map-seal map-seal--one">N</div><div className="map-seal map-seal--two">S</div>
    <svg className="hex-board" viewBox={viewBox} preserveAspectRatio="xMidYMid meet" role="group" aria-label="游戏棋盘。选择六角格查看棋子，合法行动由服务器提供">
      <defs>
        <filter id="tokenShadow" x="-30%" y="-40%" width="160%" height="190%"><feDropShadow dx="0" dy="3" stdDeviation="3" floodColor="#18251b" floodOpacity="0.35"/></filter>
        <pattern id="tileHatch" width="9" height="9" patternUnits="userSpaceOnUse"><path d="M0 9 L9 0" stroke="#85775d" strokeOpacity=".09" strokeWidth="1"/></pattern>
      </defs>
      {ordered.map(cell=>{
        const selected=cell.id===selectedHexId;
        const isSource=cell.id===selectedAction?.source_hex_id;
        const target=targets.has(cell.id),highlight=highlights.has(cell.id);
        const ownerClass=cell.owner_id===(viewerTeamId||viewerId)?'south':cell.owner_id?'north':'neutral';
        const unit=cell.unit;
        const unitStyle=(unit?.team_id||unit?.owner_id)===(viewerTeamId||viewerId)?'friendly':'enemy';
        return <g key={cell.id} transform={`translate(${cell.x} ${cell.y})`} className="hex-cell" onClick={()=>onSelectHex(cell.id)} role="button" aria-label={`格 ${cell.id}${unit?' '+unit.name+' '+unit.count+'枚':''}`} tabIndex={0} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();onSelectHex(cell.id);}}}>
          <polygon points={polygon} className={`hex-ground ${cell.terrain==='blocked'?'blocked':''} ${selected?'selected':''} ${target?'target':''} ${isSource?'source':''}`}/>
          <polygon points={polygon} fill="url(#tileHatch)" pointerEvents="none" opacity=".7"/>
          {cell.terrain==='objective'&& <>
            <circle r="30" className={`objective-ring ${ownerClass}`}/>
            <circle r="22" className={`objective-middle ${ownerClass}`}/>
            <path d="M-12 0 L0 -13 L12 0 L0 13 Z" className={`objective-core ${ownerClass}`}/>
            <circle r="3.2" fill="#f3e6bf"/>
          </>}
          {cell.terrain==='blocked'&&<path d="M-18 -18L18 18M18 -18L-18 18" stroke="#726451" strokeWidth="4" opacity=".55"/>}
          {selected&&<polygon points={polygon} className="hex-selection" pointerEvents="none"/>}
          {(target||highlight)&&<circle r="34" className="hex-target" pointerEvents="none"/>}
          {unit&&<g filter="url(#tokenShadow)">
            <circle r="28.5" className={`unit-coin ${unitStyle}`}/>
            <circle r="24" className={`unit-coin-inset ${unitStyle}`}/>
            <circle r="19.5" fill="none" stroke="#e9d29f" strokeOpacity=".38" strokeWidth=".85"/>
            <text y="7.5" textAnchor="middle" className="unit-symbol" aria-hidden="true">{unit.symbol || unit.short_name}</text>
            {unit.count>1&&<g transform="translate(25 -23)"><circle r="11.5" fill="#eadfc4" stroke="#514833" strokeWidth="2"/><text y="4.5" textAnchor="middle" fontSize="12" fontWeight="800" fill="#39382d">{unit.count}</text></g>}
          </g>}
          {isSource&&<circle r="37" fill="none" stroke="#f7d585" strokeWidth="2" strokeDasharray="4 4" pointerEvents="none"/>}
        </g>;
      })}
    </svg>
    <div className="map-compass" aria-hidden="true"><div className="compass-top">✦</div><span>N</span><div className="compass-stem"/></div>
    <div className="board-watermark" aria-hidden="true">CHRONICLE · 01</div>
  </div>;
}
