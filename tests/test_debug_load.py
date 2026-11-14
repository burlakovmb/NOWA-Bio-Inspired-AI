#!/usr/bin/env python3
"""Detailed debugging - check what happens in sleep_manager during load"""

import sys
sys.path.insert(0, 'src')

from agent import Agent
from hippocampus import NOWAHippocampus
from sleep import CortexMemory, SleepManager
from selector import ActionSelector
from intent_memory import IntentMemory
from storage import AgentStorage
from affect import AffectiveState
from temporal import TemporalLevels
print("=" * 70)
print("DETAILED DEBUG: What's in sleep_manager after load?")
print("=" * 70)

# ==== CREATE AND SAVE ====
print("\n[SAVE PHASE]")
hip = NOWAHippocampus()
cortex = CortexMemory()
intent_mem = IntentMemory()
sleep_mgr = SleepManager(hip, cortex, intent_mem)
selector = ActionSelector(actions=['respond', 'ask', 'clarify'])
affect_state = AffectiveState()
temporal = TemporalLevels()
agent = Agent(hip, cortex, selector, sleep_mgr, intent_mem)
storage = AgentStorage()

print("1. Creating experiences...")
for msg in ["привет", "как дела"]:
    agent.step([f"user:{msg}"])

print("2. Sleep to form chains...")
sleep_mgr.sleep_cycle()
sleep_mgr.sleep_cycle()

print(f"3. sleep_mgr.chain_memory id: {id(sleep_mgr.chain_memory)}")
print(f"   sleep_mgr.chain_memory.chains: {len(sleep_mgr.chain_memory.chains)}")

print("4. Saving...")
save_path = storage.save_agent(hip, cortex, selector, affect_state=affect_state, temporal=temporal, sleep_manager=sleep_mgr, filename="debug.pkl", agent=agent)

# Check what was saved
from storage import read_agent_state
saved = read_agent_state(save_path)
    
print(f"5. Saved data contains:")
print(f"   'sleep_manager': {'sleep_manager' in saved}")
if 'sleep_manager' in saved:
    sm_data = saved['sleep_manager']
    print(f"   'chain_memory' in sleep_manager: {'chain_memory' in sm_data}")
    if 'chain_memory' in sm_data:
        cm_data = sm_data['chain_memory']
        print(f"   chains count in save: {len(cm_data.get('chains', {}))}")

# ==== FRESH AGENT AND LOAD ====
print("\n[LOAD PHASE]")
print("1. Creating fresh sleep_manager...")
hip2 = NOWAHippocampus()
cortex2 = CortexMemory()
intent_mem2 = IntentMemory()
sleep_mgr2 = SleepManager(hip2, cortex2, intent_mem2)
selector2 = ActionSelector(actions=['respond', 'ask', 'clarify'])
affect_state2 = AffectiveState()
temporal2 = TemporalLevels()
agent2 = Agent(hip2, cortex2, selector2, sleep_mgr2, intent_mem2)

print(f"2. BEFORE load - sleep_mgr2.chain_memory id: {id(sleep_mgr2.chain_memory)}")
print(f"   BEFORE load - sleep_mgr2.chain_memory.chains: {len(sleep_mgr2.chain_memory.chains)}")

print("3. Loading...")
storage.load_agent(hip2, cortex2, selector2, save_path, affect_state=affect_state2, temporal=temporal2, sleep_manager=sleep_mgr2, agent=agent2)

print(f"4. AFTER load - sleep_mgr2.chain_memory id: {id(sleep_mgr2.chain_memory)}")
print(f"   AFTER load - sleep_mgr2.chain_memory.chains: {len(sleep_mgr2.chain_memory.chains)}")

print(f"5. Statistics:")
stats = sleep_mgr2.chain_memory.statistics()
print(f"   {stats}")

print(f"6. Chain details:")
for i, (sig, chain) in enumerate(list(sleep_mgr2.chain_memory.chains.items())[:3]):
    print(f"   Chain {i+1}: {sig}")

# ==== CLEANUP ====
import os
os.remove(save_path)

print("\n" + "=" * 70)
if len(sleep_mgr2.chain_memory.chains) > 0:
    print("✅ CHAINS LOADED CORRECTLY")
else:
    print("❌ CHAINS NOT LOADED")
print("=" * 70)
