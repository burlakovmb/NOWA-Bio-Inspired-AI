import sys
import uuid
from pathlib import Path


# Add src directory to path
SRC_DIR = Path(__file__).parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def test_session_persists_runtime_counters():
    from main import ChinchillaAgent

    demo_dir = Path(__file__).parent.parent
    save_name = f"agent_save_test_{uuid.uuid4().hex[:8]}.nowa"
    save_path = demo_dir / "saves" / save_name

    # Create and save
    agent = ChinchillaAgent(
        demo_dir=str(demo_dir),
        use_pygame=False,
        use_gui=False,
        session_filename=save_name,
    )
    agent.total_sim_time = 123.4
    agent.tick_count = 321
    agent._do_save_session()

    # New agent should load automatically on init
    agent2 = ChinchillaAgent(
        demo_dir=str(demo_dir),
        use_pygame=False,
        use_gui=False,
        session_filename=save_name,
    )
    assert abs(agent2.total_sim_time - 123.4) < 0.01
    assert agent2.tick_count == 321

    # Cleanup
    if save_path.exists():
        try:
            save_path.unlink()
        except Exception:
            pass
