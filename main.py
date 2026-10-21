#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TMT — Terminal Focus Timer
==========================

A lightweight, offline focus timer for the terminal.

Features
--------
* 25/5 focus and break sessions with pause/resume.
* Six color themes, eight interface languages.
* Automatic background-music discovery (pygame), loop or shuffle.
* A quote after every focus session, typed out smoothly.
* Full dashboard or minimalist one-line mode.
* Local daily statistics in ``stats.txt``.

Dependencies: colorama, pygame (pygame is used only when music is enabled).
"""

from __future__ import annotations

import argparse
import math
import os
import random
import shutil
import sys
import time
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Callable, Iterable, Sequence

# Keep pygame's import banner out of the terminal UI.
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

APP_NAME = "TMT"
APP_SUBTITLE = "Terminal Focus Timer"
VERSION = "2.0.0"

DEFAULT_WORK = 25
DEFAULT_BREAK = 5
WORK_RANGE = (1, 180)
BREAK_RANGE = (1, 60)

TICK = 0.1                    # key polling interval
TYPE_DELAY = 0.012            # quote typewriter delay per character
CARD_WIDTH = 44               # inner width of the full timer card
BAR_WIDTH = 30                # full-mode progress bar width
MUSIC_VOLUME = 0.55
AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".flac"}
EXCLUDED_DIRS = {
    ".git", ".hg", ".svn", ".venv", "venv", "env", "__pycache__",
    "build", "dist", "node_modules", ".idea", ".vscode",
}

# ---------------------------------------------------------------------------
# Paths, terminal and color handling
# ---------------------------------------------------------------------------


def app_directory() -> Path:
    """Directory of the script, or of the .exe when frozen by PyInstaller."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


BASE_DIR = app_directory()
_env_stats = os.environ.get("TMT_STATS")
STATS_PATH = Path(_env_stats).expanduser() if _env_stats else BASE_DIR / "stats.txt"


def ensure_utf8_output() -> None:
    """Allow emoji and box drawing in Windows consoles / redirected output."""
    if os.name != "nt":
        return
    for stream in (sys.stdout, sys.stderr):
        if stream is None:
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            pass


try:
    import colorama
    from colorama import Fore, Style

    HAS_COLORAMA = True
except ImportError:  # The app still works, just without color.
    class _EmptyStyle:
        def __getattr__(self, _name: str) -> str:
            return ""

    Fore = _EmptyStyle()  # type: ignore[assignment]
    Style = _EmptyStyle()  # type: ignore[assignment]
    HAS_COLORAMA = False

COLORS_ENABLED = True
RESET = Style.RESET_ALL or ""
BOLD = Style.BRIGHT or ""
DIM = Style.DIM or ""

HIDE_CURSOR = "\x1b[?25l"
SHOW_CURSOR = "\x1b[?25h"
CLEAR_SCREEN = "\x1b[2J\x1b[H"
CLEAR_LINE = "\x1b[2K"


def setup_console(no_color: bool) -> None:
    """Initialize colorama and decide whether ANSI colors should be emitted."""
    global COLORS_ENABLED

    ensure_utf8_output()
    if HAS_COLORAMA:
        try:
            colorama.just_fix_windows_console()
        except AttributeError:
            try:
                colorama.init(autoreset=False)
            except Exception:
                pass
        except Exception:
            pass

    COLORS_ENABLED = (
        sys.stdout.isatty()
        and not no_color
        and "NO_COLOR" not in os.environ
        and os.environ.get("TERM") != "dumb"
    )


def paint(text: str, *codes: str) -> str:
    """Wrap text in colorama codes and always reset afterwards."""
    if not COLORS_ENABLED or not text:
        return text
    active = [code for code in codes if code]
    if not active:
        return text
    return "".join(active) + text + RESET


# ---------------------------------------------------------------------------
# Width-aware text helpers (emoji take two terminal cells)
# ---------------------------------------------------------------------------


def display_width(text: str) -> int:
    width = 0
    for char in text:
        if char in ("\ufe0f", "\u200d") or unicodedata.combining(char):
            continue
        width += 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1
    return width


def clip_display(text: str, width: int) -> str:
    if display_width(text) <= width:
        return text
    out: list[str] = []
    used = 0
    for char in text:
        step = 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1
        if used + step > width:
            break
        out.append(char)
        used += step
    return "".join(out)


def center_display(text: str, width: int) -> str:
    free = max(0, width - display_width(text))
    left = free // 2
    return " " * left + text + " " * (free - left)


def wrap_display(text: str, width: int) -> list[str]:
    """Wrap on word boundaries while respecting visible width."""
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if display_width(candidate) <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return [clip_display(line, width) for line in lines]


def fmt_clock(seconds: float) -> str:
    total = max(0, int(seconds))
    minutes, rest = divmod(total, 60)
    return f"{minutes:02d}:{rest:02d}"


# ---------------------------------------------------------------------------
# Themes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Theme:
    key: str
    name: str
    accent: str
    highlight: str
    secondary: str
    bar: tuple[str, str, str]
    border: str
    dim: str
    error: str = Fore.LIGHTRED_EX
    success: str = Fore.LIGHTGREEN_EX


def _dim(code: str = Fore.LIGHTBLACK_EX) -> str:
    return DIM + code


THEMES: tuple[Theme, ...] = (
    Theme(
        "hacker", "Hacker Green",
        accent=Fore.GREEN, highlight=Fore.LIGHTGREEN_EX, secondary=Fore.CYAN,
        bar=(Fore.GREEN, Fore.LIGHTGREEN_EX, Fore.LIGHTGREEN_EX),
        border=Fore.GREEN, dim=_dim(),
    ),
    Theme(
        "cyberpunk", "Cyberpunk Neon",
        accent=Fore.MAGENTA, highlight=Fore.LIGHTCYAN_EX,
        secondary=Fore.LIGHTMAGENTA_EX,
        bar=(Fore.MAGENTA, Fore.LIGHTMAGENTA_EX, Fore.LIGHTCYAN_EX),
        border=Fore.LIGHTCYAN_EX, dim=_dim(),
    ),
    Theme(
        "mono", "Monochrome Classic",
        accent=Fore.WHITE, highlight=Fore.LIGHTWHITE_EX,
        secondary=Fore.LIGHTBLACK_EX,
        bar=(Fore.WHITE, Fore.LIGHTWHITE_EX, Fore.LIGHTWHITE_EX),
        border=Fore.LIGHTBLACK_EX, dim=_dim(),
    ),
    Theme(
        "sunset", "Sunset Amber",
        accent=Fore.YELLOW, highlight=Fore.LIGHTYELLOW_EX,
        secondary=Fore.LIGHTRED_EX,
        bar=(Fore.RED, Fore.YELLOW, Fore.LIGHTYELLOW_EX),
        border=Fore.YELLOW, dim=_dim(),
    ),
    Theme(
        "ocean", "Ocean Blue",
        accent=Fore.LIGHTBLUE_EX, highlight=Fore.LIGHTCYAN_EX,
        secondary=Fore.CYAN,
        bar=(Fore.BLUE, Fore.LIGHTBLUE_EX, Fore.LIGHTCYAN_EX),
        border=Fore.LIGHTBLUE_EX, dim=_dim(),
    ),
    Theme(
        "rose", "Rose Quartz",
        accent=Fore.LIGHTMAGENTA_EX, highlight=Fore.LIGHTRED_EX,
        secondary=Fore.MAGENTA,
        bar=(Fore.MAGENTA, Fore.LIGHTMAGENTA_EX, Fore.LIGHTRED_EX),
        border=Fore.LIGHTMAGENTA_EX, dim=_dim(),
    ),
)
THEME_BY_KEY = {theme.key: theme for theme in THEMES}

# ---------------------------------------------------------------------------
# Languages
# ---------------------------------------------------------------------------

LANGUAGES: tuple[tuple[str, str, str], ...] = (
    ("en", "English", "🇬🇧"),
    ("uk", "Українська", "🇺🇦"),
    ("ru", "Русский", "🇷🇺"),
    ("es", "Español", "🇪🇸"),
    ("de", "Deutsch", "🇩🇪"),
    ("fr", "Français", "🇫🇷"),
    ("it", "Italiano", "🇮🇹"),
    ("pt", "Português", "🇵🇹"),
)
LANG_KEYS = tuple(code for code, _, _ in LANGUAGES)

EN = {
    "tagline": "Deep work, one session at a time.",
    "theme_title": "Choose a color theme",
    "music_title": "Background music",
    "music_found": "Audio files found: {count}",
    "music_no_files": "No audio files found. Add .mp3, .wav, .ogg or .flac files next to main.py.",
    "music_off": "Disable music",
    "music_shuffle": "Shuffle all tracks",
    "music_loop_hint": "Selected tracks loop automatically.",
    "music_prompt": "Choose music",
    "music_unavailable": "pygame is not installed — music is disabled. Run: pip install -r requirements.txt",
    "music_start_failed": "Could not start music: {error}. Continuing without sound.",
    "setup_title": "Session setup",
    "work_prompt": "Focus duration (minutes)",
    "break_prompt": "Break duration (minutes)",
    "mode_title": "Interface mode",
    "mode_full": "Full dashboard",
    "mode_minimal": "Minimalist — digits and a mini progress bar",
    "mode_full_short": "Full",
    "mode_minimal_short": "Minimal",
    "mode_prompt": "Choose interface mode",
    "invalid_number": "“{value}” is not a whole number. Try something like {default}.",
    "out_of_range": "Please enter a value from {low} to {high}.",
    "invalid_choice": "Please choose a number from {low} to {high}.",
    "setup_summary": "Ready: {work} min focus · {break_min} min break · {mode} · Music: {music}",
    "start": "Let's focus.",
    "today": "🔥 Today: {sessions} · {minutes} of focus",
    "no_today": "🌱 No sessions today yet — a great day to begin.",
    "session_word": ("session", "sessions"),
    "minute_word": ("minute", "minutes"),
    "focus": "FOCUS",
    "break": "BREAK",
    "paused": "PAUSED",
    "done": "DONE",
    "stopped": "STOPPED",
    "session_no": "Session #{n}",
    "of": "of",
    "hint_running": "Space — pause · Q — quit",
    "hint_paused": "Space — resume · Q — quit",
    "focus_complete": "FOCUS SESSION COMPLETE",
    "break_complete": "BREAK IS OVER",
    "break_suggestion": "Take a {n}-min break — your brain needs it.",
    "back_to_work": "Back to work. You've got this.",
    "quote_heading": "A thought for you",
    "break_question": "Take a {n}-min break?",
    "next_question": "Start another session?",
    "yes_no_hint": "Enter — yes · N — no · Q — quit",
    "yes_no_hint_no": "Enter — no · Y — yes · Q — quit",
    "answer_invalid": "Please answer Y or N.",
    "stopped_message": "Stopped.",
    "farewell": "See you! 👋",
    "stats_title": "FOCUS STATISTICS",
    "stats_empty": "No completed sessions yet. Start the timer — everything will appear here!",
    "stats_date": "Date",
    "stats_sessions": "Sessions",
    "stats_minutes": "Minutes",
    "stats_chart": "Chart",
    "stats_total": "Total",
    "stats_today": "← today",
    "stats_file": "Stats file: {path}",
    "stats_broken": "Skipped malformed lines: {n}",
    "stats_saved_error": "Could not save statistics: {error}",
    "stats_read_error": "Could not read statistics: {error}",
    "min_short": "min",
    "shuffle_short": "Shuffle",
    "music_status_off": "Off",
}

