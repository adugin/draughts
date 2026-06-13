# DRAUGHTS — контекст проекта для Claude

## Цель проекта

Русские шашки на **Python 3.12+ / PyQt6 / NumPy**. Цель —
**продукт мирового класса**, совмещающий лучшие фичи ведущих шашечных
программ (Kingsrow, Scan, Dam 3.0, CheckerBoard, Windraughts и др.).

Оригинал: Borland Pascal 7.0 (~1998–2000), полный разбор:
**[ANALYSIS.md](ANALYSIS.md)**. Отход от legacy разрешён везде, где это
даёт заметное улучшение; международные шашечные стандарты (FMJD, PDN)
имеют приоритет над наследственными решениями.

---

## Конфигурация Claude Code (`.claude/`)

```
.claude/
├── settings.json        # проектные настройки: permissions + quality-хуки
├── settings.local.json  # персональные настройки (звук уведомлений) — НЕ в git
├── quality_check.py     # PreToolUse-хук: блокирует git commit при провале гейтов
├── ruff_hook.py         # PostToolUse-хук: ruff format + check --fix после Write/Edit
├── quality_full.py      # полный advisory-аудит (vulture/radon/bandit) — запуск вручную
├── agents/              # 5 субагентов (YAML frontmatter + markdown)
└── playbooks/           # 6 справочных чеклистов
```

По рекомендациям Anthropic `CLAUDE.md` и `.claude/` **трекаются в git**;
персональные `settings.local.json` и `CLAUDE.local.md` — нет.
`.planning/` — внутренние рабочие артефакты, не трекаются.

**Агенты** (`.claude/agents/`, вызываются через Agent tool):

- `product-owner` — гроссмейстер + product strategy. Решает ЧТО строить;
  консультация перед любой существенной фичей.
- `elite-qa` — баг-хантер уровня «видит код как шахматист видит доску».
  Запускать после каждой волны изменений и перед merge.
- `engine-tuner` — alpha-beta internals + Texel + SPRT. Запускать при
  любых изменениях в `draughts/game/ai/`.
- `rules-oracle` — FMJD-арбитр, все edge cases русских шашек.
  Консультировать при работе с правилами / move generation.
- `theme-designer` — UX/UI + Qt skinning + TOML theme engine. Темы,
  визуальные баги, расширение системы тем.

**Playbooks** (`.claude/playbooks/`, агенты ссылаются на них):

- `search-bug-debugging.md` — методика поиска багов в minimax-поиске
- `eval-change-checklist.md` — что проверить после изменения весов eval
- `agent-orchestration.md` — выбор модели, параллельные волны, шаблоны промптов
- `safe-refactoring.md` — безопасный split/move модулей (фазы 0–4)
- `lessons-learned.md` — «грабли» с цифрами: fail-hard, eval scale, speed≠strength
- `theme-creation.md` — создание тем, ноль inline hex-цветов

**Правило самообновления:** после каждой сессии, где агент или playbook
получил новые знания (найден баг, выработана методика, изменилась
архитектура), оркестратор **ОБЯЗАН** обновить соответствующий файл:
track record агента, новый edge case / pitfall в playbook, «Required
reading» при появлении нового playbook. Цель — агенты накапливают опыт
от сессии к сессии: больше опыта → лучше находки → больше опыта.

**Артефакты PO** — тактический слой в `.planning/product/`: `ROADMAP.md`
(упорядоченные фичи), `DECISIONS.md` (архитектурные решения Dnn),
`RESEARCH.md` (анализ конкурентов). **Стратегический слой** (в git, т.к.
`.planning/` — нет): `docs/ROADMAP_2026-2031.md` — 5-летний roadmap,
ревизия ежеквартально/ежегодно (governance — в его §11; решение D39).

---

## Политика выбора модели

Алиасы (`opus` / `sonnet` / `haiku`) вместо привязки к номерам версий.

- **opus-класс** — стратегия, архитектура, сложный поиск, рефакторинг
  с рисками, анализ корневых багов. Оркестратор (главный чат) — opus.
- **sonnet-класс** — сбор данных, типовые тесты, линейный рефакторинг,
  документация, механические правки. Большинство sub-agent работы.
- **haiku-класс** — не используется (не хватает reasoning для проекта).

