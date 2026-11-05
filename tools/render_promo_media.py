#!/usr/bin/env python3
"""Render short promo clips of the colony, tamagotchi, and lineage tree.

Headless: SDL_VIDEODRIVER=dummy. Requires pygame and pillow
(pip install -r requirements-demo.txt && pip install pillow).

    python tools/render_promo_media.py
"""

from __future__ import annotations

import os
import random
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "docs" / "media"
COLONY_SRC = REPO / "Demo" / "Colony chinchillas" / "src"
TAMAGOTCHI_SRC = REPO / "Demo" / "Tamagochi Chinchilla" / "src"


def _image_from_surface(surface, max_width: int = 760):
    import pygame
    from PIL import Image

    width, height = surface.get_size()
    if width > max_width:
        height = max(1, int(height * max_width / width))
        width = max_width
        surface = pygame.transform.smoothscale(surface, (width, height))
    raw = pygame.image.tobytes(surface, "RGB")
    return Image.frombytes("RGB", (width, height), raw)


def _save_gif(frames, path: Path, fps: int = 8) -> None:
    if not frames:
        raise RuntimeError(f"no frames for {path}")
    # Quantize each frame on its own, then hand Pillow a fresh RGB sequence.
    # Sharing one palette across frames collapsed the colony clip to a single frame.
    rgb = [frame.convert("RGB") for frame in frames]
    rgb[0].save(
        path,
        format="GIF",
        save_all=True,
        append_images=rgb[1:],
        duration=int(1000 / fps),
        loop=0,
        optimize=True,
    )


def _report(path: Path) -> None:
    size = path.stat().st_size
    print(f"{path.relative_to(REPO)}  {size / 1_048_576:.2f} MB")
    if size > 5 * 1_048_576:
        raise RuntimeError(f"{path} exceeds 5 MB")


def _activate(lang: str) -> None:
    os.environ["NOWA_LANG"] = lang
    for src in (COLONY_SRC, TAMAGOTCHI_SRC):
        if str(src) not in sys.path:
            sys.path.insert(0, str(src))
    from colony_gui.i18n import set_language as set_colony_language
    from tama_i18n import set_language as set_tama_language

    set_colony_language(lang)
    set_tama_language(lang)


