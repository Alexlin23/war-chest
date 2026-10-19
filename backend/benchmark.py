"""Reproducible CPU benchmark; excludes HTTP, database, model and browser costs."""
import argparse
import json
import platform
import random
from statistics import median
from time import perf_counter_ns
from .engine import clone, legal_actions, _apply_legal_action
from .env import WarChestEnv, observation, packed_observation


def run(steps=100000,repeats=3,players=2,observation_format='none'):
    measurements=[]
    completed=[]
    positions=[]
    for repeat in range(repeats):
        picker=random.Random(70)
        env=WarChestEnv(70,setup='random',player_count=players)
        wins=0
        start=perf_counter_ns()
        for i in range(steps):
            if observation_format=='dict': codes=env.observe()['legal_action_codes']
            elif observation_format=='packed': codes=env.observe_packed().legal_action_codes
            else: codes=env.legal_action_codes()
            env.step(picker.choice(codes),expected_revision=env.revision)
            if env.done or (i+1)%1000==0:
                wins+=bool(env._game.winner)
                env.reset(70+i,setup='random',player_count=players)
        measurements.append((perf_counter_ns()-start)/1e9)
        completed.append(wins)
    env=WarChestEnv(70,setup='random',player_count=players)
    picker=random.Random(70)
    for i in range(300):
        codes=env.legal_action_codes()
        if i%10==0: positions.append(clone(env._game))
        env.step(picker.choice(codes),expected_revision=env.revision)
        if env.done: env.reset(70+i,setup='random',player_count=players)
    components={}
    for name,fn in [('legal_actions',legal_actions),('clone',clone),
                    ('packed_observation',lambda g:packed_observation(g,g.decision)),
                    ('observation',lambda g:observation(g,g.decision))]:
        start=perf_counter_ns()
        for _ in range(200):
            for g in positions: fn(g)
        components[name+'_us']=(perf_counter_ns()-start)/len(positions)/200/1000
    samples=[]
    for g in positions:
        a=legal_actions(g)[0]
        for _ in range(100):
            h=clone(g)
            start=perf_counter_ns()
            _apply_legal_action(h,a)
            samples.append(perf_counter_ns()-start)
    components['apply_legal_action_us']=sum(samples)/len(samples)/1000
    return {'python':platform.python_version(),'platform':platform.platform(),
        'processor':platform.processor(),'players':players,'observation_format':observation_format,'steps_per_repeat':steps,
        'repeats':repeats,'seconds':measurements,
        'median_steps_per_second':steps/median(measurements),
        'natural_wins_per_repeat':completed,'components':components,
        'notes':'Single process; candidate encoding+validation included; observation mode is explicit; no trace/invariant checks per step; reset every 1000 steps or win.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--steps',type=int,default=100000)
    parser.add_argument('--repeats',type=int,default=3)
    parser.add_argument('--players',type=int,choices=(2,4),default=2)
    parser.add_argument('--observation',choices=('none','dict','packed'),default='none')
    args=parser.parse_args()
    print(json.dumps(run(args.steps,args.repeats,args.players,args.observation),indent=2))