UK = {
    "tagline": "Глибока робота — одна сесія за раз.",
    "theme_title": "Обери кольорову тему",
    "music_title": "Фонова музика",
    "music_found": "Знайдено аудіофайлів: {count}",
    "music_no_files": "Аудіофайлів не знайдено. Додай .mp3, .wav, .ogg або .flac поруч із main.py.",
    "music_off": "Вимкнути музику",
    "music_shuffle": "Перемішати всі треки",
    "music_loop_hint": "Обрані треки грають по колу автоматично.",
    "music_prompt": "Обери музику",
    "music_unavailable": "pygame не встановлено — музику вимкнено. Виконай: pip install -r requirements.txt",
    "music_start_failed": "Не вдалося запустити музику: {error}. Продовжуємо без звуку.",
    "setup_title": "Налаштування сесії",
    "work_prompt": "Тривалість фокусу (хвилини)",
    "break_prompt": "Тривалість перерви (хвилини)",
    "mode_title": "Режим інтерфейсу",
    "mode_full": "Повна панель",
    "mode_minimal": "Мінімалізм — лише цифри й мініпрогрес",
    "mode_full_short": "Повний",
    "mode_minimal_short": "Мінімум",
    "mode_prompt": "Обери режим інтерфейсу",
    "invalid_number": "«{value}» — не ціле число. Спробуй, наприклад, {default}.",
    "out_of_range": "Введи значення від {low} до {high}.",
    "invalid_choice": "Обери число від {low} до {high}.",
    "setup_summary": "Готово: {work} хв фокусу · {break_min} хв перерви · {mode} · Музика: {music}",
    "start": "Починаємо.",
    "today": "🔥 Сьогодні: {sessions} · {minutes} фокусу",
    "no_today": "🌱 Сьогодні ще немає сесій — чудовий день, щоб почати.",
    "session_word": ("сесія", "сесії", "сесій"),
    "minute_word": ("хвилина", "хвилини", "хвилин"),
    "focus": "ФОКУС",
    "break": "ПЕРЕРВА",
    "paused": "ПАУЗА",
    "done": "ГОТОВО",
    "stopped": "ЗУПИНЕНО",
    "session_no": "Сесія №{n}",
    "of": "з",
    "hint_running": "Пробіл — пауза · Q — вихід",
    "hint_paused": "Пробіл — продовжити · Q — вихід",
    "focus_complete": "СЕСІЮ ФОКУСУ ЗАВЕРШЕНО",
    "break_complete": "ПЕРЕРВА ЗАКІНЧИЛАСЬ",
    "break_suggestion": "Зроби перерву на {n} хв — мозку потрібне перезавантаження.",
    "back_to_work": "Повертаємося до роботи. У тебе вийде!",
    "quote_heading": "Думка для тебе",
    "break_question": "Зробити перерву на {n} хв?",
    "next_question": "Почати ще одну сесію?",
    "yes_no_hint": "Enter — так · N — ні · Q — вихід",
    "yes_no_hint_no": "Enter — ні · Y — так · Q — вихід",
    "answer_invalid": "Відповідай Y або N.",
    "stopped_message": "Зупинено.",
    "farewell": "До зустрічі! 👋",
    "stats_title": "СТАТИСТИКА ФОКУСУ",
    "stats_empty": "Ще немає завершених сесій. Запусти таймер — і все з'явиться!",
    "stats_date": "Дата",
    "stats_sessions": "Сесії",
    "stats_minutes": "Хвилини",
    "stats_chart": "Графік",
    "stats_total": "Разом",
    "stats_today": "← сьогодні",
    "stats_file": "Файл статистики: {path}",
    "stats_broken": "Пропущено пошкоджених рядків: {n}",
    "stats_saved_error": "Не вдалося зберегти статистику: {error}",
    "stats_read_error": "Не вдалося прочитати статистику: {error}",
    "min_short": "хв",
    "shuffle_short": "Перемішано",
    "music_status_off": "Вимкнено",
}

RU = {
    "tagline": "Глубокая работа — одна сессия за раз.",
    "theme_title": "Выбери цветовую тему",
    "music_title": "Фоновая музыка",
    "music_found": "Найдено аудиофайлов: {count}",
    "music_no_files": "Аудиофайлы не найдены. Добавь .mp3, .wav, .ogg или .flac рядом с main.py.",
    "music_off": "Выключить музыку",
    "music_shuffle": "Перемешать все треки",
    "music_loop_hint": "Выбранные треки повторяются автоматически.",
    "music_prompt": "Выбери музыку",
    "music_unavailable": "pygame не установлен — музыка выключена. Выполни: pip install -r requirements.txt",
    "music_start_failed": "Не удалось запустить музыку: {error}. Продолжаем без звука.",
    "setup_title": "Настройка сессии",
    "work_prompt": "Длительность фокуса (минуты)",
    "break_prompt": "Длительность перерыва (минуты)",
    "mode_title": "Режим интерфейса",
    "mode_full": "Полная панель",
    "mode_minimal": "Минимализм — только цифры и мини-прогресс",
    "mode_full_short": "Полный",
    "mode_minimal_short": "Минимум",
    "mode_prompt": "Выбери режим интерфейса",
    "invalid_number": "«{value}» — не целое число. Попробуй, например, {default}.",
    "out_of_range": "Введи значение от {low} до {high}.",
    "invalid_choice": "Выбери число от {low} до {high}.",
    "setup_summary": "Готово: {work} мин фокуса · {break_min} мин перерыва · {mode} · Музыка: {music}",
    "start": "Начинаем.",
    "today": "🔥 Сегодня: {sessions} · {minutes} фокуса",
    "no_today": "🌱 Сегодня ещё нет сессий — отличный день, чтобы начать.",
    "session_word": ("сессия", "сессии", "сессий"),
    "minute_word": ("минута", "минуты", "минут"),
    "focus": "ФОКУС",
    "break": "ПЕРЕРЫВ",
    "paused": "ПАУЗА",
    "done": "ГОТОВО",
    "stopped": "ОСТАНОВЛЕНО",
    "session_no": "Сессия №{n}",
    "of": "из",
    "hint_running": "Пробел — пауза · Q — выход",
    "hint_paused": "Пробел — продолжить · Q — выход",
    "focus_complete": "СЕССИЯ ФОКУСА ЗАВЕРШЕНА",
    "break_complete": "ПЕРЕРЫВ ЗАКОНЧЕН",
    "break_suggestion": "Сделай перерыв на {n} мин — мозгу нужна перезагрузка.",
    "back_to_work": "Возвращаемся к работе. Ты справишься!",
    "quote_heading": "Мысль для тебя",
    "break_question": "Сделать перерыв на {n} мин?",
    "next_question": "Начать ещё одну сессию?",
    "yes_no_hint": "Enter — да · N — нет · Q — выход",
    "yes_no_hint_no": "Enter — нет · Y — да · Q — выход",
    "answer_invalid": "Ответь Y или N.",
    "stopped_message": "Остановлено.",
    "farewell": "До встречи! 👋",
    "stats_title": "СТАТИСТИКА ФОКУСА",
    "stats_empty": "Пока нет завершённых сессий. Запусти таймер — и всё появится!",
    "stats_date": "Дата",
    "stats_sessions": "Сессии",
    "stats_minutes": "Минуты",
    "stats_chart": "График",
    "stats_total": "Итого",
    "stats_today": "← сегодня",
    "stats_file": "Файл статистики: {path}",
    "stats_broken": "Пропущено повреждённых строк: {n}",
    "stats_saved_error": "Не удалось сохранить статистику: {error}",
    "stats_read_error": "Не удалось прочитать статистику: {error}",
    "min_short": "мин",
    "shuffle_short": "Перемешивание",
    "music_status_off": "Выключена",
}

ES = {
    "tagline": "Trabajo profundo, una sesión a la vez.",
    "theme_title": "Elige un tema de color",
    "music_title": "Música de fondo",
    "music_found": "Archivos de audio encontrados: {count}",
    "music_no_files": "No se encontraron archivos de audio. Añade .mp3, .wav, .ogg o .flac junto a main.py.",
    "music_off": "Desactivar la música",
    "music_shuffle": "Reproducir todo en aleatorio",
    "music_loop_hint": "Las pistas seleccionadas se repiten en bucle.",
    "music_prompt": "Elige la música",
    "music_unavailable": "pygame no está instalado; la música está desactivada. Ejecuta: pip install -r requirements.txt",
    "music_start_failed": "No se pudo iniciar la música: {error}. Seguimos sin sonido.",
    "setup_title": "Configuración de la sesión",
    "work_prompt": "Duración del enfoque (minutos)",
    "break_prompt": "Duración del descanso (minutos)",
    "mode_title": "Modo de interfaz",
    "mode_full": "Panel completo",
    "mode_minimal": "Minimalista: solo dígitos y una mini barra",
    "mode_full_short": "Completo",
    "mode_minimal_short": "Mínimo",
    "mode_prompt": "Elige el modo de interfaz",
    "invalid_number": "«{value}» no es un número entero. Prueba, por ejemplo, {default}.",
    "out_of_range": "Introduce un valor entre {low} y {high}.",
    "invalid_choice": "Elige un número entre {low} y {high}.",
    "setup_summary": "Listo: {work} min de enfoque · {break_min} min de descanso · {mode} · Música: {music}",
    "start": "Vamos a concentrarnos.",
    "today": "🔥 Hoy: {sessions} · {minutes} de enfoque",
    "no_today": "🌱 Aún no hay sesiones hoy: es un gran día para empezar.",
    "session_word": ("sesión", "sesiones"),
    "minute_word": ("minuto", "minutos"),
    "focus": "ENFOQUE",
    "break": "DESCANSO",
    "paused": "PAUSA",
    "done": "HECHO",
    "stopped": "DETENIDO",
    "session_no": "Sesión n.º {n}",
    "of": "de",
    "hint_running": "Espacio — pausa · Q — salir",
    "hint_paused": "Espacio — continuar · Q — salir",
    "focus_complete": "SESIÓN DE ENFOQUE COMPLETADA",
    "break_complete": "EL DESCANSO HA TERMINADO",
    "break_suggestion": "Tómate {n} min de descanso; tu cerebro lo necesita.",
    "back_to_work": "Volvemos al trabajo. ¡Puedes con ello!",
    "quote_heading": "Una idea para ti",
    "break_question": "¿Tomar un descanso de {n} min?",
    "next_question": "¿Empezar otra sesión?",
    "yes_no_hint": "Enter — sí · N — no · Q — salir",
    "yes_no_hint_no": "Enter — no · Y — sí · Q — salir",
    "answer_invalid": "Responde Y o N.",
    "stopped_message": "Detenido.",
    "farewell": "¡Hasta luego! 👋",
    "stats_title": "ESTADÍSTICAS DE ENFOQUE",
    "stats_empty": "Aún no hay sesiones completadas. ¡Inicia el temporizador y todo aparecerá aquí!",
    "stats_date": "Fecha",
    "stats_sessions": "Sesiones",
    "stats_minutes": "Minutos",
    "stats_chart": "Gráfico",
    "stats_total": "Total",
    "stats_today": "← hoy",
    "stats_file": "Archivo de estadísticas: {path}",
    "stats_broken": "Líneas dañadas omitidas: {n}",
    "stats_saved_error": "No se pudieron guardar las estadísticas: {error}",
    "stats_read_error": "No se pudieron leer las estadísticas: {error}",
    "min_short": "min",
    "shuffle_short": "Aleatorio",
    "music_status_off": "Desactivada",
}

