#!/usr/bin/env python3
"""Capture colony evolution from a real seeded run, in English and Russian.

Headless: SDL_VIDEODRIVER=dummy. Uses the colony window's own overlays
(lineage, swarm analytics, inspector genome tab, status panel).

    python tools/render_evolution_media.py
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
CORE_SRC = REPO / "src"
if str(CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CORE_SRC))
if str(COLONY_SRC) not in sys.path:
    sys.path.insert(0, str(COLONY_SRC))

from render_promo_media import (  # noqa: E402
    _image_from_surface,
    _mate_and_birth,
    _mature,
    _report,
    _save_gif,
)


def _fonts():
    import pygame

    pygame.font.init()
    family = "DejaVu Sans, Liberation Sans, Arial"
    mono = "DejaVu Sans Mono, Liberation Mono, Courier New"
    return (
        pygame.font.SysFont(family, 16),
        pygame.font.SysFont(family, 13),
        pygame.font.SysFont(mono, 12),
    )


def _living(runner, generation: int | None = None):
    agents = list(runner.agents)
    if generation is None:
        return agents
    return [agent for agent in agents if int(getattr(agent, "generation", 0) or 0) == generation]


def _unrelated(female, male) -> bool:
    mothers = {item for item in (getattr(female, "parents", ()) or ()) if item}
    fathers = {item for item in (getattr(male, "parents", ()) or ()) if item}
    if not mothers or not fathers:
        return True
    return mothers.isdisjoint(fathers)


def _breed_wave(runner, generation: int) -> list:
    females = [agent for agent in _living(runner, generation) if agent.sex == "F"]
    males = [agent for agent in _living(runner, generation) if agent.sex == "M"]
    born: list = []
    used: set[str] = set()
    pairs = []
    for female in females:
        for male in males:
            if _unrelated(female, male):
                pairs.append((female, male))
    for female in females:
        for male in males:
            if (female, male) not in pairs:
                pairs.append((female, male))
    for female, male in pairs:
        if female.agent_id in used or male.agent_id in used:
            continue
        _mature(female)
        _mature(male)
        kids = _mate_and_birth(runner, female, male)
        if not kids:
            continue
        used.add(female.agent_id)
        used.add(male.agent_id)
        born.extend(kids)
    return born


def _kill_oldest(runner, agents: list) -> None:
    from config_colony import COLONY_MAX_LIFESPAN_AGE_S

    for agent in agents:
        if agent not in runner.agents:
            continue
        agent.mortality_system.update(
            energy=0.5,
            wakefulness=0.2,
            lived_steps=int(getattr(agent, "lived_steps", 0) or 0),
            cortisol_mean=0.1,
            biological_age_s=max(float(agent.age), float(COLONY_MAX_LIFESPAN_AGE_S)),
            dt_s=1.0,
        )
    for agent_id in list(runner.swarm.check_mortality()):
        runner._handle_agent_death(agent_id)


def simulate_evolution(seed: int = 11):
    """Breed several generations through the colony runner and record checkpoints."""

    from colony_agent import ChinchillaAgent
    from colony_gui.colony_gui import ColonyGUI
    from colony_gui.config import is_formatted_name
    from genome import GenomeVector
    from simulation_runner import SimulationRunner

    ChinchillaAgent._generation_name_counters.clear()
    journal_dir = Path(tempfile.mkdtemp(prefix="nowa-evolution-"))
    runner = SimulationRunner(death_journal_path=journal_dir / "deaths.jsonl")
    rng = random.Random(seed)
    founders = []
    for sex in ("F", "M", "F", "M", "F", "M", "F", "M"):
        agent = ChinchillaAgent(
            sex=sex,
            is_mature=True,
            position="floor",
            genome=GenomeVector.random(random.Random(rng.randrange(1 << 30))),
            rng=random.Random(rng.randrange(1 << 30)),
        )
        runner.add_agent(agent)
        founders.append(agent)

    gui = ColonyGUI(runner)
    checkpoints = [("founders", _snapshot(gui))]
    for generation in (0, 1, 2):
        born = _breed_wave(runner, generation)
        if not born:
            raise RuntimeError(f"generation {generation} produced no offspring")
        label = f"after-g{generation + 1}"
        checkpoints.append((label, _snapshot(gui)))

    _kill_oldest(runner, founders[:3])
    checkpoints.append(("after-deaths", _snapshot(gui)))

    names = []
    for agent in runner.agents:
        names.append(agent.name)
    names.extend(memorial.name for memorial in runner.death_registry.get_all_memorials())
    if not names or not all(is_formatted_name(name) for name in names):
        raise RuntimeError(f"evolution names are not colony ids: {names}")
    generations = {int(agent.generation) for agent in runner.agents}
    generations.update(int(memorial.generation) for memorial in runner.death_registry.get_all_memorials())
    if max(generations) < 3:
        raise RuntimeError(f"expected generation 3, got {sorted(generations)}")
    print(
        "evolution pedigree:",
        ", ".join(names),
        "generations",
        sorted(generations),
        "births",
        runner.total_births,
        "deaths",
        runner.total_deaths,
    )
    return gui, checkpoints


def _snapshot(gui) -> dict:
    """Freeze render numbers, reproduction diagnostics, and recent deaths."""

    from colony_gui.app import _collect_reproduction_diagnostics

    gui.observer.observe_force()
    gui._update_snapshot()
    registry = gui.runner.death_registry
    dead = list(registry.get_recent_memorials(12)) if registry is not None else []
    stats = gui.get_render_state().get("population_stats", {})
    print(
        "checkpoint agents",
        stats.get("agent_count"),
        "births",
        stats.get("total_births"),
        "deaths",
        stats.get("total_deaths"),
        "has_data",
        stats.get("has_data"),
    )
    return {
        "state": gui.get_render_state(),
        "diagnostics": dict(_collect_reproduction_diagnostics(gui.runner)),
        "dead": dead,
    }


def _draw_colony_stats(screen, gui, checkpoint) -> None:
    from colony_gui.app import _draw_right_panel, _draw_stats_panel, _paint_static_scene
    from colony_gui.cage_view import get_zone_render_pos

    import pygame

    state = checkpoint["state"]
    font, font_small, _font_mono = _fonts()
    _paint_static_scene(screen, font)
    zone_counts: dict[str, int] = {}
    for agent in state.get("agents", []):
        zone = str(agent.get("position") or "floor")
        index = zone_counts.get(zone, 0)
        zone_counts[zone] = index + 1
        try:
            x, y = get_zone_render_pos(zone, index, str(agent.get("agent_id", "")))
        except Exception:
            x, y = 200 + (index * 28) % 600, 400
        pygame.draw.circle(screen, (90, 70, 55), (int(x), int(y)), 14)
        label = font_small.render(str(agent.get("name", "")), True, (35, 28, 20))
        screen.blit(label, (int(x) - label.get_width() // 2, int(y) - 28))
    _draw_stats_panel(
        screen=screen,
        font_small=font_small,
        text_surface_cache={},
        sim_time_text=str(state.get("sim_time_text", "")),
        speed=float(gui.speed),
        paused=False,
        audio_enabled=False,
        diagnostics=dict(checkpoint.get("diagnostics", {})),
        population_stats=dict(state.get("population_stats", {})),
        resources=dict(state.get("resources", {})),
    )
    _draw_right_panel(
        screen,
        font,
        font_small,
        living_agents_data=list(state.get("agents", [])),
        dead_memorials=list(checkpoint.get("dead", [])),
        name_registry=getattr(gui.runner, "birth_registry", None),
        selected_agent_id=None,
        scroll_offset=0,
    )


def _colony_frame(gui, checkpoint):
    import pygame

    from colony_gui.app import PANEL_RIGHT_W, PANEL_RIGHT_X, STATS_PANEL_HEIGHT, STATS_PANEL_MARGIN_TOP, WINDOW_EXTRA_UI_HEIGHT
    from colony_gui.config import CAGE_RECT

    screen_w = max(gui.WIDTH, PANEL_RIGHT_X + PANEL_RIGHT_W + 8)
    screen_h = gui.HEIGHT + WINDOW_EXTRA_UI_HEIGHT
    screen = pygame.display.set_mode((screen_w, screen_h))
    screen.fill((235, 228, 215))
    _draw_colony_stats(screen, gui, checkpoint)
    pygame.display.flip()
    cage_x, cage_y, cage_w, cage_h = CAGE_RECT
    top = int(cage_y + cage_h + STATS_PANEL_MARGIN_TOP)
    # Native-resolution status strip: population, births/deaths, affect bars.
    crop = pygame.Rect(int(cage_x), top, int(cage_w), int(STATS_PANEL_HEIGHT))
    return _image_from_surface(screen.subsurface(crop).copy(), max_width=980)


def _overlay_frame(draw, crop_box=None):
    import pygame

    screen = pygame.display.set_mode((1040, 760))
    screen.fill((235, 228, 215))
    font, font_small, font_mono = _fonts()
    panel = draw(screen, font, font_small, font_mono)
    pygame.display.flip()
    if crop_box is None and panel is not None:
        crop_box = panel
    if crop_box is not None:
        screen = screen.subsurface(pygame.Rect(crop_box)).copy()
    return _image_from_surface(screen, max_width=900)


def _render_language(gui, checkpoints, lang: str, dest: Path) -> None:
    import pygame

    from colony_gui.i18n import set_language
    from colony_gui.lineage_overlay import LineageOverlay
    from colony_gui.swarm_analytics_overlay import SwarmAnalyticsOverlay

    pygame.init()
    pygame.font.init()
    set_language(lang)
    dest.mkdir(parents=True, exist_ok=True)
    runner = gui.runner
    gui._update_snapshot()
    index_map = dict(gui._generation_index_map)

    # Stored checkpoints keep each moment's counts. Drawing them in order is
    # the colony strip changing from founders through later generations.
    colony_frames = [_colony_frame(gui, checkpoint) for _label, checkpoint in checkpoints]
    gif = dest / "evolution-colony.gif"
    _save_gif(colony_frames, gif, fps=1)
    colony_frames[-1].save(dest / "evolution-colony.png", optimize=True)
    _report(gif)
    _report(dest / "evolution-colony.png")

    def draw_lineage(screen, font, font_small, _font_mono, step: int = 0, fitted=None):
        overlay = getattr(draw_lineage, "overlay", None)
        if overlay is None:
            overlay = LineageOverlay(runner.death_registry, allow_nonadjacent_parents=False)
            overlay._visible = True
            overlay.rebuild(list(runner.agents), index_map)
            draw_lineage.overlay = overlay
            draw_lineage.focus = [node.agent_id for node in overlay._nodes]
        focus = draw_lineage.focus
        if not focus:
            raise RuntimeError("lineage overlay produced no nodes")
        overlay._fit_pending = step == 0
        overlay._selected_id = focus[min(len(focus) - 1, max(0, len(focus) // 2))]
        overlay._hovered_id = focus[(step + 3) % len(focus)]
        if fitted is not None:
            overlay._offset[0] = fitted[0] + (step - 6) * 8
        overlay.draw(screen, font, font_small)
        return list(overlay._offset)

    lineage_frames = []
    fitted = None
    for step in range(12):
        def _draw(screen, font, font_small, font_mono, step=step):
            nonlocal fitted
            fitted = draw_lineage(screen, font, font_small, font_mono, step=step, fitted=fitted)

        lineage_frames.append(_overlay_frame(_draw))
    lineage_gif = dest / "evolution-lineage.gif"
    _save_gif(lineage_frames, lineage_gif, fps=4)
    lineage_frames[0].save(dest / "evolution-lineage.png", optimize=True)
    _report(lineage_gif)
    _report(dest / "evolution-lineage.png")

    swarm = SwarmAnalyticsOverlay()
    swarm._visible = True
    swarm.refresh(runner, gui.observer, index_map)
    for tab, name in ((0, "evolution-swarm"), (1, "evolution-generations"), (2, "evolution-genomes"), (4, "evolution-forecast")):
        swarm._active_tab = tab
        swarm._scroll = 0

        def _draw(screen, font, font_small, font_mono, tab=tab):
            swarm._active_tab = tab
            swarm.draw(screen, font, font_small, font_mono)
            return swarm._panel_rect

        frame = _overlay_frame(_draw)
        frame.save(dest / f"{name}.png", optimize=True)
        _report(dest / f"{name}.png")

    living = list(runner.agents)
    founders = [agent for agent in living if int(agent.generation) == 0]
    latest = max(int(agent.generation) for agent in living)
    descendants = [
        agent
        for agent in living
        if int(agent.generation) == latest
        and str((getattr(agent, "genome_inheritance_meta", {}) or {}).get("mode", "")) == "recombined"
    ]
    if not founders or not descendants:
        raise RuntimeError("need a living founder and a recombined descendant for the genome tab")
    _save_inspector(dest / "evolution-founder.png", founders[0], runner, index_map, scroll=0)
    _save_inspector(dest / "evolution-descendant.png", descendants[0], runner, index_map, scroll=0)
    _save_inspector(dest / "evolution-mutations.png", descendants[0], runner, index_map, scroll=420)


def _save_inspector(path: Path, agent, runner, index_map, scroll: int) -> None:
    from colony_gui.agent_inspector import AgentInspectorOverlay, build_inspector_data_from_agent

    registry = getattr(runner, "birth_registry", None)
    display = ""
    if registry is not None:
        try:
            display = registry.get_human_name(agent.agent_id) or ""
        except Exception:
            display = ""
    display = display or str(agent.name)
    data = build_inspector_data_from_agent(
        agent,
        display,
        name_registry=registry,
        death_registry=runner.death_registry,
        generation_index_map=index_map,
    )
    inspector = AgentInspectorOverlay()
    inspector.open(data)
    inspector._active_tab = 3
    inspector._scroll = scroll

    def _draw(screen, font, font_small, font_mono):
        inspector._active_tab = 3
        inspector._scroll = scroll
        inspector.draw(screen, font, font_small, font_mono)
        return inspector._panel_rect

    frame = _overlay_frame(_draw)
    frame.save(path, optimize=True)
    _report(path)


def main() -> int:
    import pygame

    pygame.init()
    gui, checkpoints = simulate_evolution()
    for lang in ("en", "ru"):
        _render_language(gui, checkpoints, lang, OUT / lang)
    pygame.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
