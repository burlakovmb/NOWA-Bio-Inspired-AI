"""
Test suite for Neuromodulator Phase 2 implementation.

Covers all 5 mandatory test cases from specification:
- TC-1: Positive reinforcement
- TC-2: Negative + conflict
- TC-3: Novelty
- TC-4: Time decay
- TC-5: Sleep + high dopamine
"""

import sys
import time
import unittest
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from neuromodulators import NeuromodulatorState


class TestNeuromodulatorsPhase2(unittest.TestCase):
    """Test suite for Phase 2 neuromodulator implementation."""

    def setUp(self):
        """Set up fresh neuromodulator state for each test."""
        self.nm = NeuromodulatorState()
        self.initial_state = self.nm.snapshot()

    def test_initialization(self):
        """Test default initialization with correct baselines."""
        self.assertAlmostEqual(self.nm.dopamine, 0.1)
        self.assertAlmostEqual(self.nm.norepinephrine, 0.1)
        self.assertAlmostEqual(self.nm.serotonin, 0.1)
        self.assertAlmostEqual(self.nm.cortisol, 0.05)

    def test_clamping(self):
        """Test that values are clamped to [0.0, 1.0]."""
        nm = NeuromodulatorState(dopamine=2.0, serotonin=-0.5)
        self.assertEqual(nm.dopamine, 1.0)
        self.assertEqual(nm.serotonin, 0.0)

    # ========== TC-1: Positive Reinforcement ==========
    def test_tc1_positive_reinforcement(self):
        """
        TC-1: Positive reinforcement
        - reward = +1.0
        - expected: DA ↑, HT ↑ (weakly)
        """
        print("\n=== TC-1: Positive Reinforcement ===")
        initial_da = self.nm.dopamine
        initial_ht = self.nm.serotonin
        
        # Apply positive reward
        self.nm.update_from_signals(reward=1.0, novelty=0, conflict=0)
        
        print(f"Initial DA: {initial_da:.3f}, Final DA: {self.nm.dopamine:.3f}")
        print(f"Initial HT: {initial_ht:.3f}, Final HT: {self.nm.serotonin:.3f}")
        
        # Dopamine should increase significantly
        # DA += 0.25 * reward (when reward > 0)
        self.assertGreater(self.nm.dopamine, initial_da, "Dopamine should increase with positive reward")
        expected_da = min(1.0, initial_da + 0.25 * 1.0)
        self.assertAlmostEqual(self.nm.dopamine, expected_da, places=5)
        
        # Serotonin should increase weakly
        # HT += 0.05 * reward (when reward > 0 and conflict == 0)
        self.assertGreater(self.nm.serotonin, initial_ht, "Serotonin should increase weakly with positive reward")
        expected_ht = min(1.0, initial_ht + 0.05 * 1.0)
        self.assertAlmostEqual(self.nm.serotonin, expected_ht, places=5)
        
        print("✓ TC-1 PASSED: DA and HT increased correctly\n")

    # ========== TC-2: Negative + Conflict ==========
    def test_tc2_negative_and_conflict(self):
        """
        TC-2: Negative outcome + conflict
        - reward = -0.8, conflict = 0.6
        - expected: CORT ↑↑, DA ↓
        """
        print("\n=== TC-2: Negative + Conflict ===")
        initial_da = self.nm.dopamine
        initial_cort = self.nm.cortisol
        target_effective_conflict = self.nm._compute_effective_conflict(0.6)
        alpha = self.nm._compute_conflict_alpha(1.0)
        effective_conflict = alpha * target_effective_conflict
        
        # Apply negative reward with conflict
        self.nm.update_from_signals(reward=-0.8, novelty=0, conflict=0.6)
        
        print(f"Initial DA: {initial_da:.3f}, Final DA: {self.nm.dopamine:.3f}")
        print(f"Initial CORT: {initial_cort:.3f}, Final CORT: {self.nm.cortisol:.3f}")
        
        # Dopamine should decrease
        # DA += -0.10 * abs(reward) (when reward < 0)
        self.assertLess(self.nm.dopamine, initial_da, "Dopamine should decrease with negative reward")
        expected_da = max(0.0, initial_da - 0.10 * abs(-0.8))
        self.assertAlmostEqual(self.nm.dopamine, expected_da, places=5)
        
        # One-second map (dt defaults to 1): clearance 0.4 toward baseline,
        # then the full legacy dose 0.20*|reward| + 0.25*effective_conflict.
        self.assertGreater(self.nm.cortisol, initial_cort, "Cortisol should increase with negative reward and conflict")
        expected_cort = initial_cort
        expected_cort += self.nm.ACC_CORT_HOMEOSTATIC_DECAY * (self.nm.BASELINE_CORT - initial_cort)
        expected_cort += 0.20 * abs(-0.8)
        expected_cort += 0.25 * effective_conflict
        expected_cort = min(1.0, expected_cort)
        self.assertAlmostEqual(self.nm.cortisol, expected_cort, places=5)
        
        print("✓ TC-2 PASSED: CORT increased, DA decreased\n")

    # ========== TC-3: Novelty ==========
    def test_tc3_novelty(self):
        """
        TC-3: High novelty signal
        - novelty = 1.0
        - expected: NE ↑, exploration ↑
        """
        print("\n=== TC-3: Novelty ===")
        initial_ne = self.nm.norepinephrine
        initial_exploration = self.nm.get_exploration_level()
        
        # Apply novelty signal
        self.nm.update_from_signals(reward=0, novelty=1.0, conflict=0)
        
        print(f"Initial NE: {initial_ne:.3f}, Final NE: {self.nm.norepinephrine:.3f}")
        print(f"Initial exploration: {initial_exploration:.3f}, Final: {self.nm.get_exploration_level():.3f}")
        
        # Norepinephrine should increase significantly
        # NE += 0.30 * novelty
        self.assertGreater(self.nm.norepinephrine, initial_ne, "NE should increase with novelty")
        expected_ne = min(1.0, initial_ne + 0.30 * 1.0)
        self.assertAlmostEqual(self.nm.norepinephrine, expected_ne, places=5)
        
        # Exploration should increase
        exploration = self.nm.get_exploration_level()
        self.assertGreater(exploration, initial_exploration, "Exploration level should increase with high NE")
        
        print("✓ TC-3 PASSED: NE and exploration increased\n")

    # ========== TC-4: Time Decay ==========
    def test_tc4_time_decay(self):
        """
        TC-4: Temporal decay
        - After 120 seconds without signals
        - expected: all → baseline
        """
        print("\n=== TC-4: Time Decay ===")
        
        # Set all to high values
        self.nm.dopamine = 0.9
        self.nm.norepinephrine = 0.8
        self.nm.serotonin = 0.7
        self.nm.cortisol = 0.6
        
        print(f"Before decay (2 min):")
        print(f"  DA: {self.nm.dopamine:.3f}, NE: {self.nm.norepinephrine:.3f}")
        print(f"  HT: {self.nm.serotonin:.3f}, CORT: {self.nm.cortisol:.3f}")
        
        # Apply 120 seconds decay
        self.nm.decay_over_time(120.0)
        
        print(f"After 120s decay:")
        print(f"  DA: {self.nm.dopamine:.3f}, NE: {self.nm.norepinephrine:.3f}")
        print(f"  HT: {self.nm.serotonin:.3f}, CORT: {self.nm.cortisol:.3f}")
        
        print(f"Expected baselines:")
        print(f"  DA: {NeuromodulatorState.BASELINE_DA:.3f}")
        print(f"  NE: {NeuromodulatorState.BASELINE_NE:.3f}")
        print(f"  HT: {NeuromodulatorState.BASELINE_HT:.3f}")
        print(f"  CORT: {NeuromodulatorState.BASELINE_CORT:.3f}")
        
        # After 120 seconds (half-life is 90s):
        # decay_factor = 0.5^(120/90) ≈ 0.3175
        # X = baseline + (initial - baseline) * decay_factor
        # So DA = 0.1 + (0.9 - 0.1) * 0.3175 ≈ 0.354
        # Tolerance: should decay significantly toward baseline
        self.assertLess(abs(self.nm.dopamine - NeuromodulatorState.BASELINE_DA), 0.4)
        self.assertLess(abs(self.nm.norepinephrine - NeuromodulatorState.BASELINE_NE), 0.4)
        self.assertLess(abs(self.nm.serotonin - NeuromodulatorState.BASELINE_HT), 0.4)
        self.assertLess(abs(self.nm.cortisol - NeuromodulatorState.BASELINE_CORT), 0.3)
        
        print("✓ TC-4 PASSED: All values decayed toward baseline\n")

    def test_tc4_decay_half_life(self):
        """Test that decay half-life is approximately correct (90 seconds)."""
        print("\n=== TC-4b: Decay Half-Life Verification ===")
        
        # Set to double baseline
        initial_da = 0.3  # Twice baseline (0.1)
        self.nm.dopamine = initial_da
        
        # Decay for half-life duration
        self.nm.decay_over_time(NeuromodulatorState.DECAY_HALF_LIFE)
        
        print(f"Initial: {initial_da:.3f}")
        print(f"After half-life ({NeuromodulatorState.DECAY_HALF_LIFE}s): {self.nm.dopamine:.3f}")
        
        # After one half-life, should be at ~50% of initial difference from baseline
        # DA = baseline + (initial - baseline) * 0.5
        # = 0.1 + (0.3 - 0.1) * 0.5 = 0.1 + 0.1 = 0.2
        expected = 0.1 + (initial_da - 0.1) * 0.5
        self.assertAlmostEqual(self.nm.dopamine, expected, places=2)
        
        print(f"Expected: {expected:.3f}")
        print("✓ Half-life decay formula verified\n")

    # ========== TC-5: Sleep + High Dopamine ==========
    def test_tc5_sleep_consolidation_enhancement(self):
        """
        TC-5: Sleep consolidation with high dopamine
        - High DA signal (e.g., DA=0.7)
        - expected: consolidation strength should be enhanced
        """
        print("\n=== TC-5: Sleep + High Dopamine ===")
        
        # Simulate achieving high dopamine (reward signal)
        self.nm.dopamine = 0.7
        self.nm.serotonin = 0.15  # Slight stability
        
        # Get consolidation metrics
        consolidation_strength = self.nm.get_consolidation_strength()
        learning_rate = self.nm.get_learning_rate_modifier()
        forgetting_rate = self.nm.get_forgetting_rate()
        
        print(f"High DA state:")
        print(f"  DA: {self.nm.dopamine:.3f}")
        print(f"  Consolidation strength: {consolidation_strength:.3f}")
        print(f"  Learning rate modifier: {learning_rate:.3f}")
        print(f"  Forgetting rate: {forgetting_rate:.3f}")
        
        # Reset to baseline and compare
        self.nm.dopamine = 0.1
        self.nm.serotonin = 0.1
        
        consolidation_baseline = self.nm.get_consolidation_strength()
        learning_baseline = self.nm.get_learning_rate_modifier()
        forgetting_baseline = self.nm.get_forgetting_rate()
        
        print(f"\nBaseline state:")
        print(f"  DA: {self.nm.dopamine:.3f}")
        print(f"  Consolidation strength: {consolidation_baseline:.3f}")
        print(f"  Learning rate modifier: {learning_baseline:.3f}")
        print(f"  Forgetting rate: {forgetting_baseline:.3f}")
        
        # High DA should enhance consolidation
        self.assertGreater(consolidation_strength, consolidation_baseline,
                          "High dopamine should enhance consolidation strength during sleep")
        
        # High DA should increase learning rate
        self.assertGreater(learning_rate, learning_baseline,
                          "High dopamine should increase learning rate")
        
        # High DA should reduce forgetting (strengthen traces)
        self.assertLess(forgetting_rate, forgetting_baseline,
                       "High dopamine should reduce forgetting rate of strong patterns")
        
        print("✓ TC-5 PASSED: Consolidation enhanced with high DA\n")

    # ========== Integration Tests ==========
    def test_complex_scenario_high_stress(self):
        """
        Integration test: High stress scenario
        - Multiple negative rewards
        - High conflict
        - Should show appropriate neuromodulator response
        """
        print("\n=== Integration: High Stress Scenario ===")
        
        # Simulate repeated failures with conflict
        for i in range(3):
            self.nm.update_from_signals(reward=-0.7, novelty=0.1, conflict=0.8)
            print(f"Step {i+1}: DA={self.nm.dopamine:.3f}, CORT={self.nm.cortisol:.3f}, "
                  f"NE={self.nm.norepinephrine:.3f}, HT={self.nm.serotonin:.3f}")
        
        # Should show high cortisol and low dopamine
        self.assertGreater(self.nm.cortisol, 0.3, "High stress should elevate cortisol")
        self.assertLess(self.nm.dopamine, 0.2, "Repeated failures should lower dopamine")
        
        print("✓ High stress scenario handled correctly\n")

    def test_modifiers_consistency(self):
        """
        Test that all modifier methods return consistent values.
        """
        print("\n=== Modifier Consistency Test ===")
        
        # Get all modifiers
        mods = {
            'learning_rate': self.nm.get_learning_rate_modifier(),
            'consolidation_strength': self.nm.get_consolidation_strength(),
            'temporal_discount': self.nm.get_temporal_discount(),
            'exploration': self.nm.get_exploration_level(),
            'chain_generation': self.nm.get_temporal_chain_generation(),
            'forgetting_rate': self.nm.get_forgetting_rate(),
            'consolidation_threshold': self.nm.get_consolidation_threshold(),
            'arousal_modifier': self.nm.get_affective_arousal_modifier(),
        }
        
        print("Modifier values:")
        for name, value in mods.items():
            print(f"  {name}: {value:.3f}")
            # All should be numeric and finite
            self.assertIsInstance(value, float)
            self.assertTrue(-1e6 < value < 1e6, f"{name} should be finite")
        
        print("✓ All modifiers returned valid values\n")

    def test_no_extreme_jumps(self):
        """
        Test specification requirement: no jumps > 0.3 per step
        """
        print("\n=== No Extreme Jumps Test ===")
        
        # Single extreme update
        initial = self.nm.dopamine
        self.nm.update_from_signals(reward=1.0, novelty=1.0, conflict=1.0)
        
        change = abs(self.nm.dopamine - initial)
        print(f"Max single dopamine change: {change:.3f}")
        
        # Should not jump more than ~0.3
        self.assertLess(change, 0.3, "Single update should not exceed 0.3 change")
        
        print("✓ No extreme jumps detected\n")

    def test_serialization(self):
        """Test to_dict and from_dict methods."""
        print("\n=== Serialization Test ===")
        
        # Modify state
        self.nm.dopamine = 0.5
        self.nm.serotonin = 0.3
        
        # Serialize
        data = self.nm.to_dict()
        print(f"Serialized: {data}")
        
        # Deserialize
        nm2 = NeuromodulatorState.from_dict(data)
        
        self.assertAlmostEqual(nm2.dopamine, 0.5)
        self.assertAlmostEqual(nm2.serotonin, 0.3)
        
        print("✓ Serialization working correctly\n")

    def test_reset(self):
        """Test reset to baseline."""
        print("\n=== Reset Test ===")
        
        # Modify all values
        self.nm.dopamine = 0.8
        self.nm.norepinephrine = 0.7
        self.nm.serotonin = 0.6
        self.nm.cortisol = 0.5
        
        # Reset
        self.nm.reset()
        
        self.assertAlmostEqual(self.nm.dopamine, 0.1)
        self.assertAlmostEqual(self.nm.norepinephrine, 0.1)
        self.assertAlmostEqual(self.nm.serotonin, 0.1)
        self.assertAlmostEqual(self.nm.cortisol, 0.05)
        
        print("✓ Reset to baseline working\n")


    def test_cortisol_one_second_matches_two_half_seconds(self):
        """Constant secretion: one step of 1 s equals two steps of 0.5 s."""
        reward = -0.8

        def fresh():
            return NeuromodulatorState()

        full = fresh()
        full.update_from_signals(
            reward=reward, novelty=0.0, conflict=0.0, dt=1.0, use_reward_for_dopamine=False
        )
        halves = fresh()
        for _ in range(2):
            halves.update_from_signals(
                reward=reward, novelty=0.0, conflict=0.0, dt=0.5, use_reward_for_dopamine=False
            )
        self.assertAlmostEqual(full.cortisol, halves.cortisol, places=9)

        initial = fresh().cortisol
        legacy = initial
        legacy += self.nm.ACC_CORT_HOMEOSTATIC_DECAY * (self.nm.BASELINE_CORT - initial)
        legacy += self.nm.CORT_REWARD_NEGATIVE * abs(reward)
        self.assertAlmostEqual(full.cortisol, legacy, places=9)

    def test_cortisol_steady_level_does_not_depend_on_dt(self):
        """Same simulated time and a constant negative outcome share one level."""
        reward = -0.8
        horizon = 24.0
        levels = []
        for dt in (0.25, 0.5, 1.0, 1.25):
            nm = NeuromodulatorState()
            steps = int(round(horizon / dt))
            for _ in range(steps):
                nm.update_from_signals(
                    reward=reward,
                    novelty=0.0,
                    conflict=0.0,
                    dt=dt,
                    use_reward_for_dopamine=False,
                )
            levels.append(nm.cortisol)
        secretion = self.nm.CORT_REWARD_NEGATIVE * abs(reward)
        expected = self.nm.BASELINE_CORT + (secretion / self.nm.ACC_CORT_HOMEOSTATIC_DECAY)
        for level in levels:
            self.assertAlmostEqual(level, expected, places=5)
        self.assertAlmostEqual(max(levels), min(levels), places=5)

    def test_four_quarter_seconds_are_not_four_full_cortisol_doses(self):
        reward = -0.8

        def level(dt, steps):
            nm = NeuromodulatorState()
            for _ in range(steps):
                nm.update_from_signals(
                    reward=reward,
                    novelty=0.0,
                    conflict=0.0,
                    dt=dt,
                    use_reward_for_dopamine=False,
                )
            return nm.cortisol

        one_second = level(1.0, 1)
        four_quarters = level(0.25, 4)
        four_seconds = level(1.0, 4)
        self.assertAlmostEqual(four_quarters, one_second, places=9)
        self.assertLess(four_quarters, four_seconds - 0.05)


