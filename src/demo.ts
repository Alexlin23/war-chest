import type { GameView, HexView, PlayerView, ActionView, HandCoinView } from './types';

/** Static screenshot fixture ONLY. It does NOT implement or claim official game rules.
 * There are no executable demo actions, and it is never used as fallback after API failure.
 */
const key=(q:number,r:number)=>`${q},${r}`;
const points: Record<string, string|null> = {
  [key(-1,-2)]:'north', [key(2,-3)]:'north',
  [key(-2,3)]:'south',[key(1,2)]:'south',
  [key(-1,1)]:null,[key(1,-1)]:null,[key(-2,0)]:null,
  [key(2,0)]:null,[key(-3,2)]:null,[key(3,-2)]:null,
};
const units: Record<string,HexView['unit']> = {
  [key(-1,-1)]:{unit_type:'archer',name:'弓箭手',short_name:'弓',owner_id:'north',count:1,symbol:'↗'},
  [key(1,-2)]:{unit_type:'crossbowman',name:'弩手',short_name:'弩',owner_id:'north',count:2,symbol:'✢'},
  [key(0,0)]:{unit_type:'cavalry',name:'骑兵',short_name:'骑',owner_id:'south',count:2,symbol:'♞'},
  [key(-1,2)]:{unit_type:'swordsman',name:'剑士',short_name:'剑',owner_id:'south',count:1,symbol:'⚔'},
  [key(2,1)]:{unit_type:'footman',name:'步兵',short_name:'步',owner_id:'south',count:1,symbol:'♟'},
};
const board:HexView[]=[];
for(let r=-3;r<=3;r++) for(let q=-3;q<=3;q++) if(Math.abs(q+r)<=3){
  const k=key(q,r);
  board.push({id:k,q,r,terrain:Object.prototype.hasOwnProperty.call(points,k)?'objective':'normal',
    owner_id:Object.prototype.hasOwnProperty.call(points,k)?points[k]:null,unit:units[k]||null,
    decoration:q===3&&r===-1?'pines':q===-3&&r===1?'rubble':null});
}
const players:PlayerView[]=[
  {id:'north',side:'north',name:'北境守军',color_name:'曜石',control_count:2,control_target:6,bag_count:4,discard_count:3,supply_count:8,hand_count:2,board_unit_count:2,is_viewer:false,
    army:[{unit_type:'archer',name:'弓箭手',short_name:'弓',available:2},{unit_type:'crossbowman',name:'弩手',short_name:'弩',available:1},{unit_type:'pikeman',name:'长枪兵',short_name:'枪',available:2},{unit_type:'knight',name:'骑士',short_name:'骑',available:3}]},
  {id:'south',side:'south',name:'南境军团',color_name:'赤铜',control_count:3,control_target:6,bag_count:3,discard_count:2,supply_count:9,hand_count:3,board_unit_count:3,is_viewer:true,
    army:[{unit_type:'cavalry',name:'骑兵',short_name:'骑',available:2},{unit_type:'swordsman',name:'剑士',short_name:'剑',available:3},{unit_type:'footman',name:'步兵',short_name:'步',available:2},{unit_type:'scout',name:'侦察兵',short_name:'侦',available:2}]},
];
const hand:HandCoinView[]=[
  {id:'coin-1',unit_type:'cavalry',label:'骑兵',short_name:'骑',symbol:'♞',is_royal:false},
  {id:'coin-2',unit_type:'swordsman',label:'剑士',short_name:'剑',symbol:'⚔',is_royal:false},
  {id:'coin-3',unit_type:'royal',label:'皇家币',short_name:'王',symbol:'♛',is_royal:true},
];
// This list is PREVIEW COPY only. Buttons remain disabled in static preview mode.
const actions:ActionView[]=[
  {id:'preview-01',group:'maneuver',label:'骑兵 · 移动',description:'选择已显示的棋盘位置',payment_coin_type:'cavalry',source_hex_id:'0,0',target_hex_ids:['0,-1','-1,0'],presentation_icon:'move'},
  {id:'preview-02',group:'special',label:'骑兵 · 发动战术',description:'移动后执行连续步骤',payment_coin_type:'cavalry',source_hex_id:'0,0',presentation_icon:'tactic'},
  {id:'preview-03',group:'maneuver',label:'剑士 · 攻击',description:'从当前单位发起攻击',payment_coin_type:'swordsman',source_hex_id:'-1,2',presentation_icon:'attack'},
  {id:'preview-04',group:'recruit',label:'招募 · 步兵',description:'消耗皇家币，招募兵种币',payment_coin_type:'royal',presentation_icon:'recruit'},
  {id:'preview-05',group:'initiative',label:'夺取先手',description:'面朝下弃置一枚棋币',payment_coin_type:'royal',presentation_icon:'flag'},
];
export const previewView:GameView={schema_version:1,game_id:'展示视图',revision:12,ruleset_label:'双人基础版 · 静态展示',
  status:'active',winner_player_id:null,viewer_player_id:'south',decision_player_id:'south',initiative_player_id:'north',
  round:4,phase_label:'行动阶段',instruction:'选择一枚棋币，查看由后端提供的可执行行动',board,players,hand,legal_actions:actions,
  events:[
    {id:'e-1',time_label:'最近',text:'南境军团占领了中央据点',player_id:'south',type:'control'},
    {id:'e-2',time_label:'上一行动',text:'北境守军增援了弩手',player_id:'north',type:'move'},
    {id:'e-3',time_label:'本轮',text:'北境守军持有先手标记',player_id:'north',type:'info'},
  ]};
