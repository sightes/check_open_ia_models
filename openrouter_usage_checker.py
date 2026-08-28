#!/usr/bin/env python3
"""
OpenRouter Usage Checker

Comprehensive usage report for OpenRouter API including:
- Key info and limits
- Credit balance and remaining
- Usage by period (daily, weekly, monthly)
- Cost projections
- Budget alerts

Usage:
    python openrouter_usage_checker.py
    python openrouter_usage_checker.py --output json
    python openrouter_usage_checker.py --budget 50
    python openrouter_usage_checker.py --summary-only
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

# Default paths
DEFAULT_AUTH_FILE = Path.home() / ".local/share/opencode/auth.json"

# OpenRouter API endpoints
OPENROUTER_KEY_URL = "https://openrouter.ai/api/v1/key"
OPENROUTER_CREDITS_URL = "https://openrouter.ai/api/v1/credits"

# Console
console = Console()


def load_openrouter_key(auth_file: Path | None = None) -> str | None:
    """Load OpenRouter API key from environment or auth.json."""
    # Priority 1: Environment variable
    env_key = os.environ.get("OPENROUTER_API_KEY")
    if env_key:
        return env_key

    # Priority 2: auth.json file
    if auth_file and auth_file.exists():
        try:
            with open(auth_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

        # Look for "openrouter" key
        if "openrouter" in data:
            return data["openrouter"].get("key")

        # Fallback: find any key with "sk-or" prefix
        for name, creds in data.items():
            if creds.get("type") == "api":
                key = creds.get("key", "")
                if key.startswith("sk-or"):
                    return key

    return None


def check_key_usage(api_key: str) -> dict[str, Any]:
    """Check OpenRouter key usage via API."""
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        response = requests.get(OPENROUTER_KEY_URL, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        return {"error": str(e)}


def check_credits(api_key: str) -> dict[str, Any]:
    """Check OpenRouter credits (requires management key)."""
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        response = requests.get(OPENROUTER_CREDITS_URL, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        return {"error": str(e)}


def format_currency(amount: float | None) -> str:
    """Format currency amount."""
    if amount is None:
        return "N/A"
    return f"${amount:.2f}"


def format_percent(value: float, total: float | None) -> str:
    """Format percentage with visual indicator."""
    if total is None or total == 0:
        return "N/A"
    percent = (value / total) * 100
    return f"{percent:.1f}%"


def get_usage_color(usage: float, limit: float | None) -> str:
    """Get color based on usage percentage."""
    if limit is None or limit == 0:
        return "green"
    percent = (usage / limit) * 100
    if percent >= 90:
        return "red"
    elif percent >= 75:
        return "dark_orange"
    elif percent >= 50:
        return "yellow"
    else:
        return "green"


def get_budget_status(current: float, budget: float) -> tuple[str, str]:
    """Get budget status and color."""
    if budget <= 0:
        return "sin_presupuesto", "gray"

    percentage = (current / budget) * 100

    if percentage >= 100:
        return "EXCEDIDO", "red"
    elif percentage >= 75:
        return "CRITICO", "red"
    elif percentage >= 50:
        return "ALERTA", "yellow"
    elif percentage >= 25:
        return "MODERADO", "yellow"
    else:
        return "BAJO", "green"


def calculate_monthly_projection(daily_usage: float) -> dict:
    """Project monthly costs based on daily usage."""
    return {
        "daily": daily_usage,
        "weekly": daily_usage * 7,
        "monthly": daily_usage * 30,
        "yearly": daily_usage * 365
    }


def print_rich_report(key_data: dict[str, Any], credits_data: dict[str, Any],
                      budget: float, api_key: str) -> None:
    """Print comprehensive rich UI report."""

    console.print()
    console.print(Panel.fit(
        "[bold cyan]REPORTE DE USO - OPENROUTER[/bold cyan]",
        border_style="cyan"
    ))

    # Section 1: Key Info
    console.print()
    console.print(Panel("[bold]1. INFO DE KEY[/bold]", border_style="blue"))

    if "error" in key_data:
        console.print(f"[red]Error: {key_data['error']}[/red]")
        if "401" in str(key_data['error']) or "Unauthorized" in str(key_data['error']):
            console.print("\n[yellow]Verifica que tu API key sea válida.[/yellow]")
            console.print("Obtén una key en: https://openrouter.ai/keys")
        return

    key_info = key_data.get("data", {})

    info_table = Table(show_header=False, box=box.SIMPLE, padding=(0, 2))
    info_table.add_column("Campo", style="cyan", width=20)
    info_table.add_column("Valor", width=30)

    label = key_info.get("label", "Sin nombre")
    is_free = key_info.get("is_free_tier", False)
    tier = "Free" if is_free else "Paid"

    info_table.add_row("Label", label)
    info_table.add_row("Tier", f"[{'green' if not is_free else 'yellow'}]{tier}[/{'green' if not is_free else 'yellow'}]")

    limit = key_info.get("limit")
    info_table.add_row("Límite Key", format_currency(limit) if limit else "Sin límite")

    console.print(info_table)

    # Section 2: Balance
    console.print()
    console.print(Panel("[bold]2. SALDO Y CRÉDITOS[/bold]", border_style="green"))

    usage = key_info.get("usage", 0)
    limit_remaining = key_info.get("limit_remaining")

    # If we have credits data (management key)
    if "error" not in credits_data:
        credits = credits_data.get("data", {})
        total_credits = credits.get("total_credits", 0)
        total_usage = credits.get("total_usage", 0)
        remaining = total_credits - total_usage

        balance_table = Table(show_header=False, box=box.SIMPLE, padding=(0, 2))
        balance_table.add_column("Concepto", style="cyan", width=20)
        balance_table.add_column("Monto", width=15)
        balance_table.add_column("Porcentaje", width=15)
        balance_table.add_column("Estado", width=15)

        used_color = get_usage_color(total_usage, total_credits)
        percent_str = format_percent(total_usage, total_credits)

        balance_table.add_row(
            "Total Comprado",
            format_currency(total_credits),
            "100%",
            "[green]Total[/green]"
        )
        balance_table.add_row(
            "Usado",
            f"[{used_color}]{format_currency(total_usage)}[/{used_color}]",
            f"[{used_color}]{percent_str}[/{used_color}]",
            f"[{used_color}]Gastado[/{used_color}]"
        )
        balance_table.add_row(
            "Restante",
            f"[bold green]{format_currency(remaining)}[/bold green]",
            format_percent(remaining, total_credits),
            "[bold green]Disponible[/bold green]"
        )

        console.print(balance_table)
    else:
        # No management key - show key-level info
        balance_table = Table(show_header=False, box=box.SIMPLE, padding=(0, 2))
        balance_table.add_column("Concepto", style="cyan", width=20)
        balance_table.add_column("Monto", width=15)

        if limit_remaining is not None:
            balance_table.add_row("Límite Key", format_currency(limit))
            balance_table.add_row("Usado", f"[yellow]{format_currency(usage)}[/yellow]")
            balance_table.add_row("Restante", f"[bold green]{format_currency(limit_remaining)}[/bold green]")
        else:
            balance_table.add_row("Uso Total (all-time)", format_currency(usage))
            balance_table.add_row("Límite", "[dim]Sin límite definido[/dim]")

        console.print(balance_table)

        if "error" in credits_data:
            console.print("\n[dim]Para ver saldo completo, usa una Management Key.[/dim]")
            console.print("[dim]Obtén una en: https://openrouter.ai/keys → Create Key → Management[/dim]")

    # Section 3: Usage by Period
    console.print()
    console.print(Panel("[bold]3. USO POR PERÍODO[/bold]", border_style="yellow"))

    daily = key_info.get("usage_daily", 0)
    weekly = key_info.get("usage_weekly", 0)
    monthly = key_info.get("usage_monthly", 0)

    period_table = Table(show_header=True, header_style="bold", box=box.ROUNDED)
    period_table.add_column("Período", style="cyan", width=15)
    period_table.add_column("Uso", justify="right", width=12)
    period_table.add_column("Comparación", width=30)

    # Find max for visual comparison
    max_usage = max(daily, weekly / 7, monthly / 30) if any([daily, weekly, monthly]) else 1

    daily_bar_len = int((daily / max_usage) * 20) if max_usage > 0 else 0
    weekly_avg = weekly / 7
    weekly_bar_len = int((weekly_avg / max_usage) * 20) if max_usage > 0 else 0
    monthly_avg = monthly / 30
    monthly_bar_len = int((monthly_avg / max_usage) * 20) if max_usage > 0 else 0

    period_table.add_row(
        "Hoy",
        f"[bold]{format_currency(daily)}[/bold]",
        f"[cyan]{'█' * daily_bar_len}{'░' * (20 - daily_bar_len)}[/cyan] Avg/día"
    )
    period_table.add_row(
        "Esta semana",
        f"[bold]{format_currency(weekly)}[/bold]",
        f"[yellow]{'█' * weekly_bar_len}{'░' * (20 - weekly_bar_len)}[/yellow] {format_currency(weekly_avg)}/día"
    )
    period_table.add_row(
        "Este mes",
        f"[bold]{format_currency(monthly)}[/bold]",
        f"[green]{'█' * monthly_bar_len}{'░' * (20 - monthly_bar_len)}[/green] {format_currency(monthly_avg)}/día"
    )

    console.print(period_table)

    # Section 4: Cost Projection
    console.print()
    console.print(Panel("[bold]4. PROYECCIÓN DE COSTOS[/bold]", border_style="red"))

    projection = calculate_monthly_projection(daily)

    proj_table = Table(show_header=False, box=box.SIMPLE, padding=(0, 2))
    proj_table.add_column("Período", style="cyan", width=20)
    proj_table.add_column("Proyección", width=15)
    proj_table.add_column("Notas", width=30)

    proj_table.add_row(
        "Promedio diario",
        f"[bold]{format_currency(projection['daily'])}[/bold]",
        "Basado en uso de hoy"
    )
    proj_table.add_row(
        "Proyección semanal",
        f"[bold yellow]{format_currency(projection['weekly'])}[/bold yellow]",
        "7 días"
    )
    proj_table.add_row(
        "Proyección mensual",
        f"[bold red]{format_currency(projection['monthly'])}[/bold red]",
        "30 días"
    )
    proj_table.add_row(
        "Proyección anual",
        f"[bold]{format_currency(projection['yearly'])}[/bold]",
        "365 días"
    )

    console.print(proj_table)

    # Budget comparison
    if budget > 0:
        monthly_ratio = projection['monthly'] / budget
        if monthly_ratio > 1:
            console.print(f"\n[red]⚠ La proyección mensual ({format_currency(projection['monthly'])}) "
                         f"excede el presupuesto ({format_currency(budget)}) en {monthly_ratio:.1f}x[/red]")
        else:
            console.print(f"\n[green]✓ La proyección mensual ({format_currency(projection['monthly'])}) "
                         f"está dentro del presupuesto ({format_currency(budget)})[/green]")

    # Section 5: Budget Status
    if budget > 0:
        console.print()
        console.print(Panel("[bold]5. ESTADO DEL PRESUPUESTO[/bold]", border_style="magenta"))

        status, color = get_budget_status(monthly, budget)
        remaining = max(0, budget - monthly)

        budget_panel = f"[bold {color}]PRESUPUESTO MENSUAL[/bold {color}]\n\n"
        budget_panel += f"Usado este mes: [bold {color}]{format_currency(monthly)}[/bold {color}] / {format_currency(budget)}\n"
        budget_panel += f"Estado: [bold {color}]{status}[/bold {color}]\n"
        budget_panel += f"Restante: [bold {color}]{format_currency(remaining)}[/bold {color}]"

        console.print(Panel(budget_panel, border_style=color))

    # Section 6: Key Limits Info
    if limit is not None:
        console.print()
        console.print(Panel("[bold]6. LÍMITES DE KEY[/bold]", border_style="yellow"))

        info_limit_table = Table(show_header=False, box=box.SIMPLE, padding=(0, 2))
        info_limit_table.add_column("Concepto", style="cyan", width=25)
        info_limit_table.add_column("Valor", width=20)

        info_limit_table.add_row("Límite mensual de key", format_currency(limit))
        info_limit_table.add_row("Usado este mes (key)", format_currency(usage))
        info_limit_table.add_row("Restante en key", format_currency(limit_remaining) if limit_remaining is not None else "N/A")

        reset_info = key_info.get("limit_reset", "N/A")
        info_limit_table.add_row("Reset del límite", reset_info)

        console.print(info_limit_table)

        # Only warn if limit_remaining is explicitly 0 and we have no credits data
        if limit_remaining is not None and limit_remaining == 0 and "error" in credits_data:
            console.print("\n[yellow]⚠ Límite de key agotado. Aumenta el límite o espera al reset.[/yellow]")

    # Footer
    console.print()
    console.print(Panel(
        "[dim]Docs: https://openrouter.ai/docs | "
        "Keys: https://openrouter.ai/keys | "
        "Dashboard: https://openrouter.ai/activity[/dim]",
        border_style="dim"
    ))
    console.print()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reporte de uso de OpenRouter."
    )
    parser.add_argument(
        "--auth-file",
        type=Path,
        default=DEFAULT_AUTH_FILE,
        help=f"Ruta al archivo de autenticación (default: {DEFAULT_AUTH_FILE})",
    )
    parser.add_argument(
        "--output",
        choices=["table", "json"],
        default="table",
        help="Formato de salida (default: table)",
    )
    parser.add_argument(
        "--budget",
        type=float,
        default=0,
        help="Presupuesto mensual en USD para alertas (default: 0 = sin límite)",
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Mostrar solo el resumen",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="API key directa (override auth.json)",
    )
    args = parser.parse_args()

    # Load API key
    if args.api_key:
        api_key = args.api_key
    else:
        api_key = load_openrouter_key(args.auth_file)

    if not api_key:
        console.print("[red]Error: No se encontró API key de OpenRouter.[/red]")
        console.print("\n[yellow]Opciones:[/yellow]")
        console.print("1. Variable de entorno: export OPENROUTER_API_KEY='sk-or-v1-xxx'")
        console.print(f"2. Archivo: {args.auth_file}")
        console.print('   {"openrouter": {"type": "api", "key": "sk-or-v1-xxx"}}')
        console.print("\n3. Parámetro: python openrouter_usage_checker.py --api-key sk-or-v1-xxx")
        console.print("\nObtén una key en: https://openrouter.ai/keys")
        return 1

    # Check key usage
    key_data = check_key_usage(api_key)

    # Try to get credits (may fail if not management key)
    credits_data = check_credits(api_key)

    if args.output == "json":
        result = {
            "key_usage": key_data,
            "credits": credits_data,
            "config": {
                "auth_file": str(args.auth_file),
                "budget": args.budget
            },
            "checked_at": datetime.now(timezone.utc).isoformat()
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        if args.summary_only:
            if "error" not in key_data:
                key_info = key_data.get("data", {})
                daily = key_info.get("usage_daily", 0)
                monthly = key_info.get("usage_monthly", 0)
                limit = key_info.get("limit")
                remaining = key_info.get("limit_remaining")

                console.print(f"\n[bold]OpenRouter:[/bold] Hoy: {format_currency(daily)} | "
                            f"Mes: {format_currency(monthly)} | "
                            f"Restante: {format_currency(remaining) if remaining else 'N/A'}")
            else:
                console.print(f"[red]Error: {key_data['error']}[/red]")
        else:
            print_rich_report(key_data, credits_data, args.budget, api_key)

    return 0


if __name__ == "__main__":
    sys.exit(main())