**Правило:** задача описывается в 3 предложениях с чёткими шагами →
sonnet. Архитектурные решения или глубокий анализ кода → opus.
Подробнее: `.claude/playbooks/agent-orchestration.md`.

---

## Benchmark-driven development

**Правило:** любое изменение в `draughts/game/ai/` должно быть измерено
A/B-бенчмарком против предыдущей версии, прежде чем считаться
улучшением. Инфраструктура в `.planning/`:

- `head2head.py` — head-to-head NEW vs OLD; OLD — снапшот пакета
  в `.planning/ai_old_pkg/` (процедура обновления — в docstring)
- `bench.py` — trap battery + self-play blunder rate
- `sprt.py` — SPRT-тест для статистически строгих сравнений
- `perf_baseline.py` — замер скорости на канонических позициях

**Workflow алгоритмических изменений:**

1. Перед правкой обновить снапшот: `cp draughts/game/ai/*.py
   .planning/ai_old_pkg/` + переписать импорты (готовая команда —
   в docstring `head2head.py`)
2. Внести изменение, прогнать `pytest`
3. `python .planning/head2head.py --games 60 --depth 5`
4. Если score NEW < 55% или CI пересекает 50% на 60 играх — изменение
   не улучшение: откат либо расширение выборки до 100+ игр
5. Подтверждено — коммит с цифрами в commit message

**Никаких «улучшений на глаз».** Только измеримые.

**Инвариант dev-mode:** все тесты AI vs AI обязаны использовать hard
limits: `max_ply`, `move_timeout`, `game_timeout`, `quiet_move_limit`.
Никаких бесконечных циклов. Дефолты в `HeadlessGame.play_full_game`
и `Tournament` не позволяют случайному запуску подвесить процесс.

---

## Международные стандарты

- **Нотация:** PDN (Portable Draughts Notation) для сохранений и
  экспорта партий. `GameType "25"` для русских 8×8 — `draughts/game/pdn.py`.
- **Алгебраическая нотация** `a1..h8` на всех уровнях: UI, CLI, логи,
  комментарии в коде.
- **Уровни сложности** — приблизительный рейтинг (~1200, ~1600, ~2000
  Elo) с глубиной в скобках. Никаких «лёгкий/средний/сложный» без чисел.
- **Локализация:** RU основная (`draughts/i18n/`), строки-источники
  готовы к i18n (gettext-совместимый формат).

---

## Команды разработки

```bash
# Запуск игры
python main.py                          # новая игра
python main.py game.json                # загрузить партию
python main.py --resume                 # продолжить из автосохранения
python main.py --difficulty 3 --black   # сложность + играть чёрными
python main.py --depth 8                # ручная глубина AI

# Dev CLI: headless-игры, анализ позиций, турниры, скриншоты
python dev.py play-game --games 5 --depth 4
python dev.py tournament --games 20
python dev.py analyze --position POS --depth 8

# Бенчмарк AI (глубина 1-8, профилирование)
python benchmark.py --depth 8 --profile

# Тесты (запускать перед коммитом)
python -m pytest tests/ -q

# Проверка типов (strict на core + engine)
mypy draughts/game/ draughts/engine/

# Линтер + форматтер (ruff); конфигурация — в pyproject.toml
ruff check draughts/ tests/
ruff format draughts/ tests/

# Полный advisory-аудит качества (перед merge/release, не блокирует)
python .claude/quality_full.py
```

---

## Git-workflow

- Рабочая ветка: **`dev`** — все изменения коммитим и пушим сюда
- Ветка **`master`** защищена: **никогда не пушить** без явного указания
- Слияние `dev → master` — только по явному запросу пользователя
- Коммит после каждого целостного блока, push сразу в dev
- `git commit` проходит через quality-гейты (`.claude/quality_check.py`):
  ruff check + format, mypy strict, bandit HIGH, pytest — блокирующие

---

## Архитектура

- **Доска**: `np.ndarray((8,8), dtype=np.int8)`, 0-индексация, знаковая
  кодировка: `BLACK=1, BLACK_KING=2, WHITE=-1, WHITE_KING=-2, EMPTY=0`
