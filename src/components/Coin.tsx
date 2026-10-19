import type { HandCoinView } from '../types';
export function Coin({coin,selected,onClick,disabled=false}: {coin:HandCoinView,selected:boolean,onClick:()=>void,disabled?:boolean}){
  return <button type="button" title={coin.label} aria-pressed={selected} aria-label={`选择手牌 ${coin.label}`} className={`hand-coin ${coin.is_royal?'royal':''} ${selected?'picked':''}`} onClick={onClick} disabled={disabled}>
    <span className="hand-coin-inner"><span className="coin-sigil">{coin.symbol||coin.short_name}</span><span className="coin-name">{coin.label}</span></span>
  </button>;
}