class TestNeuromodulatorsWithAgentContext(unittest.TestCase):
    """Test neuromodulators in agent context."""
    
    def setUp(self):
        """Set up neuromodulator state."""
        self.nm = NeuromodulatorState()
    
    def test_typical_agent_cycle(self):
        """
        Simulate a typical agent interaction cycle:
        1. Positive interaction (reward)
        2. Consolidation during sleep
        3. Decay during rest
        """
        print("\n=== Typical Agent Cycle ===")
        
        # Waking: positive interaction
        print("1. Waking interaction (positive reward)")
        self.nm.update_from_signals(reward=0.8, novelty=0.3, conflict=0.0)
        state_after_wake = self.nm.snapshot()
        print(f"   DA: {self.nm.dopamine:.3f}, HT: {self.nm.serotonin:.3f}")
        
        # Sleep: consolidation window
        print("2. Sleep consolidation")
        consolidation = self.nm.get_consolidation_strength()
        print(f"   Consolidation strength: {consolidation:.3f}")
        self.assertGreater(consolidation, 1.0, "Should enhance consolidation after positive reward")
        
        # Rest period: decay
        print("3. Rest period (10 minutes)")
        self.nm.decay_over_time(600.0)  # 10 minutes
        print(f"   DA: {self.nm.dopamine:.3f}, HT: {self.nm.serotonin:.3f}")
        
        # Should have partially decayed
        self.assertLess(self.nm.dopamine, state_after_wake['dopamine'])
        
        print("✓ Typical cycle completed\n")


def run_tests():
    """Run all tests with detailed output."""
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all tests
    suite.addTests(loader.loadTestsFromTestCase(TestNeuromodulatorsPhase2))
    suite.addTests(loader.loadTestsFromTestCase(TestNeuromodulatorsWithAgentContext))
    
    # Run with verbose output
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result


if __name__ == '__main__':
    result = run_tests()
    
    # Print summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    print(f"Tests run: {result.testsRun}")
    print(f"Successes: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print("="*70)
    
    # Return exit code
    sys.exit(0 if result.wasSuccessful() else 1)
