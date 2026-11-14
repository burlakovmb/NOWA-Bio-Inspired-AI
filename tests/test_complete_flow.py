#!/usr/bin/env python3
"""Test the complete save/load flow like the GUI does"""

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
import os

print("=" * 70)
print("TESTING COMPLETE GUI-LIKE FLOW: SAVE → LOAD → CHECK CHAINS")
print("=" * 70)

# ==== STEP 1: Create agent like GUI does ====
print("\n[1] Creating agent (like GUI initialization)...")
hip = NOWAHippocampus()
cortex = CortexMemory()
intent_mem = IntentMemory()
sleep_mgr = SleepManager(hip, cortex, intent_mem)
selector = ActionSelector(actions=['respond', 'ask', 'clarify'])
affect_state = AffectiveState()
temporal = TemporalLevels()
agent = Agent(hip, cortex, selector, sleep_mgr, intent_mem)
agent.affect_state = affect_state
agent.temporal = temporal
storage = AgentStorage()

# ==== STEP 2: Create experiences ====
print("\n[2] Creating experiences...")
for i, msg in enumerate(["привет", "как дела", "расскажи"], 1):
    context = [f"user:{msg}"]
    agent.step(context)
    print(f"   {i}. {msg}")

print(f"   Total experiences: {len(hip.experiences)}")

# ==== STEP 3: Sleep to form chains ====
print("\n[3] Sleeping to form chains...")
for cycle in range(2):
    stats = sleep_mgr.sleep_cycle()
    print(f"   Cycle {cycle+1}: {stats['chains_formed']} chains")

chains_before = len(sleep_mgr.chain_memory.chains)
stats_before = sleep_mgr.chain_memory.statistics()
print(f"\n   BEFORE SAVE:")
print(f"     Total chains: {chains_before}")
print(f"     Avg stability: {stats_before['avg_stability']:.2f}")
print(f"     Chain details: {list(sleep_mgr.chain_memory.chains.keys())[:2]}...")

# ==== STEP 4: Save ====
print("\n[4] Saving agent...")
save_path = storage.save_agent(
    hip, cortex, selector,
    affect_state=affect_state,
    temporal=temporal,
    sleep_manager=sleep_mgr,
    agent=agent,
    filename="test_full_flow.pkl"
)
print(f"   Saved to: {save_path}")

# Check what's in the save file
from storage import read_agent_state
saved_data = read_agent_state(save_path)
    
print(f"   Save contains 'sleep_manager': {'sleep_manager' in saved_data}")
if 'sleep_manager' in saved_data:
    print(f"   Save contains 'chain_memory': {'chain_memory' in saved_data['sleep_manager']}")
    if 'chain_memory' in saved_data['sleep_manager']:
        cm = saved_data['sleep_manager']['chain_memory']
        print(f"   Saved chains count: {len(cm.get('chains', {}))}")

# ==== STEP 5: Create fresh agent (like starting new GUI) ====
print("\n[5] Creating fresh agent (new GUI session)...")
hip2 = NOWAHippocampus()
cortex2 = CortexMemory()
intent_mem2 = IntentMemory()
sleep_mgr2 = SleepManager(hip2, cortex2, intent_mem2)
selector2 = ActionSelector(actions=['respond', 'ask', 'clarify'])
affect_state2 = AffectiveState()
temporal2 = TemporalLevels()
agent2 = Agent(hip2, cortex2, selector2, sleep_mgr2, intent_mem2)

print(f"   Fresh agent chains: {len(sleep_mgr2.chain_memory.chains)}")

# ==== STEP 6: Load (like GUI does) ====
print("\n[6] Loading agent (like GUI load_selected())...")
timestamp = storage.load_agent(
    hip2, cortex2, selector2,
    save_path,
    affect_state=affect_state2,
    temporal=temporal2,
    sleep_manager=sleep_mgr2,
    agent=agent2
)
print(f"   Loaded timestamp: {timestamp}")

# ==== STEP 7: Check chains after load ====
print("\n[7] Checking chains AFTER LOAD...")
chains_after = len(sleep_mgr2.chain_memory.chains)
stats_after = sleep_mgr2.chain_memory.statistics()

print(f"   AFTER LOAD:")
print(f"     Total chains: {chains_after}")
print(f"     Avg stability: {stats_after['avg_stability']:.2f}")
print(f"     Chain details: {list(sleep_mgr2.chain_memory.chains.keys())[:2]}...")

# ==== STEP 8: Verify ====
print("\n[8] VERIFICATION:")
if chains_before == 0:
    print(f"   ❌ NO CHAINS WERE CREATED! Check step 3")
elif chains_after == 0:
    print(f"   ❌ CHAINS LOST AFTER LOAD!")
    print(f"      Before: {chains_before}")
    print(f"      After: {chains_after}")
else:
    if chains_before == chains_after:
        print(f"   ✅ Chains restored correctly: {chains_after}")
    else:
        print(f"   ⚠️  Chain count changed: {chains_before} → {chains_after}")

# Cleanup
print("\n[9] Cleanup...")
os.remove(save_path)
print(f"   Removed: {save_path}")

print("\n" + "=" * 70)
if chains_after > 0:
    print("✅ COMPLETE FLOW WORKS!")
else:
    print("❌ SOMETHING IS BROKEN IN THE FLOW")
print("=" * 70)