- **AI** (`draughts/game/ai/` — пакет): поиск `search.py` (alpha-beta +
  TT/Zobrist + iterative deepening + quiescence + LMR + killers), оценка
  `eval.py`, генерация ходов `moves.py`, дебютная книга `book.py`,
  эндшпильная bitbase `bitbase.py`, Elo-калибровка `elo.py`,
  `SearchContext` в `state.py`
- **Движок как процесс** (`draughts/engine/`): DXP-протокол
  (client/server), без зависимости от PyQt6
- **Game-слой** (`draughts/game/`): board, controller, PDN, FEN,
  gametree, анализ партий, пазлы, headless/tournament для dev-режима
- **UI**: PyQt6, минималистичный — доска + стандартное меню; темы TOML
  в `draughts/themes/`
- **Сохранения**: JSON; **язык интерфейса**: русский
- **Автор**: Andrey Dugin — в «О программе»

## Ключевые факты о коде

- Тёмные клетки: `x % 2 != y % 2` → 32 активные клетки
- `y=0` — верх (чёрные), `y=7` — низ (белые); нотация `(0,0)=a8`
- Русские шашки: обязательное взятие, множественные прыжки, дамки
  ходят на любое расстояние
- Цепочка AI: `AIEngine.find_move()` → `_search_best_move()`
  (iterative deepening) → `_alphabeta()` → `_quiescence()`
  (всё в `ai/search.py`) → `_evaluate_fast()` (`ai/eval.py`)
- Оценка: материал + продвижение + центр + связанные пешки + фазовые
  веса + расстояние дамки + золотые углы
- Детекция повторов и ничейных эндшпилей (правила FMJD)

---

## Временные решения и TODO-маркеры

Любой костыль, обходной путь или незавершённая реализация
**ОБЯЗАТЕЛЬНО** маркируется тегом `# TAG(контекст): описание`,
где контекст — milestone, решение или причина:

- `# TODO(M5): заменить эвристику на табличную оценку` — задача
- `# FIXME(D6): Elo-числа placeholder, нужен турнир 100+ игр` — известный баг
- `# HACK(Qt6): deleteLater без quit вызывает segfault, поэтому quit+wait`
- `# WORKAROUND(numpy): int8 overflow при piece_count > 127` — обход бага зависимости

**Правила:** никаких «тихих» костылей; `elite-qa` проверяет все маркеры
при каждом аудите; при закрытии TODO удалять и комментарий, и костыль.
Инвентаризация: `grep -rn "TODO\|FIXME\|HACK\|WORKAROUND" draughts/`.

---

## Отчёт по выполнению задачи

После каждой задачи — отчёт:

1. **Задача:** краткая формулировка
2. **Статус:** успешно / частично / не выполнено
3. **Что сделано:** перечень действий и изменений
4. **Изменения:** файлы созданы / изменены / удалены
5. **Примечания:** предупреждения, рекомендации (если есть)

---

## Версионирование

[Semantic Versioning](https://semver.org/); история — в **CHANGELOG.md**.

- Единственный source of truth: `draughts/__init__.py` → `__version__`
- **Коммиты в dev версию НЕ меняют**; версия меняется **только при
  merge в master** (по запросу пользователя)
- Claude сам определяет номер: **patch** (4.0.x) — баг-фиксы и
  косметика; **minor** (4.x.0) — новые фичи, улучшения AI, настройки,
  CLI-параметры; **major** (x.0.0) — ломающие изменения, только по
  явному запросу пользователя
- При обновлении версии — **обязательно обновить CHANGELOG.md**

## Обновление документации

- Изменилась механика/настройки/UI → обновить справку
  `draughts/resources/help.md`
- Существенные изменения (новые фичи, архитектура, зависимости,
  системные требования) → обновить **README.md**
- Обновилась версия → обновить **CHANGELOG.md**

---

## Что НЕ делать без явного запроса

- Менять правила русских шашек (фундамент; другие варианты — отдельный
  milestone)
- Пушить в `master` напрямую
- Вносить изменения в AI без A/B-бенчмарка против предыдущей версии

## Что МОЖНО без подтверждения, если PO одобрил

- Переделывать меню настроек и UI-опции под мировые стандарты
- Развивать Elo-based систему уровней сложности
- Рефакторить модульную структуру (цель — независимая работа над модулями)
- Расширять PDN, движковый анализ, подсказки, базу партий и задач
- Удалять legacy-решения, противоречащие мировым стандартам