DE = {
    "tagline": "Konzentrierte Arbeit, eine Sitzung nach der anderen.",
    "theme_title": "Wähle ein Farbthema",
    "music_title": "Hintergrundmusik",
    "music_found": "Gefundene Audiodateien: {count}",
    "music_no_files": "Keine Audiodateien gefunden. Lege .mp3-, .wav-, .ogg- oder .flac-Dateien neben main.py ab.",
    "music_off": "Musik deaktivieren",
    "music_shuffle": "Alle Titel zufällig abspielen",
    "music_loop_hint": "Ausgewählte Titel werden automatisch wiederholt.",
    "music_prompt": "Wähle die Musik",
    "music_unavailable": "pygame ist nicht installiert – Musik ist deaktiviert. Führe aus: pip install -r requirements.txt",
    "music_start_failed": "Musik konnte nicht gestartet werden: {error}. Wir machen ohne Ton weiter.",
    "setup_title": "Sitzung einrichten",
    "work_prompt": "Fokusdauer (Minuten)",
    "break_prompt": "Pausendauer (Minuten)",
    "mode_title": "Oberflächenmodus",
    "mode_full": "Vollständiges Dashboard",
    "mode_minimal": "Minimalistisch – nur Ziffern und eine Mini-Leiste",
    "mode_full_short": "Voll",
    "mode_minimal_short": "Minimal",
    "mode_prompt": "Wähle den Oberflächenmodus",
    "invalid_number": "„{value}“ ist keine ganze Zahl. Versuche zum Beispiel {default}.",
    "out_of_range": "Bitte gib einen Wert von {low} bis {high} ein.",
    "invalid_choice": "Bitte wähle eine Zahl von {low} bis {high}.",
    "setup_summary": "Bereit: {work} Min. Fokus · {break_min} Min. Pause · {mode} · Musik: {music}",
    "start": "Los geht's.",
    "today": "🔥 Heute: {sessions} · {minutes} Fokus",
    "no_today": "🌱 Heute noch keine Sitzungen – ein guter Tag zum Anfangen.",
    "session_word": ("Sitzung", "Sitzungen"),
    "minute_word": ("Minute", "Minuten"),
    "focus": "FOKUS",
    "break": "PAUSE",
    "paused": "PAUSIERT",
    "done": "FERTIG",
    "stopped": "GESTOPPT",
    "session_no": "Sitzung #{n}",
    "of": "von",
    "hint_running": "Leertaste — Pause · Q — beenden",
    "hint_paused": "Leertaste — weiter · Q — beenden",
    "focus_complete": "FOKUSSITZUNG ABGESCHLOSSEN",
    "break_complete": "DIE PAUSE IST VORBEI",
    "break_suggestion": "Mach {n} Min. Pause – dein Gehirn braucht sie.",
    "back_to_work": "Zurück an die Arbeit. Du schaffst das!",
    "quote_heading": "Ein Gedanke für dich",
    "break_question": "{n} Min. Pause machen?",
    "next_question": "Noch eine Sitzung starten?",
    "yes_no_hint": "Enter — ja · N — nein · Q — beenden",
    "yes_no_hint_no": "Enter — nein · Y — ja · Q — beenden",
    "answer_invalid": "Bitte antworte mit Y oder N.",
    "stopped_message": "Gestoppt.",
    "farewell": "Bis später! 👋",
    "stats_title": "FOKUS-STATISTIK",
    "stats_empty": "Noch keine abgeschlossenen Sitzungen. Starte den Timer – hier erscheint alles!",
    "stats_date": "Datum",
    "stats_sessions": "Sitzungen",
    "stats_minutes": "Minuten",
    "stats_chart": "Diagramm",
    "stats_total": "Gesamt",
    "stats_today": "← heute",
    "stats_file": "Statistikdatei: {path}",
    "stats_broken": "Übersprungene fehlerhafte Zeilen: {n}",
    "stats_saved_error": "Statistik konnte nicht gespeichert werden: {error}",
    "stats_read_error": "Statistik konnte nicht gelesen werden: {error}",
    "min_short": "Min.",
    "shuffle_short": "Zufall",
    "music_status_off": "Aus",
}

FR = {
    "tagline": "Le travail profond, une session à la fois.",
    "theme_title": "Choisissez un thème de couleurs",
    "music_title": "Musique de fond",
    "music_found": "Fichiers audio trouvés : {count}",
    "music_no_files": "Aucun fichier audio trouvé. Ajoutez des .mp3, .wav, .ogg ou .flac à côté de main.py.",
    "music_off": "Désactiver la musique",
    "music_shuffle": "Lire toutes les pistes en aléatoire",
    "music_loop_hint": "Les pistes sélectionnées sont lues en boucle.",
    "music_prompt": "Choisissez la musique",
    "music_unavailable": "pygame n'est pas installé — la musique est désactivée. Exécutez : pip install -r requirements.txt",
    "music_start_failed": "Impossible de démarrer la musique : {error}. On continue sans son.",
    "setup_title": "Configuration de la session",
    "work_prompt": "Durée de concentration (minutes)",
    "break_prompt": "Durée de la pause (minutes)",
    "mode_title": "Mode d'interface",
    "mode_full": "Tableau de bord complet",
    "mode_minimal": "Minimaliste — chiffres et mini-barre",
    "mode_full_short": "Complet",
    "mode_minimal_short": "Minimal",
    "mode_prompt": "Choisissez le mode d'interface",
    "invalid_number": "« {value} » n'est pas un nombre entier. Essayez par exemple {default}.",
    "out_of_range": "Entrez une valeur entre {low} et {high}.",
    "invalid_choice": "Choisissez un nombre entre {low} et {high}.",
    "setup_summary": "Prêt : {work} min de focus · {break_min} min de pause · {mode} · Musique : {music}",
    "start": "Concentrons-nous.",
    "today": "🔥 Aujourd'hui : {sessions} · {minutes} de concentration",
    "no_today": "🌱 Aucune session aujourd'hui — c'est le bon moment pour commencer.",
    "session_word": ("session", "sessions"),
    "minute_word": ("minute", "minutes"),
    "focus": "CONCENTRATION",
    "break": "PAUSE",
    "paused": "EN PAUSE",
    "done": "TERMINÉ",
    "stopped": "ARRÊTÉ",
    "session_no": "Session n° {n}",
    "of": "sur",
    "hint_running": "Espace — pause · Q — quitter",
    "hint_paused": "Espace — reprendre · Q — quitter",
    "focus_complete": "SESSION DE CONCENTRATION TERMINÉE",
    "break_complete": "LA PAUSE EST TERMINÉE",
    "break_suggestion": "Prenez {n} min de pause — votre cerveau en a besoin.",
    "back_to_work": "Retour au travail. Vous allez y arriver !",
    "quote_heading": "Une pensée pour vous",
    "break_question": "Prendre une pause de {n} min ?",
    "next_question": "Commencer une autre session ?",
    "yes_no_hint": "Entrée — oui · N — non · Q — quitter",
    "yes_no_hint_no": "Entrée — non · Y — oui · Q — quitter",
    "answer_invalid": "Répondez par Y ou N.",
    "stopped_message": "Arrêté.",
    "farewell": "À bientôt ! 👋",
    "stats_title": "STATISTIQUES DE CONCENTRATION",
    "stats_empty": "Aucune session terminée pour l'instant. Lancez le minuteur — tout apparaîtra ici !",
    "stats_date": "Date",
    "stats_sessions": "Sessions",
    "stats_minutes": "Minutes",
    "stats_chart": "Graphique",
    "stats_total": "Total",
    "stats_today": "← aujourd'hui",
    "stats_file": "Fichier de statistiques : {path}",
    "stats_broken": "Lignes invalides ignorées : {n}",
    "stats_saved_error": "Impossible d'enregistrer les statistiques : {error}",
    "stats_read_error": "Impossible de lire les statistiques : {error}",
    "min_short": "min",
    "shuffle_short": "Aléatoire",
    "music_status_off": "Désactivée",
}

