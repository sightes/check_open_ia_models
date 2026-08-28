#!/usr/bin/env python3
"""
Token Usage Checker for OpenCode

Comprehensive token usage report with rich terminal UI including:
- OpenCode Go subscription quota (API)
- Historical token usage from local database
- Usage breakdown by model with efficiency analysis
- Cost projections and budget alerts
- Usage patterns by hour/day
- Session duration analysis

Usage:
    python token_usage_checker.py
    python token_usage_checker.py --output json
    python token_usage_checker.py --days 30
    python token_usage_checker.py --summary-only
    python token_usage_checker.py --budget 50
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import requests
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, BarColumn, TextColumn
from rich.columns import Columns
from rich.text import Text
from rich import box

# Default paths
DEFAULT_AUTH_FILE = Path.home() / ".local/share/opencode/auth.json"
DEFAULT_DB_FILE = Path.home() / ".local/share/opencode/opencode.db"

# API endpoints
GO_USAGE_URL = "https://opencode.ai/zen/go/v1/usage"

# Console
console = Console()


def load_auth_key(auth_file: Path, key_name: str = "opencode-go") -> str | None:
    """Load API key from auth.json file."""
    if not auth_file.exists():
        return None

    try:
        with open(auth_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError):
        return None

    if key_name in data:
        return data[key_name].get("key")

    for name, creds in data.items():
        if creds.get("type") == "api":
            return creds.get("key")

    return None


def check_go_usage(api_key: str) -> dict[str, Any]:
    """Check OpenCode Go subscription usage via API."""
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        response = requests.get(GO_USAGE_URL, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        return {"error": str(e)}


def get_database_stats(db_file: Path, days: int = 30) -> dict[str, Any]:
    """Get comprehensive stats from local OpenCode database."""
    if not db_file.exists():
        return {"error": f"Database not found at {db_file}"}

    try:
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
    except Exception as e:
        return {"error": f"Database error: {e}"}

    stats = {}

    # Total summary
    cursor.execute('''
        SELECT 
            COUNT(*) as total_sessions,
            SUM(CASE WHEN tokens_input > 0 THEN tokens_input ELSE 0 END) as total_input,
            SUM(CASE WHEN tokens_output > 0 THEN tokens_output ELSE 0 END) as total_output,
            SUM(CASE WHEN tokens_reasoning > 0 THEN tokens_reasoning ELSE 0 END) as total_reasoning,
            SUM(CASE WHEN tokens_cache_read > 0 THEN tokens_cache_read ELSE 0 END) as total_cache_read,
            SUM(CASE WHEN tokens_cache_write > 0 THEN tokens_cache_write ELSE 0 END) as total_cache_write,
            SUM(CASE WHEN cost > 0 THEN cost ELSE 0 END) as total_cost,
            MIN(time_created) as first_session,
            MAX(time_created) as last_session
        FROM session
        WHERE tokens_input IS NOT NULL
    ''')
    row = cursor.fetchone()
    stats['total'] = {
        'sessions': row[0] or 0,
        'input_tokens': row[1] or 0,
        'output_tokens': row[2] or 0,
        'reasoning_tokens': row[3] or 0,
        'cache_read': row[4] or 0,
        'cache_write': row[5] or 0,
        'cost': row[6] or 0.0,
        'first_session': row[7],
        'last_session': row[8]
    }

    # Usage by model
    cursor.execute('''
        SELECT 
            model,
            COUNT(*) as sessions,
            SUM(CASE WHEN tokens_input > 0 THEN tokens_input ELSE 0 END) as total_input,
            SUM(CASE WHEN tokens_output > 0 THEN tokens_output ELSE 0 END) as total_output,
            SUM(CASE WHEN tokens_reasoning > 0 THEN tokens_reasoning ELSE 0 END) as total_reasoning,
            SUM(CASE WHEN cost > 0 THEN cost ELSE 0 END) as total_cost,
            AVG(time_updated - time_created) as avg_duration_ms
        FROM session
        WHERE tokens_input IS NOT NULL AND tokens_input > 0
        GROUP BY model
        ORDER BY total_cost DESC
    ''')
    stats['by_model'] = []
    for row in cursor.fetchall():
        stats['by_model'].append({
            'model': row[0] or 'unknown',
            'sessions': row[1],
            'input_tokens': row[2] or 0,
            'output_tokens': row[3] or 0,
            'reasoning_tokens': row[4] or 0,
            'cost': row[5] or 0.0,
            'avg_duration_ms': row[6] or 0
        })

    # Usage by day (last N days)
    cursor.execute(f'''
        SELECT 
            date(time_created/1000, 'unixepoch', 'localtime') as day,
            COUNT(*) as sessions,
            SUM(CASE WHEN tokens_input > 0 THEN tokens_input ELSE 0 END) as total_input,
            SUM(CASE WHEN tokens_output > 0 THEN tokens_output ELSE 0 END) as total_output,
            SUM(CASE WHEN cost > 0 THEN cost ELSE 0 END) as total_cost
        FROM session
        WHERE tokens_input IS NOT NULL 
          AND time_created > (strftime('%s', 'now') - {days}*24*60*60) * 1000
        GROUP BY day
        ORDER BY day DESC
    ''')
    stats['by_day'] = []
    for row in cursor.fetchall():
        stats['by_day'].append({
            'date': row[0],
            'sessions': row[1],
            'input_tokens': row[2] or 0,
            'output_tokens': row[3] or 0,
            'cost': row[4] or 0.0
        })

    # Usage by hour (for pattern analysis)
    cursor.execute('''
        SELECT 
            CAST(strftime('%H', time_created/1000, 'unixepoch', 'localtime') AS INTEGER) as hour,
            COUNT(*) as sessions,
            SUM(CASE WHEN cost > 0 THEN cost ELSE 0 END) as total_cost
        FROM session
        WHERE tokens_input IS NOT NULL
        GROUP BY hour
        ORDER BY hour
    ''')
    stats['by_hour'] = []
    for row in cursor.fetchall():
        stats['by_hour'].append({
            'hour': row[0],
            'sessions': row[1],
            'cost': row[2] or 0.0
        })

    # Recent sessions (top 10)
    cursor.execute('''
        SELECT 
            title,
            model,
            tokens_input,
            tokens_output,
            tokens_reasoning,
            cost,
            time_created,
            time_updated
        FROM session
        WHERE tokens_input IS NOT NULL AND tokens_input > 0
        ORDER BY time_created DESC
        LIMIT 10
    ''')
    stats['recent_sessions'] = []
    for row in cursor.fetchall():
        title = row[0] or 'Sin titulo'
        model_str = row[1] or 'unknown'
        try:
            model_json = json.loads(model_str)
            model_name = model_json.get('id', model_str)
        except (json.JSONDecodeError, TypeError):
            model_name = model_str

        duration_ms = (row[7] or 0) - (row[6] or 0)
        stats['recent_sessions'].append({
            'title': title[:40],
            'model': model_name,
            'input_tokens': row[2] or 0,
            'output_tokens': row[3] or 0,
            'reasoning_tokens': row[4] or 0,
            'cost': row[5] or 0.0,
            'timestamp': row[6],
            'duration_ms': duration_ms
        })

    conn.close()
    return stats


def format_tokens(tokens: int) -> str:
    """Format token count with K/M suffixes."""
    if tokens >= 1_000_000:
        return f"{tokens/1_000_000:.2f}M"
    elif tokens >= 1_000:
        return f"{tokens/1_000:.1f}K"
    return str(tokens)


def format_duration(ms: int) -> str:
    """Format milliseconds to human readable duration."""
    if ms <= 0:
        return "N/A"
    seconds = ms / 1000
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = seconds / 60
    if minutes < 60:
        return f"{minutes:.1f}m"
    hours = minutes / 60
    return f"{hours:.1f}h"


def calculate_efficiency(input_tokens: int, output_tokens: int) -> float:
    """Calculate output/input efficiency ratio."""
    if input_tokens == 0:
        return 0.0
    return (output_tokens / input_tokens) * 100


def calculate_cost_projection(daily_costs: list[dict], days_ahead: int = 30) -> dict:
    """Project costs based on recent usage patterns."""
    if not daily_costs:
        return {'daily_avg': 0, 'monthly_proj': 0, 'yearly_proj': 0}

    total_cost = sum(d.get('cost', 0) for d in daily_costs)
    num_days = len(daily_costs)
    daily_avg = total_cost / num_days if num_days > 0 else 0

    return {
        'daily_avg': daily_avg,
        'monthly_proj': daily_avg * 30,
        'yearly_proj': daily_avg * 365,
        'period_days': num_days
    }


def get_budget_status(current_cost: float, budget: float) -> tuple[str, str]:
    """Get budget status and color."""
    if budget <= 0:
        return "sin_presupuesto", "gray"
    
    percentage = (current_cost / budget) * 100
    
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


def print_rich_report(go_data: dict[str, Any], db_stats: dict[str, Any], 
                      days: int, budget: float) -> None:
    """Print comprehensive rich UI report."""
    
    console.print()
    console.print(Panel.fit(
        "[bold cyan]REPORTE DETALLADO DE USO - OPENCODE[/bold cyan]",
        border_style="cyan"
    ))

    # Section 1: Go Quota with progress bars
    console.print()
    console.print(Panel("[bold]1. CUOTA OPENCODE GO (API)[/bold]", border_style="blue"))
    
    if "error" in go_data:
        console.print(f"[red]Error: {go_data['error']}[/red]")
    else:
        usage = go_data.get("usage", {})
        
        # Rolling (24h)
        rolling = usage.get("rolling", {})
        rolling_pct = rolling.get("percent", 0)
        rolling_status = rolling.get("status", "unknown")
        rolling_reset = rolling.get("resetsAt", "")
        
        # Weekly
        weekly = usage.get("weekly", {})
        weekly_pct = weekly.get("percent", 0)
        weekly_status = weekly.get("status", "unknown")
        weekly_reset = weekly.get("resetsAt", "")
        
        # Monthly
        monthly = usage.get("monthly", {})
        monthly_pct = monthly.get("percent", 0)
        monthly_status = monthly.get("status", "unknown")
        monthly_reset = monthly.get("resetsAt", "")
        
        # Create progress table
        quota_table = Table(show_header=True, header_style="bold", box=box.SIMPLE)
        quota_table.add_column("Periodo", style="cyan", width=12)
        quota_table.add_column("Uso", width=30)
        quota_table.add_column("Porcentaje", justify="right", width=10)
        quota_table.add_column("Reset", width=20)
        
        # Color based on percentage
        def get_color(pct: int) -> str:
            if pct < 25: return "green"
            elif pct < 50: return "yellow"
            elif pct < 75: return "dark_orange"
            else: return "red"
        
        rolling_bar = f"[{get_color(rolling_pct)}]{'█' * (rolling_pct // 5)}{'░' * (20 - rolling_pct // 5)}[/{get_color(rolling_pct)}]"
        quota_table.add_row(
            "Rolling (24h)",
            rolling_bar,
            f"[{get_color(rolling_pct)}]{rolling_pct}%[/{get_color(rolling_pct)}]",
            rolling_reset[:16] if rolling_reset else "N/A"
        )
        
        weekly_bar = f"[{get_color(weekly_pct)}]{'█' * (weekly_pct // 5)}{'░' * (20 - weekly_pct // 5)}[/{get_color(weekly_pct)}]"
        quota_table.add_row(
            "Weekly",
            weekly_bar,
            f"[{get_color(weekly_pct)}]{weekly_pct}%[/{get_color(weekly_pct)}]",
            weekly_reset[:16] if weekly_reset else "N/A"
        )
        
        monthly_bar = f"[{get_color(monthly_pct)}]{'█' * (monthly_pct // 5)}{'░' * (20 - monthly_pct // 5)}[/{get_color(monthly_pct)}]"
        quota_table.add_row(
            "Monthly",
            monthly_bar,
            f"[{get_color(monthly_pct)}]{monthly_pct}%[/{get_color(monthly_pct)}]",
            monthly_reset[:16] if monthly_reset else "N/A"
        )
        
        console.print(quota_table)

    # Section 2: Total Summary
    if "error" not in db_stats:
        total = db_stats.get("total", {})
        
        console.print()
        console.print(Panel("[bold]2. RESUMEN TOTAL[/bold]", border_style="green"))
        
        # Summary grid
        summary_table = Table(show_header=False, box=box.SIMPLE, padding=(0, 2))
        summary_table.add_column("Metrica", style="cyan", width=20)
        summary_table.add_column("Valor", width=20)
        summary_table.add_column("Metrica", style="cyan", width=20)
        summary_table.add_column("Valor", width=20)
        
        summary_table.add_row(
            "Sesiones totales", str(total.get('sessions', 0)),
            "Costo total", f"[bold yellow]${total.get('cost', 0):.4f}[/bold yellow]"
        )
        summary_table.add_row(
            "Input tokens", format_tokens(total.get('input_tokens', 0)),
            "Output tokens", format_tokens(total.get('output_tokens', 0))
        )
        summary_table.add_row(
            "Reasoning tokens", format_tokens(total.get('reasoning_tokens', 0)),
            "Cache read", format_tokens(total.get('cache_read', 0))
        )
        
        console.print(summary_table)
        
        # Budget status
        if budget > 0:
            current_cost = total.get('cost', 0)
            status, color = get_budget_status(current_cost, budget)
            remaining = max(0, budget - current_cost)
            
            console.print()
            budget_panel = f"[bold {color}]PRESUPUESTO: ${current_cost:.2f} / ${budget:.2f} ({status})[/bold {color}]\n"
            budget_panel += f"Restante: [bold {color}]${remaining:.2f}[/bold {color}]"
            console.print(Panel(budget_panel, border_style=color))

    # Section 3: Efficiency by Model
    by_model = db_stats.get("by_model", [])
    if by_model:
        console.print()
        console.print(Panel("[bold]3. EFICIENCIA POR MODELO[/bold]", border_style="magenta"))
        
        model_table = Table(show_header=True, header_style="bold", box=box.ROUNDED)
        model_table.add_column("Modelo", style="cyan", width=20)
        model_table.add_column("Sesiones", justify="right", width=8)
        model_table.add_column("Input", justify="right", width=10)
        model_table.add_column("Output", justify="right", width=10)
        model_table.add_column("Eficiencia", justify="right", width=10)
        model_table.add_column("Costo/Sesion", justify="right", width=12)
        model_table.add_column("Duracion Prom.", justify="right", width=12)
        
        for model in by_model:
            model_name = model.get('model', 'unknown')[:20]
            if model_name.startswith('{'):
                try:
                    model_json = json.loads(model.get('model', '{}'))
                    model_name = model_json.get('id', 'unknown')[:20]
                except (json.JSONDecodeError, TypeError):
                    pass
            
            efficiency = calculate_efficiency(
                model.get('input_tokens', 0),
                model.get('output_tokens', 0)
            )
            
            cost_per_session = model.get('cost', 0) / model.get('sessions', 1)
            avg_duration = format_duration(model.get('avg_duration_ms', 0))
            
            # Color efficiency
            eff_color = "green" if efficiency > 20 else "yellow" if efficiency > 10 else "red"
            
            model_table.add_row(
                model_name,
                str(model.get('sessions', 0)),
                format_tokens(model.get('input_tokens', 0)),
                format_tokens(model.get('output_tokens', 0)),
                f"[{eff_color}]{efficiency:.1f}%[/{eff_color}]",
                f"${cost_per_session:.4f}",
                avg_duration
            )
        
        console.print(model_table)

    # Section 4: Usage Patterns (by hour)
    by_hour = db_stats.get("by_hour", [])
    if by_hour:
        console.print()
        console.print(Panel("[bold]4. PATRONES DE USO (POR HORA)[/bold]", border_style="yellow"))
        
        # Find peak hours
        max_sessions = max(h.get('sessions', 0) for h in by_hour) if by_hour else 1
        
        hour_table = Table(show_header=True, header_style="bold", box=box.SIMPLE)
        hour_table.add_column("Hora", style="cyan", width=8)
        hour_table.add_column("Actividad", width=40)
        hour_table.add_column("Sesiones", justify="right", width=10)
        hour_table.add_column("Costo", justify="right", width=10)
        
        for hour_data in by_hour:
            hour = hour_data.get('hour', 0)
            sessions = hour_data.get('sessions', 0)
            cost = hour_data.get('cost', 0)
            
            # Create bar
            bar_length = int((sessions / max_sessions) * 30) if max_sessions > 0 else 0
            bar = "█" * bar_length + "░" * (30 - bar_length)
            
            # Highlight peak hours
            is_peak = sessions == max_sessions
            style = "bold green" if is_peak else ""
            
            hour_table.add_row(
                f"{hour:02d}:00",
                f"[{style}]{bar}[/{style}]" if style else bar,
                str(sessions),
                f"${cost:.4f}"
            )
        
        console.print(hour_table)
        
        # Peak hours summary
        peak_hours = [h for h in by_hour if h.get('sessions', 0) == max_sessions]
        if peak_hours:
            peak_str = ", ".join([f"{h['hour']:02d}:00" for h in peak_hours])
            console.print(f"\n[bold green]Horas pico: {peak_str}[/bold green]")

    # Section 5: Cost Projection
    by_day = db_stats.get("by_day", [])
    if by_day:
        console.print()
        console.print(Panel("[bold]5. PROYECCION DE COSTOS[/bold]", border_style="red"))
        
        projection = calculate_cost_projection(by_day)
        
        proj_table = Table(show_header=False, box=box.SIMPLE, padding=(0, 2))
        proj_table.add_column("Periodo", style="cyan", width=20)
        proj_table.add_column("Proyeccion", width=20)
        proj_table.add_column("Notas", width=30)
        
        proj_table.add_row(
            "Promedio diario",
            f"[bold]${projection['daily_avg']:.4f}[/bold]",
            f"Basado en {projection['period_days']} dias"
        )
        proj_table.add_row(
            "Proyeccion mensual",
            f"[bold yellow]${projection['monthly_proj']:.2f}[/bold yellow]",
            "30 dias"
        )
        proj_table.add_row(
            "Proyeccion anual",
            f"[bold red]${projection['yearly_proj']:.2f}[/bold red]",
            "365 dias"
        )
        
        console.print(proj_table)
        
        # Compare with budget
        if budget > 0:
            monthly_ratio = projection['monthly_proj'] / budget
            if monthly_ratio > 1:
                console.print(f"\n[red]⚠ La proyeccion mensual ({projection['monthly_proj']:.2f}) "
                            f"excede el presupuesto ({budget:.2f}) en {monthly_ratio:.1f}x[/red]")
            else:
                console.print(f"\n[green]✓ La proyeccion mensual ({projection['monthly_proj']:.2f}) "
                            f"esta dentro del presupuesto ({budget:.2f})[/green]")

    # Section 6: Daily Usage Trend
    if by_day:
        console.print()
        console.print(Panel("[bold]6. TENDENCIA DIARIA[/bold]", border_style="cyan"))
        
        daily_table = Table(show_header=True, header_style="bold", box=box.ROUNDED)
        daily_table.add_column("Fecha", style="cyan", width=12)
        daily_table.add_column("Sesiones", justify="right", width=8)
        daily_table.add_column("Input", justify="right", width=10)
        daily_table.add_column("Output", justify="right", width=10)
        daily_table.add_column("Costo", justify="right", width=10)
        daily_table.add_column("Tendencia", width=20)
        
        max_daily_cost = max(d.get('cost', 0) for d in by_day) if by_day else 1
        
        for day in by_day[:10]:  # Last 10 days
            cost = day.get('cost', 0)
            bar_length = int((cost / max_daily_cost) * 15) if max_daily_cost > 0 else 0
            bar = "█" * bar_length + "░" * (15 - bar_length)
            
            daily_table.add_row(
                day.get('date', 'N/A'),
                str(day.get('sessions', 0)),
                format_tokens(day.get('input_tokens', 0)),
                format_tokens(day.get('output_tokens', 0)),
                f"${cost:.4f}",
                bar
            )
        
        console.print(daily_table)

    # Section 7: Recent Sessions
    recent = db_stats.get("recent_sessions", [])
    if recent:
        console.print()
        console.print(Panel("[bold]7. SESIONES RECIENTES[/bold]", border_style="blue"))
        
        session_table = Table(show_header=True, header_style="bold", box=box.SIMPLE)
        session_table.add_column("Titulo", style="cyan", width=30)
        session_table.add_column("Modelo", width=15)
        session_table.add_column("Input", justify="right", width=10)
        session_table.add_column("Output", justify="right", width=10)
        session_table.add_column("Costo", justify="right", width=10)
        session_table.add_column("Duracion", justify="right", width=10)
        
        for session in recent:
            session_table.add_row(
                session.get('title', 'Sin titulo')[:28],
                session.get('model', 'N/A')[:13],
                format_tokens(session.get('input_tokens', 0)),
                format_tokens(session.get('output_tokens', 0)),
                f"${session.get('cost', 0):.4f}",
                format_duration(session.get('duration_ms', 0))
            )
        
        console.print(session_table)

    # Footer
    console.print()
    console.print(Panel(
        "[dim]OpenCode Zen no expone saldo via API. "
        "Consulta https://opencode.ai/workspace/ para ver tu saldo.[/dim]",
        border_style="dim"
    ))
    console.print()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reporte detallado de uso de tokens en OpenCode."
    )
    parser.add_argument(
        "--auth-file",
        type=Path,
        default=DEFAULT_AUTH_FILE,
        help=f"Ruta al archivo de autenticacion (default: {DEFAULT_AUTH_FILE})",
    )
    parser.add_argument(
        "--db-file",
        type=Path,
        default=DEFAULT_DB_FILE,
        help=f"Ruta a la base de datos (default: {DEFAULT_DB_FILE})",
    )
    parser.add_argument(
        "--output",
        choices=["table", "json"],
        default="table",
        help="Formato de salida (default: table)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Dias a considerar para el historial (default: 30)",
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Mostrar solo el resumen total",
    )
    parser.add_argument(
        "--budget",
        type=float,
        default=0,
        help="Presupuesto mensual en USD para alertas (default: 0 = sin limite)",
    )
    parser.add_argument(
        "--key-name",
        type=str,
        default="opencode-go",
        help="Nombre de la key en auth.json (default: opencode-go)",
    )
    args = parser.parse_args()

    # Load API key
    api_key = load_auth_key(args.auth_file, args.key_name)

    # Check Go usage
    if api_key:
        go_data = check_go_usage(api_key)
    else:
        go_data = {"error": "API key not found"}

    # Get database stats
    db_stats = get_database_stats(args.db_file, args.days)

    if args.output == "json":
        result = {
            "go_usage": go_data,
            "database_stats": db_stats,
            "config": {
                "auth_file": str(args.auth_file),
                "db_file": str(args.db_file),
                "days": args.days,
                "budget": args.budget
            },
            "checked_at": datetime.now(timezone.utc).isoformat()
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        if args.summary_only:
            if "error" not in db_stats:
                total = db_stats.get("total", {})
                console.print(f"\n[bold]Resumen:[/bold] {total.get('sessions', 0)} sesiones | "
                            f"Input: {format_tokens(total.get('input_tokens', 0))} | "
                            f"Output: {format_tokens(total.get('output_tokens', 0))} | "
                            f"Costo: ${total.get('cost', 0):.4f}")
            if "error" in go_data:
                console.print(f"[red]Go API: {go_data['error']}[/red]")
            else:
                usage = go_data.get("usage", {})
                monthly = usage.get("monthly", {})
                console.print(f"Go Monthly: {monthly.get('percent', 0)}% usado")
        else:
            print_rich_report(go_data, db_stats, args.days, args.budget)

    return 0


if __name__ == "__main__":
    sys.exit(main())
