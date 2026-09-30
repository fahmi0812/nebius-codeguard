"""CodeGuard command-line interface.

    codeguard run "<task>"      Nemotron writes code+tests -> sandbox -> gates -> judge
    codeguard check FILE        run an existing module through preflight -> sandbox -> gates
    codeguard scan FILE         static gates only (no network)
    codeguard doctor            show (safe) configuration
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from . import __version__
from .agent import Attempt, PipelineResult, evaluate_source, make_llm, run_pipeline
from .config import ConfigError, describe, get_settings
from .gates import preflight

app = typer.Typer(
    help="Nebius CodeGuard — a coding agent that must prove its code in a Nebius sandbox.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console(highlight=False)


def _settings(require_key: bool = True):
    try:
        return get_settings(require_key=require_key)
    except ConfigError as exc:
        console.print(f"[bold red]config error:[/] {exc}")
        raise typer.Exit(2) from exc


def _header(title: str) -> None:
    console.print(Panel.fit(Text(title, style="bold white"), border_style="bright_green", title="Nebius CodeGuard"))


def _gate_table(attempt: Attempt) -> Table:
    t = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
    t.add_column("gate", style="cyan", no_wrap=True)
    t.add_column("result", no_wrap=True)
    t.add_column("detail")
    for name, ok, detail in attempt.report.checks:
        t.add_row(name, "[green]PASS[/]" if ok else "[red]FAIL[/]", detail)
    if attempt.judge is not None:
        j = attempt.judge
        if j.recommend_accept is None:
            t.add_row("nemotron judge", "[yellow]N/A[/]", "reply not parseable (advisory only)")
        else:
            detail = j.summary or ""
            if j.risks:
                detail += ("  risks: " + "; ".join(j.risks))[:200]
            t.add_row("nemotron judge", "[green]ACCEPT[/]" if j.recommend_accept else "[red]VETO[/]", detail.strip())
    return t


def _verdict(accepted: bool, reasons: list[str], extra: str = "") -> None:
    if accepted:
        body = Text("ACCEPT", style="bold green")
        body.append("  evidence-backed: tests passed in a Nebius sandbox" + extra, style="green")
        console.print(Panel(body, border_style="green"))
    else:
        body = Text("REJECT", style="bold red")
        for r in reasons:
            body.append(f"\n  • {r}", style="red")
        console.print(Panel(body, border_style="red"))


class _Printer:
    """Turns pipeline events into readable terminal output."""

    def __init__(self, settings, show_code: bool, mode: str = "run") -> None:
        self.settings = settings
        self.show_code = show_code
        self.mode = mode
        self._status = None

    def _spin(self, msg: str) -> None:
        self._stop()
        self._status = console.status(msg, spinner="dots")
        self._status.start()

    def _stop(self) -> None:
        if self._status is not None:
            self._status.stop()
            self._status = None

    def __call__(self, event: str, data: dict) -> None:
        s = self.settings
        if event == "write_start":
            n = data["attempt"]
            label = "repair attempt" if data["repair"] else "attempt"
            console.print(Rule(f"[bold]{label} {n}[/]", style="bright_black"))
            console.print(f"[bold cyan][1/4] Write[/]  NVIDIA Nemotron ({s.nemotron_model}) via Nebius Token Factory")
            self._spin("Nemotron is writing code + tests …")
        elif event == "write_done":
            self._stop()
            src = data["source"]
            lines = src.count("\n")
            what = "generated solution.py" if self.mode == "run" else "module under test"
            console.print(f"      {what}: {lines} lines")
            if self.show_code:
                console.print(Syntax(src, "python", theme="monokai", line_numbers=True, word_wrap=True))
        elif event == "preflight":
            f = data["findings"]
            if f:
                console.print("[bold cyan][2/4] Preflight[/]  static security + quality scan: [red]BLOCKED[/]")
                for x in f:
                    console.print(f"      [red]✘ {x}[/]")
                console.print("      [yellow]code is NOT sent to the sandbox[/]")
            else:
                console.print("[bold cyan][2/4] Preflight[/]  static security + quality scan: [green]clean[/]")
        elif event == "sandbox_start":
            console.print(
                f"[bold cyan][3/4] Sandbox[/]  Nebius Token Factory Sandbox (Contree) · image {s.sandbox_image}"
            )
            self._spin("running tests in a fresh disposable sandbox …")
        elif event == "sandbox_done":
            self._stop()
            run, tests = data["run"], data["tests"]
            dur = f" · {run.duration_s:.1f}s" if run.duration_s else ""
            color = "green" if run.exit_code == 0 else "red"
            if tests.total is not None:
                summary = f" · tests {tests.passed}/{tests.total} passed"
            else:
                summary = " · no test summary"
            console.print(f"      exit code: [{color}]{run.exit_code}[/]{dur}{summary}")
            out = (run.stdout.strip() or "(empty)")
            console.print(
                Panel(Text(out[-1200:]), title="sandbox stdout", border_style="bright_black", expand=False)
            )
            if run.stderr.strip():
                err = Text(run.stderr.strip()[-900:], style="red")
                console.print(Panel(err, title="sandbox stderr", border_style="red", expand=False))
        elif event == "gates":
            console.print("[bold cyan][4/4] Gates[/]  evidence-first accept / reject")
        elif event == "judge_start":
            self._spin("Nemotron judge reviewing observed evidence only …")
        elif event == "judge_done":
            self._stop()
        elif event == "attempt_done":
            att: Attempt = data["attempt"]
            console.print(_gate_table(att))
            if not att.accepted and self.mode == "run":
                console.print(f"      attempt {att.number}: [red]REJECT[/]")


@app.command()
def run(
    task: str = typer.Argument(..., help="Coding task in plain English."),
    attempts: int = typer.Option(2, "--attempts", "-n", min=1, max=3, help="Max write attempts (repair loop)."),
    judge: bool = typer.Option(True, "--judge/--no-judge", help="Ask the Nemotron judge (veto only)."),
    show_code: bool = typer.Option(True, "--show-code/--hide-code", help="Print generated code."),
    save: Optional[Path] = typer.Option(None, "--save", help="Write the accepted module to this path."),
) -> None:
    """Nemotron writes code + tests → Nebius sandbox runs them → gates → judge."""
    settings = _settings()
    _header(f"Task: {task}")
    printer = _Printer(settings, show_code)
    from .sandbox import SandboxClient

    try:
        result: PipelineResult = run_pipeline(
            task,
            llm=make_llm(settings),
            sandbox=SandboxClient(settings),
            attempts=attempts,
            use_judge=judge,
            on_event=printer,
        )
    finally:
        printer._stop()
    final = result.final
    assert final is not None
    extra = f" (attempt {final.number}, {result.sandbox_runs} sandbox run{'s' if result.sandbox_runs != 1 else ''})"
    console.print()
    _verdict(result.accepted, final.reasons, extra if result.accepted else "")
    if result.accepted and save:
        save.write_text(final.source, encoding="utf-8")
        console.print(f"saved accepted module → {save}")
    raise typer.Exit(0 if result.accepted else 1)


@app.command()
def check(
    path: Path = typer.Argument(..., exists=True, dir_okay=False, help="Python module with test_* functions."),
    judge: bool = typer.Option(False, "--judge/--no-judge", help="Also ask the Nemotron judge."),
) -> None:
    """Run an existing module through preflight → sandbox → gates (no code generation)."""
    settings = _settings()
    source = path.read_text(encoding="utf-8")
    _header(f"Check: {path.name}")
    printer = _Printer(settings, show_code=True, mode="check")
    console.print("[bold cyan][1/4] Input[/]  existing module (no code generation)")
    printer("write_done", {"source": source})
    from .sandbox import SandboxClient

    try:
        att = evaluate_source(
            source,
            sandbox=SandboxClient(settings),
            llm=make_llm(settings) if judge else None,
            use_judge=judge,
            on_event=printer,
        )
    finally:
        printer._stop()
    printer("attempt_done", {"attempt": att})
    console.print()
    _verdict(att.accepted, att.reasons)
    raise typer.Exit(0 if att.accepted else 1)


@app.command()
def scan(path: Path = typer.Argument(..., exists=True, dir_okay=False)) -> None:
    """Static security + quality gates only (no network, no sandbox)."""
    findings = preflight(path.read_text(encoding="utf-8"))
    if findings:
        for f in findings:
            console.print(f"[red]✘[/] {f}")
        raise typer.Exit(1)
    console.print("[green]✔ clean[/] (static gates only — run `codeguard check` for sandbox evidence)")


@app.command()
def doctor() -> None:
    """Show configuration (secret values are never printed)."""
    settings = _settings(require_key=False)
    t = Table(show_header=False, box=None)
    for k, v in describe(settings).items():
        style = "red" if v == "MISSING" else ""
        t.add_row(k, f"[{style}]{v}[/]" if style else v)
    console.print(t)
    if not settings.api_key or not settings.project_id:
        raise typer.Exit(2)


@app.command()
def version() -> None:
    """Print version."""
    console.print(__version__)


def main() -> None:
    app(prog_name="codeguard")


if __name__ == "__main__":
    sys.exit(main())