IT = {
    "tagline": "Lavoro profondo, una sessione alla volta.",
    "theme_title": "Scegli un tema di colori",
    "music_title": "Musica di sottofondo",
    "music_found": "File audio trovati: {count}",
    "music_no_files": "Nessun file audio trovato. Aggiungi .mp3, .wav, .ogg o .flac accanto a main.py.",
    "music_off": "Disattiva la musica",
    "music_shuffle": "Riproduci tutte le tracce in ordine casuale",
    "music_loop_hint": "Le tracce selezionate si ripetono in loop.",
    "music_prompt": "Scegli la musica",
    "music_unavailable": "pygame non è installato: la musica è disattivata. Esegui: pip install -r requirements.txt",
    "music_start_failed": "Impossibile avviare la musica: {error}. Continuiamo senza audio.",
    "setup_title": "Configurazione della sessione",
    "work_prompt": "Durata della concentrazione (minuti)",
    "break_prompt": "Durata della pausa (minuti)",
    "mode_title": "Modalità interfaccia",
    "mode_full": "Dashboard completa",
    "mode_minimal": "Minimalista: solo cifre e mini barra",
    "mode_full_short": "Completa",
    "mode_minimal_short": "Minimal",
    "mode_prompt": "Scegli la modalità dell'interfaccia",
    "invalid_number": "«{value}» non è un numero intero. Prova, ad esempio, {default}.",
    "out_of_range": "Inserisci un valore da {low} a {high}.",
    "invalid_choice": "Scegli un numero da {low} a {high}.",
    "setup_summary": "Pronto: {work} min di focus · {break_min} min di pausa · {mode} · Musica: {music}",
    "start": "Concentriamoci.",
    "today": "🔥 Oggi: {sessions} · {minutes} di concentrazione",
    "no_today": "🌱 Nessuna sessione oggi: è un ottimo giorno per iniziare.",
    "session_word": ("sessione", "sessioni"),
    "minute_word": ("minuto", "minuti"),
    "focus": "CONCENTRAZIONE",
    "break": "PAUSA",
    "paused": "IN PAUSA",
    "done": "FATTO",
    "stopped": "FERMATO",
    "session_no": "Sessione n. {n}",
    "of": "di",
    "hint_running": "Spazio — pausa · Q — esci",
    "hint_paused": "Spazio — riprendi · Q — esci",
    "focus_complete": "SESSIONE DI CONCENTRAZIONE COMPLETATA",
    "break_complete": "LA PAUSA È FINITA",
    "break_suggestion": "Fai una pausa di {n} min: il cervello ne ha bisogno.",
    "back_to_work": "Torniamo al lavoro. Ce la puoi fare!",
    "quote_heading": "Un pensiero per te",
    "break_question": "Fare una pausa di {n} min?",
    "next_question": "Iniziare un'altra sessione?",
    "yes_no_hint": "Invio — sì · N — no · Q — esci",
    "yes_no_hint_no": "Invio — no · Y — sì · Q — esci",
    "answer_invalid": "Rispondi Y o N.",
    "stopped_message": "Fermato.",
    "farewell": "A presto! 👋",
    "stats_title": "STATISTICHE DI CONCENTRAZIONE",
    "stats_empty": "Nessuna sessione completata. Avvia il timer: tutto apparirà qui!",
    "stats_date": "Data",
    "stats_sessions": "Sessioni",
    "stats_minutes": "Minuti",
    "stats_chart": "Grafico",
    "stats_total": "Totale",
    "stats_today": "← oggi",
    "stats_file": "File statistiche: {path}",
    "stats_broken": "Righe non valide ignorate: {n}",
    "stats_saved_error": "Impossibile salvare le statistiche: {error}",
    "stats_read_error": "Impossibile leggere le statistiche: {error}",
    "min_short": "min",
    "shuffle_short": "Casuale",
    "music_status_off": "Disattivata",
}

PT = {
    "tagline": "Trabalho profundo, uma sessão de cada vez.",
    "theme_title": "Escolha um tema de cores",
    "music_title": "Música de fundo",
    "music_found": "Arquivos de áudio encontrados: {count}",
    "music_no_files": "Nenhum arquivo de áudio encontrado. Adicione .mp3, .wav, .ogg ou .flac ao lado de main.py.",
    "music_off": "Desativar música",
    "music_shuffle": "Tocar todas em ordem aleatória",
    "music_loop_hint": "As faixas selecionadas repetem automaticamente.",
    "music_prompt": "Escolha a música",
    "music_unavailable": "pygame não está instalado — a música está desativada. Execute: pip install -r requirements.txt",
    "music_start_failed": "Não foi possível iniciar a música: {error}. Vamos continuar sem som.",
    "setup_title": "Configuração da sessão",
    "work_prompt": "Duração do foco (minutos)",
    "break_prompt": "Duração da pausa (minutos)",
    "mode_title": "Modo de interface",
    "mode_full": "Painel completo",
    "mode_minimal": "Minimalista — dígitos e mini barra",
    "mode_full_short": "Completo",
    "mode_minimal_short": "Mínimo",
    "mode_prompt": "Escolha o modo de interface",
    "invalid_number": "«{value}» não é um número inteiro. Tente algo como {default}.",
    "out_of_range": "Digite um valor de {low} a {high}.",
    "invalid_choice": "Escolha um número de {low} a {high}.",
    "setup_summary": "Pronto: {work} min de foco · {break_min} min de pausa · {mode} · Música: {music}",
    "start": "Vamos focar.",
    "today": "🔥 Hoje: {sessions} · {minutes} de foco",
    "no_today": "🌱 Nenhuma sessão hoje ainda — ótimo dia para começar.",
    "session_word": ("sessão", "sessões"),
    "minute_word": ("minuto", "minutos"),
    "focus": "FOCO",
    "break": "PAUSA",
    "paused": "PAUSADO",
    "done": "CONCLUÍDO",
    "stopped": "PARADO",
    "session_no": "Sessão #{n}",
    "of": "de",
    "hint_running": "Espaço — pausa · Q — sair",
    "hint_paused": "Espaço — continuar · Q — sair",
    "focus_complete": "SESSÃO DE FOCO CONCLUÍDA",
    "break_complete": "A PAUSA TERMINOU",
    "break_suggestion": "Faça uma pausa de {n} min — seu cérebro precisa.",
    "back_to_work": "De volta ao trabalho. Você consegue!",
    "quote_heading": "Um pensamento para você",
    "break_question": "Fazer uma pausa de {n} min?",
    "next_question": "Começar outra sessão?",
    "yes_no_hint": "Enter — sim · N — não · Q — sair",
    "yes_no_hint_no": "Enter — não · Y — sim · Q — sair",
    "answer_invalid": "Responda Y ou N.",
    "stopped_message": "Parado.",
    "farewell": "Até logo! 👋",
    "stats_title": "ESTATÍSTICAS DE FOCO",
    "stats_empty": "Nenhuma sessão concluída ainda. Inicie o timer — tudo aparecerá aqui!",
    "stats_date": "Data",
    "stats_sessions": "Sessões",
    "stats_minutes": "Minutos",
    "stats_chart": "Gráfico",
    "stats_total": "Total",
    "stats_today": "← hoje",
    "stats_file": "Arquivo de estatísticas: {path}",
    "stats_broken": "Linhas inválidas ignoradas: {n}",
    "stats_saved_error": "Não foi possível salvar as estatísticas: {error}",
    "stats_read_error": "Não foi possível ler as estatísticas: {error}",
    "min_short": "min",
    "shuffle_short": "Aleatório",
    "music_status_off": "Desativada",
}

STRINGS = {"en": EN, "uk": UK, "ru": RU, "es": ES, "de": DE, "fr": FR, "it": IT, "pt": PT}

# Fill any accidental gaps with English so the app never crashes on a label.
for _language_data in STRINGS.values():
    for _key, _value in EN.items():
        _language_data.setdefault(_key, _value)


def plural_index(lang: str, number: int) -> int:
    if lang in ("ru", "uk"):
        n10, n100 = number % 10, number % 100
        if n10 == 1 and n100 != 11:
            return 0
        if 2 <= n10 <= 4 and not 12 <= n100 <= 14:
            return 1
        return 2
    return 0 if number == 1 else 1


class Localizer:
    def __init__(self, lang: str) -> None:
        self.lang = lang if lang in STRINGS else "en"
        self.data = STRINGS[self.lang]

    def __call__(self, key: str, **kwargs: object) -> str:
        template = self.data.get(key) or EN[key]
        return template.format(**kwargs) if kwargs else template  # type: ignore[union-attr]

    def phrase(self, key: str, number: int) -> str:
        forms = self.data[key]
        index = plural_index(self.lang, number)
        return f"{number} {forms[min(index, len(forms) - 1)]}"

# ---------------------------------------------------------------------------
# Quotes (50 phrases across eight languages)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Quote:
    text: str
    author: str


QUOTES: dict[str, tuple[Quote, ...]] = {
    "en": (
        Quote("The secret of getting ahead is getting started.", "Mark Twain"),
        Quote("Simplicity is prerequisite for reliability.", "Edsger W. Dijkstra"),
        Quote("The best way to predict the future is to invent it.", "Alan Kay"),
        Quote("Focus is a matter of deciding what things you're not going to do.", "John Carmack"),
        Quote("Talk is cheap. Show me the code.", "Linus Torvalds"),
        Quote("Premature optimization is the root of all evil.", "Donald Knuth"),
        Quote("It always seems impossible until it's done.", "Nelson Mandela"),
        Quote("Stay hungry, stay foolish.", "Steve Jobs"),
    ),
    "uk": (
        Quote("Хто хоче — шукає можливості, хто не хоче — причини.", "Народна мудрість"),
        Quote("Терпіння і труд усе перетруть.", "Народна мудрість"),
        Quote("Не бійся йти повільно, бійся стояти на місці.", "Народна мудрість"),
        Quote("Успіх — це сума маленьких зусиль, що повторюються щодня.", "Роберт Кольєр"),
        Quote("Простота — запорука надійності.", "Едсгер Дейкстра"),
        Quote("Найкращий час почати — зараз.", "Народна мудрість"),
    ),
    "ru": (
        Quote("Дорогу осилит идущий.", "Народная мудрость"),
        Quote("Терпение и труд всё перетрут.", "Народная мудрость"),
        Quote("Простота — залог надёжности.", "Эдсгер Дейкстра"),
        Quote("Успех — это сумма маленьких усилий, повторяемых изо дня в день.", "Роберт Кольер"),
        Quote("Лучшее время начать — сейчас.", "Народная мудрость"),
        Quote("Глаза боятся, а руки делают.", "Народная мудрость"),
    ),
    "es": (
        Quote("La simplicidad es un requisito previo para la fiabilidad.", "Edsger W. Dijkstra"),
        Quote("El secreto para salir adelante es empezar.", "Mark Twain"),
        Quote("La disciplina es el puente entre las metas y los logros.", "Jim Rohn"),
        Quote("Nunca es tarde para ser lo que podrías haber sido.", "George Eliot"),
        Quote("El que lee mucho y anda mucho, ve mucho y sabe mucho.", "Miguel de Cervantes"),
        Quote("Cada día es una nueva oportunidad para cambiar tu vida.", "Anónimo"),
    ),
    "de": (
        Quote("Einfachheit ist die Voraussetzung für Zuverlässigkeit.", "Edsger W. Dijkstra"),
        Quote("Der Weg ist das Ziel.", "Konfuzius"),
        Quote("Wer immer tut, was er schon kann, bleibt immer das, was er schon ist.", "Henry Ford"),
        Quote("Nicht weil es schwer ist, wagen wir es nicht, sondern weil wir es nicht wagen, ist es schwer.", "Seneca"),
        Quote("Es ist nie zu spät, das zu werden, was man hätte sein können.", "George Eliot"),
        Quote("Übung macht den Meister.", "Sprichwort"),
    ),
    "fr": (
        Quote("La simplicité est la condition préalable de la fiabilité.", "Edsger W. Dijkstra"),
        Quote("Le secret pour avancer, c'est de commencer.", "Mark Twain"),
        Quote("La discipline est le pont entre les objectifs et les réalisations.", "Jim Rohn"),
        Quote("Il n'est jamais trop tard pour devenir ce que l'on aurait pu être.", "George Eliot"),
        Quote("Petit à petit, l'oiseau fait son nid.", "Proverbe français"),
        Quote("Le génie, c'est un pour cent d'inspiration et quatre-vingt-dix-neuf pour cent de transpiration.", "Thomas Edison"),
    ),
    "it": (
        Quote("La semplicità è il prerequisito dell'affidabilità.", "Edsger W. Dijkstra"),
        Quote("Il segreto per andare avanti è cominciare.", "Mark Twain"),
        Quote("La disciplina è il ponte tra gli obiettivi e i risultati.", "Jim Rohn"),
        Quote("Non è mai troppo tardi per diventare ciò che avresti potuto essere.", "George Eliot"),
        Quote("Chi va piano va sano e va lontano.", "Proverbio italiano"),
        Quote("Fatto è meglio che perfetto.", "Proverbio italiano"),
    ),
    "pt": (
        Quote("A simplicidade é o pré-requisito da confiabilidade.", "Edsger W. Dijkstra"),
        Quote("O segredo para avançar é começar.", "Mark Twain"),
        Quote("A disciplina é a ponte entre metas e realizações.", "Jim Rohn"),
        Quote("Nunca é tarde para ser o que você poderia ter sido.", "George Eliot"),
        Quote("Devagar se vai ao longe.", "Provérbio português"),
        Quote("A persistência é o caminho do êxito.", "Provérbio português"),
    ),
}