def render_colony(out: Path) -> None:
    import pygame

    if str(COLONY_SRC) not in sys.path:
        sys.path.insert(0, str(COLONY_SRC))
    from colony_gui.app import run_pygame_demo

    frames = []

    def on_frame(screen) -> None:
        frames.append(_image_from_surface(screen))

    run_pygame_demo(
        agent_count=6,
        max_frames=24,
        frame_dt_s=0.12,
        on_frame=on_frame,
    )
    pygame.quit()
    gif = out / "colony.gif"
    png = out / "colony.png"
    _save_gif(frames, gif, fps=8)
    frames[len(frames) // 2].save(png, optimize=True)
    _report(gif)
    _report(png)


def render_tamagotchi(out: Path) -> None:
    import pygame

    if str(TAMAGOTCHI_SRC) not in sys.path:
        sys.path.insert(0, str(TAMAGOTCHI_SRC))
    from pygame_engine import PygameEngine

    engine = PygameEngine(width=960, height=640, fps=30)
    engine.audio_enabled = False
    font_name = "DejaVu Sans, Liberation Sans, Arial"
    engine.font_sub = pygame.font.SysFont(font_name, 22)
    engine.font_ui = pygame.font.SysFont(font_name, 16)
    engine.font_ui_title = pygame.font.SysFont(font_name, 20, bold=True)
    sprites = REPO / "Demo" / "Tamagochi Chinchilla" / "sprites"
    for sprite in sorted(sprites.glob("*.png")):
        engine.load_animation(sprite.stem, sprite)

    script = (
        ("walk_loop", "bowl_pellets", "ест гранулы", 10),
        ("eat_hay_loop", "bowl_hay", "ест сено", 12),
        ("run_wheel_loop", "wheel", "на колесе", 12),
        ("dustbath_loop", "dustbath", "купается в пыли", 10),
        ("sleep_loop", "house", "спит в домике", 10),
    )
    frames = []
    for anim, position, subtitle, steps in script:
        engine.queue_action(
            {
                "action_id": anim,
                "anim": anim,
                "sfx": None,
                "position": position,
                "duration": [2, 4],
                "subtitle": subtitle,
                "loop": True,
                "layer": "action",
            }
        )
        engine.process_actions()
        # The engine will not replace an action younger than one second.
        engine._action_layer_age = 2.0
        for _ in range(steps):
            engine.update(0.12)
            engine.render()
            frames.append(_image_from_surface(engine.screen, max_width=720))
    pygame.quit()
    gif = out / "tamagotchi.gif"
    png = out / "tamagotchi.png"
    _save_gif(frames, gif, fps=8)
    frames[len(frames) // 3].save(png, optimize=True)
    _report(gif)
    _report(png)


def _remember(observer, target, affinity: float) -> None:
    from agent_knowledge import KnownAgent

    observer.knowledge[target.agent_id] = KnownAgent(
        agent_id=target.agent_id,
        name=target.name,
        sex=target.sex,
        last_seen_position=target.position,
        last_seen_time=observer.sim_time,
        familiarity=0.7,
        affinity=affinity,
        relationship_type="acquaintance",
    )


def _mate_and_birth(runner, female, male) -> list:
    """Drive the same mating and birth path the colony tests use."""

    _remember(female, male, 0.7)
    _remember(male, female, 0.6)
    if female.heat_cycle is None:
        return []
    female.heat_cycle.phase = "estrus"
    female.heat_cycle.value = 0.8
    female.affective_space.axes["stress"] = 0.1
    male.affective_space.axes["stress"] = 0.1
    female.energy = 0.9
    male.energy = 0.9
    response = male.send_social_offer("mount_display", female)
    if response is None or not response.accepted:
        return []
    # Gestation is 300s in the sim. The reproduction tests shorten the
    # remaining timer and then let SimulationRunner.run_for call _give_birth.
    female.gestation_timer = 1.0
    before = {agent.agent_id for agent in runner.agents}
    runner.run_for(3.0, dt=1.0)
    return [agent for agent in runner.agents if agent.agent_id not in before]


def _mature(agent) -> None:
    from config_colony import MATURITY_AGE_S

    agent.age = MATURITY_AGE_S - 1.0
    agent._age_step(2.0)


def simulate_promo_lineage():
    """Run a short colony so lineage names come from ChinchillaAgent.

    Founders are constructed without a display name, so ``_next_generated_name``
    assigns ``G{generation}A{index}S{sex}``. Births go through
    ``send_social_offer`` and ``SimulationRunner.run_for``. Two founders then
    die through ``MortalitySystem.update`` (old age at that animal's cap)
    and ``SimulationRunner``'s death registration. No display name
    is passed in.
    """

    from colony_agent import ChinchillaAgent, colony_scripted_old_age_s
    from colony_gui.config import is_formatted_name
    from simulation_runner import SimulationRunner

    ChinchillaAgent._generation_name_counters.clear()
    journal_dir = Path(tempfile.mkdtemp(prefix="nowa-lineage-"))
    runner = SimulationRunner(death_journal_path=journal_dir / "deaths.jsonl")
    rng = random.Random(7)
    founders = []
    for sex in ("F", "M", "F", "M"):
        agent = ChinchillaAgent(
            sex=sex,
            is_mature=True,
            position="floor",
            rng=random.Random(rng.randrange(1 << 30)),
        )
        runner.add_agent(agent)
        founders.append(agent)

    for female, male in ((founders[0], founders[1]), (founders[2], founders[3])):
        if not _mate_and_birth(runner, female, male):
            raise RuntimeError("founder pair did not give birth through the colony runner")

    generation_one = [agent for agent in runner.agents if agent.generation == 1]
    females = [agent for agent in generation_one if agent.sex == "F"]
    males = [agent for agent in generation_one if agent.sex == "M"]
    pair = None
    for female in females:
        for male in males:
            if set(female.parents).isdisjoint(set(male.parents)):
                pair = (female, male)
                break
        if pair is not None:
            break
    if pair is None:
        raise RuntimeError("seed 7 did not produce a cross-family breeding pair")
    _mature(pair[0])
    _mature(pair[1])
    if not _mate_and_birth(runner, pair[0], pair[1]):
        raise RuntimeError("second generation was not born through the colony runner")

    for agent in founders[:2]:
        agent.mortality_system.update(
            energy=0.5,
            wakefulness=0.2,
            lived_steps=int(getattr(agent, "lived_steps", 0) or 0),
            cortisol_mean=0.1,
            biological_age_s=colony_scripted_old_age_s(agent),
            dt_s=1.0,
        )
    for agent_id in runner.swarm.check_mortality():
        runner._handle_agent_death(agent_id)

    names = [agent.name for agent in runner.agents]
    names.extend(memorial.name for memorial in runner.death_registry.get_all_memorials())
    if not names or not all(is_formatted_name(name) for name in names):
        raise RuntimeError(f"lineage names are not colony ids: {names}")
    generations = {agent.generation for agent in runner.agents}
    generations.update(memorial.generation for memorial in runner.death_registry.get_all_memorials())
    if generations != {0, 1, 2}:
        raise RuntimeError(f"expected three generations, got {sorted(generations)}")
    if not runner.death_registry.get_all_memorials():
        raise RuntimeError("expected at least one real death in the pedigree")
    print("lineage agents:", ", ".join(names))
    return runner


def render_lineage(out: Path) -> None:
    import pygame

    if str(COLONY_SRC) not in sys.path:
        sys.path.insert(0, str(COLONY_SRC))
    from colony_gui.lineage_overlay import LineageOverlay

    runner = simulate_promo_lineage()
    pygame.init()
    pygame.font.init()
    screen = pygame.display.set_mode((960, 640))
    font = pygame.font.SysFont("DejaVu Sans, Liberation Sans, Arial", 18)
    font_small = pygame.font.SysFont("DejaVu Sans, Liberation Sans, Arial", 14)
    overlay = LineageOverlay(runner.death_registry, allow_nonadjacent_parents=False)
    overlay._visible = True
    overlay.rebuild(list(runner.agents), runner._build_generation_index_map())
    focus = [node.agent_id for node in overlay._nodes]
    if not focus:
        raise RuntimeError("lineage overlay produced no nodes")
    overlay._selected_id = focus[0]
    overlay._hovered_id = focus[min(1, len(focus) - 1)]

    frames = []
    fitted_offset = None
    for step in range(16):
        screen.fill((235, 228, 215))
        overlay._fit_pending = step == 0
        overlay._selected_id = focus[step % len(focus)]
        overlay._hovered_id = focus[(step + 2) % len(focus)]
        if fitted_offset is not None:
            overlay._offset[0] = fitted_offset[0] + (step - 8) * 6
        overlay.draw(screen, font, font_small)
        if fitted_offset is None:
            fitted_offset = list(overlay._offset)
        pygame.display.flip()
        frames.append(_image_from_surface(screen, max_width=760))
    pygame.quit()
    gif = out / "lineage.gif"
    png = out / "lineage.png"
    _save_gif(frames, gif, fps=6)
    frames[-1].save(png, optimize=True)
    _report(gif)
    _report(png)


def main() -> int:
    import shutil

    OUT.mkdir(parents=True, exist_ok=True)
    names = (
        "colony.gif",
        "colony.png",
        "tamagotchi.gif",
        "tamagotchi.png",
        "lineage.gif",
        "lineage.png",
    )
    for lang in ("en", "ru"):
        dest = OUT / lang
        dest.mkdir(parents=True, exist_ok=True)
        _activate(lang)
        render_colony(dest)
        render_tamagotchi(dest)
        render_lineage(dest)
    for name in names:
        shutil.copyfile(OUT / "en" / name, OUT / name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
