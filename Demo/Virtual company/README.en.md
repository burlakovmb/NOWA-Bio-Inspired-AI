# NOWA Virtual Organisation

Russian version: [README.ru.md](README.ru.md)

The platform contains a procurement sandbox and a protocol body with an employee host. The contours do not import one another. Scientific account, invariants, curriculum, laboratory observations, and commands: [Docs/SCIENTIFIC_DESCRIPTION.en.md](Docs/SCIENTIFIC_DESCRIPTION.en.md). Account of the complex: [Docs/SCIENTIFIC_DESCRIPTION.en.md](../../Docs/SCIENTIFIC_DESCRIPTION.en.md).

Short sandbox launch from the platform directory:

```bash
python src/nowa_sandbox/run_sandbox.py --config configs/default_world.yaml --stage 1a --quarters 30
```

Sandbox laboratory: `python -m nowa_sandbox.gui_app --lang en` (or `run_gui.bat`).

![Procurement sandbox laboratory in English](../../Docs/media/en/sandbox-lab.png)

Body laboratory: `python -m nowa_body.gui_app --lang en` (or `run_body_gui.bat`).

![Body layer laboratory in English](../../Docs/media/en/body-lab.png)

Role configurator: `python -m nowa_body.gui_configurator --lang en` (or `run_role_configurator.bat`).

![Role configurator in English](../../Docs/media/en/role-configurator.png)

Each lab has separate EN and RU buttons, and the active one is highlighted. The choice is remembered. `--lang en|ru` overrides that saved preference for one launch; otherwise `NOWA_LANG` does, and a saved preference is used when neither is set. Default is English.

Checks: `python -m pytest -m "not slow"`.

Normative specifications in `Docs/` retain module contracts. Their prefaces, in Russian and in English, refer to the scientific account.

Training checkpoints are `*.ckpt` (metadata, schema `2`) plus `*.ckpt.agent.nowa` (agent state). The employee host writes `mind.nowa` on stop. Pickle checkpoints are rejected; recreate after upgrading — [Docs/specs/issue-16-31-safe-agent-state.en.md](../../Docs/specs/issue-16-31-safe-agent-state.en.md).