def pick_quote(lang: str, last_text: str = "") -> Quote:
    pool = QUOTES.get(lang) or QUOTES["en"]
    choices = [quote for quote in pool if quote.text != last_text] or list(pool)
    return random.choice(choices)

# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------


@dataclass
class DayStats:
    sessions: int = 0
    minutes: int = 0


def read_stats(path: Path) -> tuple[dict[date, DayStats], int, str | None]:
    """Return stats, malformed-line count and an optional read error."""
    stats: dict[date, DayStats] = {}
    broken = 0

    if not path.exists():
        return stats, 0, None

    try:
        content = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as exc:
        return stats, 0, str(exc)

    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            stamp, minutes_raw = line.split(";", 1)
            day = date.fromisoformat(stamp[:10])
            minutes = int(minutes_raw)
            if not 0 < minutes <= 24 * 60:
                raise ValueError("invalid duration")
        except (ValueError, IndexError):
            broken += 1
            continue

        entry = stats.setdefault(day, DayStats())
        entry.sessions += 1
        entry.minutes += minutes

    return stats, broken, None


def append_session(path: Path, minutes: int) -> str | None:
    """Append one completed focus session; return an error string on failure."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        is_new = not path.exists()
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            if is_new:
                handle.write("# TMT session log (ISO timestamp;minutes)\n")
            handle.write(f"{datetime.now().isoformat(timespec='seconds')};{int(minutes)}\n")
        return None
    except OSError as exc:
        return str(exc)


def today_summary(stats: dict[date, DayStats], t: Localizer) -> str:
    entry = stats.get(date.today())
    if not entry or not entry.sessions:
        return t("no_today")
    return t(
        "today",
        sessions=t.phrase("session_word", entry.sessions),
        minutes=t.phrase("minute_word", entry.minutes),
    )


def show_stats_table(theme: Theme, t: Localizer, path: Path) -> None:
    stats, broken, error = read_stats(path)
    print()
    print("  " + paint("📊  " + t("stats_title"), theme.accent, BOLD))
    print("  " + paint("─" * 56, theme.border))

    if error:
        print("  " + paint(t("stats_read_error", error=error), theme.error))

    if not stats:
        print("  " + t("stats_empty"))
        if broken:
            print("  " + paint(t("stats_broken", n=broken), theme.error))
        print("  " + paint(t("stats_file", path=path), theme.dim))
        print()
        return

    max_minutes = max(entry.minutes for entry in stats.values()) or 1
    recent = sorted(stats.items())[-14:][::-1]

    header = (
        f"{t('stats_date'):<12}{t('stats_sessions'):>9}"
        f"{t('stats_minutes'):>9}  {t('stats_chart')}"
    )
    print("  " + paint(header, theme.dim))

    for day, entry in recent:
        bar = "█" * max(1, round(entry.minutes / max_minutes * 16))
        row = f"  {day.strftime('%d.%m.%Y'):<12}{entry.sessions:>9}{entry.minutes:>9}  "
        marker = "  " + t("stats_today") if day == date.today() else ""
        print(row + paint(bar, theme.success) + paint(marker, theme.dim))

    total_sessions = sum(entry.sessions for entry in stats.values())
    total_minutes = sum(entry.minutes for entry in stats.values())
    print("  " + paint("─" * 56, theme.border))
    print(f"  {t('stats_total'):<12}{total_sessions:>9}{total_minutes:>9}")

    if broken:
        print("  " + paint(t("stats_broken", n=broken), theme.error))
    print("  " + paint(t("stats_file", path=path), theme.dim))
    print()

# ---------------------------------------------------------------------------
# Music discovery and playback
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MusicSelection:
    mode: str = "none"           # none | loop | shuffle
    track: Path | None = None


def scan_music(root: Path) -> list[Path]:
    """Recursively find audio files in the project directory."""
    tracks: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, onerror=lambda _error: None):
        dirnames[:] = sorted(
            name for name in dirnames
            if not name.startswith(".") and name.lower() not in EXCLUDED_DIRS
        )
        for filename in sorted(filenames):
            path = Path(dirpath) / filename
            if path.suffix.lower() in AUDIO_EXTENSIONS:
                tracks.append(path)
    return sorted(tracks, key=lambda item: str(item).casefold())


def track_label(path: Path) -> str:
    try:
        return path.relative_to(BASE_DIR).as_posix()
    except ValueError:
        return path.name


class MusicEngine:
    """Thin pygame.mixer wrapper; imports pygame only when music is used."""

    def __init__(self, selection: MusicSelection, tracks: Sequence[Path]) -> None:
        self.selection = selection
        self.tracks = tuple(tracks)
        self.pg = None  # type: ignore[assignment]
        self.playing = False
        self.paused = False
        self.error: str | None = None
        self._last_poll = 0.0

    def prepare(self) -> str | None:
        if self.selection.mode == "none":
            return None
        if self.selection.mode == "loop":
            if not self.selection.track or not self.selection.track.is_file():
                self.error = "file not found"
                return self.error
        elif not self.tracks:
            self.error = "no tracks"
            return self.error

        try:
            import pygame
        except ImportError:
            self.error = "missing"
            return "missing"
        except Exception as exc:  # broken native library, etc.
            self.error = str(exc)
            return self.error

        try:
            pygame.mixer.init()
            pygame.mixer.music.set_volume(MUSIC_VOLUME)
            self.pg = pygame
            probe = (
                self.selection.track
                if self.selection.mode == "loop"
                else random.choice(self.tracks)
            )
            pygame.mixer.music.load(str(probe))
        except Exception as exc:
            self.error = str(exc)
            return self.error
        return None

    def start(self) -> None:
        if self.pg is None or self.selection.mode == "none":
            return
        try:
            if self.selection.mode == "loop" and self.selection.track:
                self.pg.mixer.music.load(str(self.selection.track))
                self.pg.mixer.music.play(loops=-1)
            else:
                self._play_random()
            self.playing = True
            self.paused = False
        except Exception as exc:
            self.error = str(exc)
            self.playing = False

    def _play_random(self) -> None:
        if not self.tracks or self.pg is None:
            return
        current = self.selection.track
        choices = [path for path in self.tracks if path != current] or list(self.tracks)
        random.shuffle(choices)
        last_error: Exception | None = None
        for track in choices:
            try:
                self.pg.mixer.music.load(str(track))
                self.pg.mixer.music.play()
                self.selection = MusicSelection("shuffle", track)
                return
            except Exception as exc:
                last_error = exc
        if last_error:
            raise last_error

    def tick(self) -> None:
        """Advance shuffle playback when a track ends."""
        if self.pg is None or self.selection.mode != "shuffle":
            return
        if not self.playing or self.paused:
            return
        now = time.monotonic()
        if now - self._last_poll < 0.4:
            return
        self._last_poll = now
        try:
            if not self.pg.mixer.music.get_busy():
                self._play_random()
        except Exception as exc:
            self.error = str(exc)
            self.playing = False

    def pause(self) -> None:
        if self.pg is None or not self.playing or self.paused:
            return
        try:
            self.pg.mixer.music.pause()
            self.paused = True
        except Exception:
            pass

    def resume(self) -> None:
        if self.pg is None or not self.playing or not self.paused:
            return
        try:
            self.pg.mixer.music.unpause()
            self.paused = False
        except Exception:
            pass

    def fade_out(self, milliseconds: int = 700) -> None:
        if self.pg is not None and self.playing:
            try:
                if self.paused:
                    self.pg.mixer.music.unpause()
                self.pg.mixer.music.fadeout(milliseconds)
            except Exception:
                pass
        self.playing = False
        self.paused = False

    def stop_now(self) -> None:
        if self.pg is not None:
            try:
                self.pg.mixer.music.stop()
            except Exception:
                pass
        self.playing = False
        self.paused = False

    def disable(self) -> None:
        self.stop_now()
        if self.pg is not None:
            try:
                self.pg.mixer.quit()
            except Exception:
                pass
        self.pg = None
        self.selection = MusicSelection("none")
        self.tracks = ()

    def close(self) -> None:
        self.disable()

# ---------------------------------------------------------------------------
# Session state helpers
# ---------------------------------------------------------------------------


class QuitRequested(Exception):
    """The user asked to leave."""


class SessionCancelled(QuitRequested):
    """The active session was stopped with Q."""


QUIT_WORDS = {
    "q", "quit", "exit", "й", "выход", "вихід",
    "salir", "beenden", "quitter", "esci", "sair",
}
YES_WORDS = {"y", "yes", "да", "так", "sí", "si", "ja", "oui", "sì", "sim", "д", "н"}
NO_WORDS = {"n", "no", "нет", "ні", "nein", "non", "não", "nao", "т"}


def ask_number(
    prompt: str,
    low: int,
    high: int,
    default: int,
    t: Localizer,
    theme: Theme,
    range_key: str = "out_of_range",
) -> int:
    while True:
        try:
            raw = input(prompt).strip()
        except EOFError as exc:
            raise QuitRequested() from exc

        if not raw:
            return default
        if raw.lower() in QUIT_WORDS:
            raise QuitRequested()

        try:
            value = int(raw)
        except ValueError:
            shown = clip_display(raw, 20)
            print("  " + paint(t("invalid_number", value=shown, default=default), theme.error))
            continue

        if low <= value <= high:
            return value
        print("  " + paint(t(range_key, low=low, high=high), theme.error))


def ask_yes_no(question: str, default: bool, t: Localizer, theme: Theme) -> bool:
    hint = t("yes_no_hint") if default else t("yes_no_hint_no")
    prompt = (
        f"  {paint(question, theme.highlight)}  "
        f"{paint(hint, theme.dim)} {paint('›', theme.accent)} "
    )
    while True:
        try:
            raw = input(prompt).strip().lower()
        except EOFError as exc:
            raise QuitRequested() from exc

        if not raw:
            return default
        if raw in QUIT_WORDS:
            raise QuitRequested()
        if raw in YES_WORDS:
            return True
        if raw in NO_WORDS:
            return False
        print("  " + paint(t("answer_invalid"), theme.error))


def play_beep(kind: str, silent: bool) -> None:
    if silent:
        return
    if os.name == "nt":
        try:
            import winsound

            notes = (
                [(784, 130), (988, 130), (1319, 280)]
                if kind == "focus"
                else [(880, 110), (1175, 230)]
            )
            for frequency, duration in notes:
                winsound.Beep(frequency, duration)
            return
        except Exception:
            pass
    try:
        sys.stdout.write("\a" if kind == "focus" else "\a\a")
        sys.stdout.flush()
    except OSError:
        pass


def type_quote(quote: Quote, theme: Theme, t: Localizer) -> None:
    """Print a quote with a smooth character-by-character reveal."""
    columns = shutil.get_terminal_size((80, 24)).columns
    width = max(12, min(columns - 6, 72))
    text = f"“{quote.text}”"
    lines = wrap_display(text, width)
    animate = sys.stdout.isatty()

    print()
    print("  " + paint("✨  " + t("quote_heading"), theme.accent, BOLD))
    print()

    color = theme.highlight if COLORS_ENABLED else ""
    reset = RESET if COLORS_ENABLED else ""
    indent = "    "
    try:
        for line in lines:
            if animate:
                sys.stdout.write(indent + color)
                for char in line:
                    sys.stdout.write(char)
                    sys.stdout.flush()
                    time.sleep(TYPE_DELAY)
                sys.stdout.write(reset + "\n")
            else:
                print(indent + paint(line, theme.highlight))
    except KeyboardInterrupt:
        try:
            sys.stdout.write(reset + "\n")
        except OSError:
            pass
        raise

    author = clip_display(f"— {quote.author}", width)
    print("  " + " " * max(0, 4 + width - display_width(author)) + paint(author, theme.dim))
    print()


def show_notice(theme: Theme, title: str, lines: Sequence[str]) -> None:
    columns = shutil.get_terminal_size((80, 24)).columns
    inner = max(16, min(46, columns - 4))
    content = inner - 2
    border_color = theme.border
    print()
    print(
        "  " + paint("╭", border_color)
        + paint("─" * inner, border_color)
        + paint("╮", border_color)
    )

    title = clip_display(title, content)
    left = max(0, (content - display_width(title)) // 2)
    right = max(0, content - display_width(title) - left)
    print(
        "  " + paint("│", border_color) + " " + " " * left
        + paint(title, theme.accent, BOLD) + " " * right + " "
        + paint("│", border_color)
    )
    print(
        "  " + paint("│", border_color) + " " + " " * content + " "
        + paint("│", border_color)
    )

    for raw_line in lines:
        for line in wrap_display(raw_line, content):
            padding = " " * max(0, content - display_width(line))
            print(
                "  " + paint("│", border_color) + " " + line + padding + " "
                + paint("│", border_color)
            )

    print(
        "  " + paint("╰", border_color)
        + paint("─" * inner, border_color)
        + paint("╯", border_color)
    )

# ---------------------------------------------------------------------------
# Non-blocking keyboard input
# ---------------------------------------------------------------------------


class KeyReader:
    def __init__(self) -> None:
        self.ok = False
        self._saved_attrs = None
        self._termios = None
        self._fd = -1
        if not sys.stdin.isatty():
            return
        try:
            if os.name == "nt":
                import msvcrt

                self._msvcrt = msvcrt
                self.ok = True
            else:
                import termios
                import tty

                self._fd = sys.stdin.fileno()
                self._termios = termios
                self._saved_attrs = termios.tcgetattr(self._fd)
                tty.setcbreak(self._fd)
                self.ok = True
        except Exception:
            self.ok = False

    def poll(self) -> str | None:
        if not self.ok:
            return None
        try:
            if os.name == "nt":
                if not self._msvcrt.kbhit():
                    return None
                char = self._msvcrt.getwch()
                if char in ("\x00", "\xe0"):
                    self._msvcrt.getwch()
                    return None
                return char.lower()
            import select

            ready, _, _ = select.select([sys.stdin], [], [], 0)
            if not ready:
                return None
            return sys.stdin.read(1).lower()
        except Exception:
            return None

    def close(self) -> None:
        if self._saved_attrs is not None and self._termios is not None:
            try:
                self._termios.tcsetattr(self._fd, self._termios.TCSADRAIN, self._saved_attrs)
            except Exception:
                pass
            self._saved_attrs = None


BIG_FONT: dict[str, tuple[str, ...]] = {
    "0": ("█▀▀█", "█  █", "█  █", "█  █", "█▄▄█"),
    "1": ("  █ ", "  █ ", "  █ ", "  █ ", "  █ "),
    "2": ("█▀▀█", "   █", "█▀▀█", "█   ", "█▄▄█"),
    "3": ("█▀▀█", "   █", "█▀▀█", "   █", "█▄▄█"),
    "4": ("█  █", "█  █", "█▄▄█", "   █", "   █"),
    "5": ("█▄▄█", "█   ", "█▀▀█", "   █", "█▄▄█"),
    "6": ("█▄▄█", "█   ", "█▀▀█", "█  █", "█▄▄█"),
    "7": ("█▀▀█", "   █", "   █", "   █", "   █"),
    "8": ("█▀▀█", "█  █", "█▀▀█", "█  █", "█▄▄█"),
    "9": ("█▀▀█", "█  █", "█▄▄█", "   █", "█▄▄█"),
    ":": ("    ", " ██ ", "    ", " ██ ", "    "),
}
PARTIAL_BLOCKS = " ▏▎▍▌▋▊▉█"


def build_time_art(text: str) -> list[str]:
    rows = [""] * 5
    for index, char in enumerate(text):
        glyph = BIG_FONT.get(char, BIG_FONT["0"])
        for row in range(5):
            rows[row] += (" " if index else "") + glyph[row]
    return rows


def bar_cells(
    fraction: float,
    width: int,
    theme: Theme,
    *,
    muted: bool = False,
) -> list[tuple[str, tuple[str, ...]]]:
    """Return (character, styles) pairs so visible width stays predictable."""
    fraction = min(max(fraction, 0.0), 1.0)
    filled = fraction * width
    full = int(filled)
    rest = filled - full
    cells: list[tuple[str, tuple[str, ...]]] = []

    for index in range(width):
        if index < full:
            char = "█"
        elif index == full and rest > 0.03:
            char = PARTIAL_BLOCKS[min(7, max(1, int(rest * 8)))]
        else:
            char = "░"

        styles: tuple[str, ...] = ()
        if COLORS_ENABLED:
            if char == "░":
                styles = (theme.dim,)
            elif muted:
                styles = (theme.dim,)
            else:
                band = theme.bar[min(2, int(index / max(width - 1, 1) * 3))]
                styles = (band, BOLD if index == full else "")
        cells.append((char, styles))
    return cells


def render_cells(cells: Sequence[tuple[str, tuple[str, ...]]]) -> str:
    return "".join(paint(text, *styles) for text, styles in cells)


def hard_fit(
    cells: Sequence[tuple[str, tuple[str, ...]]],
    width: int,
) -> list[tuple[str, tuple[str, ...]]]:
    """Trim segments without breaking ANSI sequences (segments are plain)."""
    result: list[tuple[str, tuple[str, ...]]] = []
    remaining = width
    for text, styles in cells:
        if remaining <= 0:
            break
        cut = clip_display(text, remaining)
        result.append((cut, styles))
        remaining -= display_width(cut)
    return result


class TimerSession:
    """One focus or break countdown with a full or minimalist display."""

    def __init__(
        self,
        kind: str,
        seconds: float,
        theme: Theme,
        t: Localizer,
        *,
        session_no: int = 0,
        compact: bool = False,
    ) -> None:
        self.kind = kind
        self.is_focus = kind == "focus"
        self.total = max(1.0, float(seconds))
        self.theme = theme
        self.t = t
        self.session_no = session_no
        self.rich = sys.stdout.isatty()
        self.term_cols, self.term_rows = shutil.get_terminal_size((80, 24))
        self.compact = compact or self.term_cols < 56 or self.term_rows < 18

        self._paused = False
        self._cancelled = False
        self._completed = False
        self._prev_lines = 0
        self._last_state: tuple[int, bool, bool, bool] | None = None
        self._last_compact_width = 0

    # -- public API ---------------------------------------------------------

    def run(
        self,
        on_tick: Callable[[], None] | None = None,
        on_pause: Callable[[], None] | None = None,
        on_resume: Callable[[], None] | None = None,
    ) -> float:
        if not self.rich:
            return self._run_plain(on_tick)

        keys = KeyReader()
        started = time.monotonic()
        paused_at: float | None = None
        paused_total = 0.0
        elapsed = 0.0

        self._enter_screen()
        try:
            while True:
                key = keys.poll()
                if key:
                    if key in ("q", "й"):
                        self._cancelled = True
                        self._render(elapsed)
                        raise SessionCancelled()
                    if key in (" ", "p", "з"):
                        if paused_at is None:
                            paused_at = time.monotonic()
                            if on_pause:
                                on_pause()
                        else:
                            paused_total += time.monotonic() - paused_at
                            paused_at = None
                            if on_resume:
                                on_resume()

                now = time.monotonic()
                reference = paused_at if paused_at is not None else now
                elapsed = min(max(reference - started - paused_total, 0.0), self.total)
                self._paused = paused_at is not None
                self._completed = elapsed >= self.total

                if on_tick:
                    on_tick()

                state = (math.ceil(self.total - elapsed), self._paused, self._completed, self._cancelled)
                if state != self._last_state:
                    self._render(elapsed)
                    self._last_state = state

                if self._completed:
                    break
                time.sleep(TICK)
        except KeyboardInterrupt:
            self._cancelled = True
            self._render(elapsed)
            raise
        finally:
            keys.close()
            self._leave_screen()

        return elapsed

    def _run_plain(self, on_tick: Callable[[], None] | None = None) -> float:
        minutes = max(1, int(round(self.total / 60)))
        label = self.t("focus") if self.is_focus else self.t("break")
        print(f"  {self._icon()} {label} · {minutes} {self.t('min_short')}")
        started = time.monotonic()
        while True:
            remaining = self.total - (time.monotonic() - started)
            if remaining <= 0:
                break
            if on_tick:
                on_tick()
            time.sleep(min(0.5, remaining))
        print(f"  ✅ {self.t('done')}")
        return self.total

    # -- screen management --------------------------------------------------

    def _enter_screen(self) -> None:
        try:
            if not self.compact:
                sys.stdout.write(CLEAR_SCREEN + "\n" + HIDE_CURSOR)
                sys.stdout.flush()
        except OSError:
            pass

    def _leave_screen(self) -> None:
        try:
            if self.compact:
                sys.stdout.write("\n")
            else:
                sys.stdout.write(SHOW_CURSOR)
            sys.stdout.flush()
        except OSError:
            pass

    def _render(self, elapsed: float) -> None:
        fraction = min(elapsed / self.total, 1.0) if self.total else 1.0
        remaining = max(0.0, self.total - elapsed)
        if self.compact:
            self._render_compact(fraction, remaining)
        else:
            self._render_full(fraction, remaining, elapsed)

    # -- full dashboard -----------------------------------------------------

    def _phase_label(self) -> tuple[str, tuple[str, ...]]:
        if self._completed:
            return "✅  " + self.t("done"), (self.theme.success, BOLD)
        if self._cancelled:
            return "⏹  " + self.t("stopped"), (self.theme.dim, BOLD)
        if self._paused:
            return "⏸  " + self.t("paused"), (self.theme.dim, BOLD)
        if self.is_focus:
            return "🍅  " + self.t("focus"), (self.theme.accent, BOLD)
        return "☕  " + self.t("break"), (self.theme.secondary, BOLD)

    def _header_right(self) -> str:
        if self.is_focus:
            return self.t("session_no", n=self.session_no)
        return self.t("break")

    def _full_row(
        self,
        cells: Sequence[tuple[str, tuple[str, ...]]],
        align: str = "left",
    ) -> str:
        cells = hard_fit(cells, CARD_WIDTH)
        used = sum(display_width(text) for text, _ in cells)
        free = max(0, CARD_WIDTH - used)
        left = free // 2 if align == "center" else free if align == "right" else 0
        body = (
            " " * left
            + render_cells(cells)
            + " " * (free - left)
        )
        return paint("│ ", self.theme.border) + body + paint(" │", self.theme.border)

    def _full_border(self, kind: str) -> str:
        left, right = {
            "top": ("╭", "╮"),
            "mid": ("├", "┤"),
            "bottom": ("╰", "╯"),
        }[kind]
        return paint(left + "─" * (CARD_WIDTH + 2) + right, self.theme.border)

    def _build_full(self, fraction: float, remaining: float, elapsed: float) -> list[str]:
        clock = fmt_clock(math.ceil(remaining - 1e-6))
        accent = self.theme.accent if self.is_focus else self.theme.secondary
        muted = self._paused or self._cancelled

        rows: list[str] = [self._full_border("top")]

        left = [
            ("🎯  ", ()),
            (APP_NAME, (accent, BOLD)),
            (" · FOCUS TIMER", (self.theme.dim,)),
        ]
        left_width = sum(display_width(text) for text, _ in left)
        right_text = clip_display(self._header_right(), max(0, CARD_WIDTH - left_width - 1))
        gap = max(1, CARD_WIDTH - left_width - display_width(right_text))
        rows.append(
            self._full_row(
                left + [(" " * gap, ()), (right_text, (self.theme.dim,))]
            )
        )
        rows.append(self._full_border("mid"))
        rows.append(self._full_row([]))
        rows.append(self._full_row([self._phase_label()], align="center"))

        if self._completed:
            row_styles = [(self.theme.success, BOLD)] * 5
        elif muted:
            row_styles = [(self.theme.dim, BOLD)] * 5
        else:
            row_styles = [
                (self.theme.bar[0], BOLD),
                (self.theme.bar[0], BOLD),
                (self.theme.bar[1], BOLD),
                (self.theme.bar[2], BOLD),
                (self.theme.bar[2], BOLD),
            ]
        for art, styles in zip(build_time_art(clock), row_styles):
            rows.append(self._full_row([(art, styles)], align="center"))

        rows.append(self._full_row([]))

        percent = min(100, int(fraction * 100))
        cells = bar_cells(fraction, BAR_WIDTH, self.theme, muted=muted)
        cells.append((f"  {percent:3d}%", (self.theme.highlight, BOLD)))
        rows.append(self._full_row(cells, align="center"))

        elapsed_clock = fmt_clock(elapsed)
        total_clock = fmt_clock(self.total)
        info = f"{elapsed_clock} {self.t('of')} {total_clock}"
        rows.append(self._full_row([(info, (self.theme.dim,))], align="center"))
        rows.append(self._full_border("bottom"))

        if self._completed or self._cancelled:
            hint = ""
        elif self._paused:
            hint = self.t("hint_paused")
        else:
            hint = self.t("hint_running")
        rows.append(paint(center_display(hint, 48), self.theme.dim))

        indent = " " * max(2, (self.term_cols - 48) // 2)
        return [indent + row for row in rows]

    def _render_full(self, fraction: float, remaining: float, elapsed: float) -> None:
        lines = self._build_full(fraction, remaining, elapsed)
        buffer: list[str] = []
        if self._prev_lines:
            buffer.append(f"\x1b[{self._prev_lines}A")
        for line in lines:
            buffer.append(CLEAR_LINE + line + "\n")
        try:
            sys.stdout.write("".join(buffer))
            sys.stdout.flush()
        except OSError:
            pass
        self._prev_lines = len(lines)

    # -- minimalist mode ----------------------------------------------------

    def _compact_icon(self) -> str:
        if self._completed:
            return "✅"
        if self._cancelled:
            return "⏹"
        if self._paused:
            return "⏸"
        return "🍅" if self.is_focus else "☕"

    def _render_compact(self, fraction: float, remaining: float) -> None:
        clock = fmt_clock(math.ceil(remaining - 1e-6))
        percent = min(100, int(fraction * 100))
        prefix = f"  {self._compact_icon()} {clock}"
        suffix = f"  {percent:3d}% "
        available = self.term_cols - display_width(prefix) - display_width(suffix) - 1
        if available < 6:
            suffix = "  "
            available = self.term_cols - display_width(prefix) - display_width(suffix) - 1
        bar_width = max(1, min(22, available))
        muted = self._paused or self._cancelled or self._completed

        cells = bar_cells(fraction, bar_width, self.theme, muted=muted)
        line = (
            paint(prefix, self.theme.accent, BOLD)
            + " "
            + render_cells(cells)
            + paint(suffix, self.theme.dim)
        )
        visible = display_width(prefix) + 1 + bar_width + display_width(suffix)
        padding = " " * max(0, self._last_compact_width - visible)
        try:
            sys.stdout.write("\r" + line + padding)
            sys.stdout.flush()
        except OSError:
            pass
        self._last_compact_width = max(visible, self._last_compact_width)

    def _icon(self) -> str:
        return "🍅" if self.is_focus else "☕"

# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------


class ConfigError(Exception):
    """Invalid command-line configuration."""


def print_brand(theme: Theme, subtitle: str | None = None) -> None:
    print()
    print(
        "  " + paint(f"🍅  {APP_NAME}", theme.accent, BOLD)
        + paint(f"  ·  {APP_SUBTITLE.upper()}", theme.highlight)
    )
    if subtitle:
        print("  " + paint(subtitle, theme.dim))


def print_rule(theme: Theme, width: int = 56) -> None:
    print("  " + paint("─" * width, theme.border))


def choose_language(theme: Theme) -> str:
    print()
    print("  " + paint("🌍  Choose language", theme.accent, BOLD))
    print("  " + paint("Мова · Язык · Idioma · Sprache · Langue · Lingua · Idioma", theme.dim))
    print()
    for index, (code, name, flag) in enumerate(LANGUAGES, 1):
        print(f"  {paint(str(index), theme.dim)}  {name} {flag}")
    print()
    prompt = (
        f"  {paint('Select', theme.highlight)} {paint('[1]', theme.dim)} "
        f"{paint('›', theme.accent)} "
    )
    choice = ask_number(prompt, 1, len(LANGUAGES), 1, Localizer("en"), theme, "invalid_choice")
    return LANGUAGES[choice - 1][0]


def choose_theme(t: Localizer, base_theme: Theme) -> Theme:
    print()
    print("  " + paint("🎨  " + t("theme_title"), base_theme.accent, BOLD))
    print()
    for index, theme in enumerate(THEMES, 1):
        name = theme.name.ljust(20)
        print(
            f"  {paint(str(index), base_theme.dim)}  "
            f"{paint(name, theme.accent, BOLD)} {paint('████████', theme.highlight)}"
        )
    print()
    prompt = (
        f"  {paint(t('theme_title'), base_theme.highlight)}  "
        f"{paint('[1]', base_theme.dim)} {paint('›', base_theme.accent)} "
    )
    choice = ask_number(prompt, 1, len(THEMES), 1, t, base_theme, "invalid_choice")
    return THEMES[choice - 1]


def choose_music(t: Localizer, theme: Theme, tracks: Sequence[Path]) -> MusicSelection:
    print()
    print("  " + paint("🎵  " + t("music_title"), theme.accent, BOLD))
    if not tracks:
        print("  " + paint(t("music_no_files"), theme.dim))
        return MusicSelection("none")

    print("  " + paint(t("music_found", count=len(tracks)), theme.dim))
    print("  " + paint(t("music_loop_hint"), theme.dim))
    print()
    print(f"  {paint('0', theme.dim)}  {t('music_off')}")
    label_width = max(8, theme_width() - 8)
    for index, path in enumerate(tracks, 1):
        print(f"  {paint(str(index), theme.dim)}  {clip_display(track_label(path), label_width)}")

    shuffle_index = len(tracks) + 1 if len(tracks) > 1 else None
    if shuffle_index:
        print(f"  {paint(str(shuffle_index), theme.dim)}  {t('music_shuffle')}")
    print()

    high = shuffle_index or len(tracks)
    prompt = (
        f"  {paint(t('music_prompt'), theme.highlight)}  "
        f"{paint('[0]', theme.dim)} {paint('›', theme.accent)} "
    )
    choice = ask_number(prompt, 0, high, 0, t, theme, "invalid_choice")
    if choice == 0:
        return MusicSelection("none")
    if shuffle_index and choice == shuffle_index:
        return MusicSelection("shuffle")
    return MusicSelection("loop", tracks[choice - 1])


def theme_width() -> int:
    return shutil.get_terminal_size((80, 24)).columns


def resolve_cli_music(raw: str, tracks: Sequence[Path]) -> MusicSelection:
    value = raw.strip()
    lower = value.lower()
    if lower in ("off", "none", "0"):
        return MusicSelection("none")
    if lower in ("shuffle", "random"):
        if not tracks:
            raise ConfigError("No audio files found for shuffle playback.")
        return MusicSelection("shuffle")
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    if not path.is_file():
        raise ConfigError(f"Music file not found: {path}")
    if path.suffix.lower() not in AUDIO_EXTENSIONS:
        raise ConfigError(f"Unsupported audio format: {path.suffix or '(none)'}")
    return MusicSelection("loop", path)


def music_status(selection: MusicSelection, t: Localizer) -> str:
    if selection.mode == "loop" and selection.track:
        return selection.track.name
    if selection.mode == "shuffle":
        return t("shuffle_short")
    return t("music_status_off")


class App:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.lang = args.lang or "en"
        self.t = Localizer(self.lang)
        self.theme = THEME_BY_KEY.get(args.theme or "", THEMES[0])
        self.work: int | None = args.work
        self.break_min: int | None = args.break_min
        self.compact = bool(args.minimal)
        self.selection = MusicSelection("none")
        self.tracks: list[Path] = []
        self.engine: MusicEngine | None = None
        self.last_quote = ""

    # -- main flow ----------------------------------------------------------

    def run(self) -> int:
        try:
            print_brand(self.theme)
            if not self.args.lang:
                self.lang = choose_language(self.theme)
                self.t = Localizer(self.lang)
            if not self.args.theme:
                self.theme = choose_theme(self.t, self.theme)

            self._print_header()
            stats, broken, error = read_stats(STATS_PATH)
            self._print_today(stats, broken, error)

            if self.args.music is None or self.args.music.strip().lower() in ("shuffle", "random"):
                self.tracks = scan_music(BASE_DIR)
            self._setup_music()
            self._setup_session()
            self._print_setup_summary()

            self._loop()
        except (QuitRequested, KeyboardInterrupt):
            if self.engine:
                self.engine.stop_now()
            if COLORS_ENABLED:
                sys.stdout.write(RESET)
            print()
            print("  " + paint(self.t("stopped_message"), self.theme.dim))
        finally:
            if self.engine:
                self.engine.stop_now()
                self.engine.close()

        self._farewell()
        return 0

    def _print_header(self) -> None:
        print()
        print(
            "  " + paint(f"🍅  {APP_NAME}", self.theme.accent, BOLD)
            + paint(f"  ·  {APP_SUBTITLE.upper()}", self.theme.highlight)
        )
        print("  " + paint(self.t("tagline"), self.theme.dim))
        print_rule(self.theme)

    def _print_today(self, stats: dict[date, DayStats], broken: int, error: str | None) -> None:
        print("  " + paint(today_summary(stats, self.t), self.theme.highlight))
        if error:
            print("  " + paint(self.t("stats_read_error", error=error), self.theme.error))
        if broken:
            print("  " + paint(self.t("stats_broken", n=broken), self.theme.error))
        print()

    def _setup_music(self) -> None:
        if self.args.music is not None:
            try:
                self.selection = resolve_cli_music(self.args.music, self.tracks)
            except ConfigError as exc:
                raise ConfigError(str(exc))
        else:
            self.selection = choose_music(self.t, self.theme, self.tracks)

        self.engine = MusicEngine(self.selection, self.tracks)
        error = self.engine.prepare()
        if error:
            if error == "missing":
                message = self.t("music_unavailable")
            elif error == "no tracks":
                message = self.t("music_no_files")
            else:
                message = self.t("music_start_failed", error=error)
            print("  " + paint(message, self.theme.error))
            self.engine.disable()
            self.selection = MusicSelection("none")

    def _setup_session(self) -> None:
        print("  " + paint("⚙️  " + self.t("setup_title"), self.theme.accent, BOLD))
        print()

        if self.work is None:
            prompt = (
                f"  {paint('🍅  ' + self.t('work_prompt'), self.theme.highlight)}  "
                f"{paint(f'({WORK_RANGE[0]}–{WORK_RANGE[1]})', self.theme.dim)} "
                f"{paint(f'[{DEFAULT_WORK}]', self.theme.success)} "
                f"{paint('›', self.theme.accent)} "
            )
            self.work = ask_number(
                prompt, WORK_RANGE[0], WORK_RANGE[1], DEFAULT_WORK, self.t, self.theme
            )

        if self.break_min is None:
            prompt = (
                f"  {paint('☕  ' + self.t('break_prompt'), self.theme.highlight)}  "
                f"{paint(f'({BREAK_RANGE[0]}–{BREAK_RANGE[1]})', self.theme.dim)} "
                f"{paint(f'[{DEFAULT_BREAK}]', self.theme.success)} "
                f"{paint('›', self.theme.accent)} "
            )
            self.break_min = ask_number(
                prompt, BREAK_RANGE[0], BREAK_RANGE[1], DEFAULT_BREAK, self.t, self.theme
            )

        if not self.args.minimal:
            print()
            print("  " + paint("🖥️  " + self.t("mode_title"), self.theme.accent, BOLD))
            print(f"  {paint('1', self.theme.dim)}  {self.t('mode_full')}")
            print(f"  {paint('2', self.theme.dim)}  {self.t('mode_minimal')}")
            prompt = (
                f"  {paint(self.t('mode_prompt'), self.theme.highlight)}  "
                f"{paint('[1]', self.theme.dim)} {paint('›', self.theme.accent)} "
            )
            choice = ask_number(prompt, 1, 2, 1, self.t, self.theme, "invalid_choice")
            self.compact = choice == 2

    def _print_setup_summary(self) -> None:
        mode = self.t("mode_minimal_short") if self.compact else self.t("mode_full_short")
        print()
        print(
            "  " + paint(
                "✅  " + self.t(
                    "setup_summary",
                    work=self.work,
                    break_min=self.break_min,
                    mode=mode,
                    music=music_status(self.selection, self.t),
                ),
                self.theme.success,
                BOLD,
            )
        )
        print("  " + paint(self.t("start"), self.theme.accent, BOLD))
        if sys.stdout.isatty():
            time.sleep(0.45)
        print()

    def _loop(self) -> None:
        session_no = 1
        while True:
            self._run_focus(session_no)
            self._celebrate_focus()
            if ask_yes_no(
                self.t("break_question", n=self.break_min),
                True,
                self.t,
                self.theme,
            ):
                self._run_break()
                self._celebrate_break()
            if not ask_yes_no(self.t("next_question"), True, self.t, self.theme):
                break
            session_no += 1

    def _run_focus(self, session_no: int) -> None:
        if self.engine:
            self.engine.start()
        session = TimerSession(
            "focus",
            (self.work or DEFAULT_WORK) * 60,
            self.theme,
            self.t,
            session_no=session_no,
            compact=self.compact,
        )
        try:
            session.run(
                on_tick=self.engine.tick if self.engine else None,
                on_pause=self.engine.pause if self.engine else None,
                on_resume=self.engine.resume if self.engine else None,
            )
        except BaseException:
            if self.engine:
                self.engine.stop_now()
            raise
        if self.engine:
            self.engine.fade_out()

    def _run_break(self) -> None:
        session = TimerSession(
            "break",
            (self.break_min or DEFAULT_BREAK) * 60,
            self.theme,
            self.t,
            compact=self.compact,
        )
        session.run()

    def _celebrate_focus(self) -> None:
        error = append_session(STATS_PATH, self.work or DEFAULT_WORK)
        if error:
            print("  " + paint(self.t("stats_saved_error", error=error), self.theme.error))

        stats, broken, read_error = read_stats(STATS_PATH)
        if read_error:
            print("  " + paint(self.t("stats_read_error", error=read_error), self.theme.error))
        show_notice(
            self.theme,
            "🎉  " + self.t("focus_complete"),
            [
                self.t("break_suggestion", n=self.break_min),
                today_summary(stats, self.t),
            ],
        )
        play_beep("focus", self.args.silent)

        quote = pick_quote(self.lang, self.last_quote)
        self.last_quote = quote.text
        type_quote(quote, self.theme, self.t)

    def _celebrate_break(self) -> None:
        play_beep("break", self.args.silent)
        show_notice(
            self.theme,
            "🚀  " + self.t("break_complete"),
            [self.t("back_to_work")],
        )

    def _farewell(self) -> None:
        stats, broken, error = read_stats(STATS_PATH)
        print()
        print("  " + paint(today_summary(stats, self.t), self.theme.highlight))
        if error:
            print("  " + paint(self.t("stats_read_error", error=error), self.theme.error))
        if broken:
            print("  " + paint(self.t("stats_broken", n=broken), self.theme.error))
        print("  " + paint(self.t("farewell"), self.theme.accent, BOLD))
        print()

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="🍅 TMT — a lightweight terminal focus timer.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python main.py\n"
            "  python main.py --lang en --theme cyberpunk --work 50 --break 10\n"
            "  python main.py --music shuffle --minimal --silent\n"
            "  python main.py --stats --lang de\n"
        ),
    )
    parser.add_argument("--lang", choices=LANG_KEYS, help="interface language")
    parser.add_argument(
        "--theme", choices=tuple(theme.key for theme in THEMES), help="color theme"
    )
    parser.add_argument(
        "-w", "--work", type=int, metavar="MIN",
        help=f"focus duration, {WORK_RANGE[0]}–{WORK_RANGE[1]} minutes",
    )
    parser.add_argument(
        "-b", "--break", dest="break_min", type=int, metavar="MIN",
        help=f"break duration, {BREAK_RANGE[0]}–{BREAK_RANGE[1]} minutes",
    )
    parser.add_argument(
        "--music", metavar="FILE|shuffle|off",
        help="music file, shuffle mode, or 'off'",
    )
    parser.add_argument(
        "--minimal", action="store_true",
        help="minimalist timer (digits and a mini progress bar only)",
    )
    parser.add_argument("--stats", action="store_true", help="show statistics and exit")
    parser.add_argument("--no-color", action="store_true", help="disable colors")
    parser.add_argument("--silent", action="store_true", help="disable completion sounds")
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    ensure_utf8_output()
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.work is not None and not WORK_RANGE[0] <= args.work <= WORK_RANGE[1]:
        parser.error(f"--work must be between {WORK_RANGE[0]} and {WORK_RANGE[1]} minutes")
    if args.break_min is not None and not BREAK_RANGE[0] <= args.break_min <= BREAK_RANGE[1]:
        parser.error(f"--break must be between {BREAK_RANGE[0]} and {BREAK_RANGE[1]} minutes")
    if args.music:
        value = args.music.strip().lower()
        if value not in ("off", "none", "0", "shuffle", "random"):
            path = Path(args.music).expanduser()
            if not path.is_absolute():
                path = (Path.cwd() / path).resolve()
            if not path.is_file():
                parser.error(f"music file not found: {path}")
            if path.suffix.lower() not in AUDIO_EXTENSIONS:
                parser.error(f"unsupported audio format: {path.suffix or '(none)'}")

    setup_console(args.no_color)

    if args.stats:
        lang = args.lang or "en"
        theme = THEME_BY_KEY.get(args.theme or "", THEMES[0])
        show_stats_table(theme, Localizer(lang), STATS_PATH)
        return 0

    try:
        return App(args).run()
    except ConfigError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except (QuitRequested, KeyboardInterrupt):
        if COLORS_ENABLED:
            sys.stdout.write(RESET)
        print("\n  See you! 👋")
        return 0
    except BrokenPipeError:
        return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        try:
            sys.stdout.close()
        except OSError:
            pass
        sys.exit(0)
