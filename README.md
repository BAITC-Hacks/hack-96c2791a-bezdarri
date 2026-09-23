 HEAD
# TaskForge

A beginner-friendly Streamlit hackathon MVP that turns vague business problems into structured student tasks, with optional OpenAI-assisted drafting and quality scoring. Python and JSON persistence; no authentication, database, or Docker.

## Концепция: «Развилка»

Главная механика платформы — показать бизнесу, насколько по-разному команда может понять одну и ту же задачу. Например, фраза «Хотим AI для анализа отзывов» может означать дашборд для директора, автоматические ответы клиентам или срочные уведомления управляющему. AI показывает эти варианты как **возможные интерпретации, а не факты о бизнесе**. Представитель бизнеса выбирает нужный результат, сочетает варианты или формулирует свой.

Затем система задаёт не менее трёх вопросов через ситуации, которые возникнут при работе над проектом:

| Ситуация | Что уточняется |
|---|---|
| «Первый день разработки. Где команда возьмёт отзывы?» | Данные и доступ к ним |
| «Пришёл негативный отзыв. Кто и что должен сделать?» | Пользователи и ожидаемое действие |
| «День сдачи. Как вы проверите, что решение работает?» | Измеримые критерии приёмки |

Ответ «пока не знаю» допустим: поле остаётся незаполненным, а система показывает, что нужно уточнить. Подтверждённые ответы собираются в редактируемую карточку задачи. В интерфейсе она выглядит как маршрут **данные → работа системы → действие пользователя → проверка результата**; неизвестные участки остаются развилками. Readiness Score растёт только за заполненные и подтверждённые поля по прозрачной шкале ниже.

Когда студенческая команда подаёт предложение, она дописывает одну фразу: **«Мы считаем задачу выполненной, когда…»**. Бизнес видит рядом своё ожидание и понимание команды. AI может подсветить расхождение — например, бизнес ждёт срочных уведомлений, а команда предлагает еженедельный отчёт. Окончательное решение о выборе одной, нескольких или ни одной команды принимает бизнес.

До выбора команды уникальная часть MVP состоит из двух взаимодействий: выбора интерпретации перед уточняющими вопросами и сравнения ожидаемого результата с предложением команды. После выбора добавляются подтверждение этапов, отзыв и Team XP. Обязательный сценарий — рейтинг, публикация, открытый каталог, предложения и ручной выбор — сохраняется.

## Основной сценарий

**Business Idea → Possible Interpretations → AI Clarification → Task Card → Readiness Score → Catalog → Team Proposal → Expectation Check → Business Decision**

---

## Для бизнеса

### 1. AI-анализ и уточняющие вопросы

Бизнес может начать даже с короткого описания, например:

> «Хотим AI для анализа отзывов»

Система анализирует предоставленную информацию, определяет недостающие детали и задаёт **3–5 динамических уточняющих вопросов**.

> AI не должен выдавать найденную во внешних источниках информацию за факты, предоставленные бизнесом. Любая дополнительная информация должна быть явно обозначена и подтверждена пользователем.

### 2. Readiness Score — рейтинг задачи 0–100

Каждая задача получает оценку готовности и один из уровней:

| Score | Уровень | Значение |
|---:|---|---|
| 0–39 | **Draft** | Требуется уточнение |
| 40–69 | **Workable** | Уже можно подавать предложения |
| 70–89 | **Ready** | Задача хорошо подготовлена |
| 90–100 | **Priority** | Максимальная готовность |

Баллы начисляются за содержание **подтверждённых бизнесом** полей, а не за объём текста или автоматически сгенерированные фразы. Формула: `Readiness Score = сумма баллов по семи критериям`, максимум 100. Если условие критерия не выполнено, он даёт 0 баллов; частичные баллы в MVP не предусмотрены.

| Критерий | Баллы | Условие начисления |
|---|---:|---|
| Context & Need | 20 | Описаны текущая ситуация и то, что нужно изменить |
| Data | 20 | Названы доступные данные, примеры или источники и способ доступа |
| Expected Result | 15 | Указан конкретный результат работы команды |
| Success Criteria | 15 | Описано, как бизнес проверит и примет результат |
| Constraints | 10 | Названы ограничения по срокам, технологиям, доступу или другие границы |
| Users | 10 | Указано, для кого создаётся решение |
| Business Connection | 10 | Указаны контакт, формат консультаций и способ получения обратной связи |

Система показывает начисленные баллы по каждому критерию и список недостающих деталей. После подтверждения нового ответа или правки карточки балл и уровень пересчитываются. AI может предложить формулировку, но неподтверждённое или неизвестное поле даёт 0 баллов.

### 3. Как повысить рейтинг

Система показывает конкретные рекомендации, например:

- `+15` — Define measurable success criteria
- `+20` — Add available data and access method
- `+10` — Describe constraints

После подтверждения изменения карточки рейтинг автоматически пересчитывается. Таким образом заполнение задачи превращается в понятную механику прогресса.
## Run locally

Requires Python 3.10 or newer. From the project folder:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m streamlit run app.py
```

On macOS/Linux, replace `.\.venv\Scripts\python.exe` with `.venv/bin/python`.
Before starting, edit your local `.env` and set `OPENAI_API_KEY` to your own key. Do not overwrite an existing `.env`. It is ignored by Git. Never put the key in the UI or source code. `OPENAI_MODEL` defaults to `gpt-4o-mini`; use a model available to your account that supports Responses API structured outputs. Calls require API access and billing. Existing environment variables take precedence over `.env`.

Open http://localhost:8501. Stop the server with Ctrl+C. Catalog, proposals, manual reviews, and manual task creation still work without a key. AI actions show a safe configuration error until a key is configured.

## Demo flow

1. **Create Task:** Enter a vague description and click **Analyze with AI**. Review the initial quality score, evidence-based explanations, suggestions, and at least three clarification questions. Answer questions and click **Update task with answers**. The updated editable card and score change appear. You can edit every field and click **Reanalyze edited card**; edits invalidate the previous assessment for publishing. Review the facts, tick the confirmation box, then explicitly **Publish task**. A title is required; low-scoring briefs can still be published. Clicking Analyze with AI again starts a fresh draft from the description.
2. **Catalog:** Browse tasks ordered by score, highest first, or filter by level. Expand a task and submit a team name, solution idea, plan, estimated time, and optional HTTP(S) prototype URL. Existing team names are matched without case sensitivity; new names create team records. Proposals start as Pending.
3. **Business Dashboard:** Review proposals under their tasks and manually Accept or Reject each one. Decisions persist and can be changed. Multiple acceptances are allowed; the application never automatically chooses a team or rejects other proposals.

`Title` · `Context` · `Need` · `Users` · `Data` · `Constraints` · `Expected Result` · `Success Criteria` · `Contact` · `Interaction Format` · `Feedback Procedure`
Five fictional tasks span all four readiness levels, and five fictional teams are included. Contact addresses use `.example`; referenced sample materials are illustrative and are not bundled. Proposals start empty so you can demonstrate the whole flow.

## Readiness scoring

AI evaluates quality and completeness using the rubric below. Vague mentions receive low credit; specific, actionable information earns more. Each category includes awarded points, its maximum, an explanation, and an improvement suggestion. Missing categories earn zero. Context and need each account for up to 10 points. The title does not contribute to readiness. AI scores are subjective and may vary between calls; improvement is never forced.

| Category | Points |
| --- | ---: |
| Context and need | 20 |
| Data/materials | 20 |
| Expected result | 15 |
| Success criteria | 15 |
| Constraints | 10 |
| Users | 10 |
| Business contact/interaction format | 10 |

**До:** `We need AI for reviews.` — **0/100 · Draft**: не уточнены текущая ситуация, данные, результат и критерии приёмки.

**После:** бизнес подтвердил все поля, кроме критериев приёмки, — **85/100 · Ready**. Добавление критериев даст ещё **+15** и поднимет задачу до **100/100 · Priority**.

## AI behavior and validation

The integration uses the [OpenAI Responses API with Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs). The description, current card, and submitted answers are sent only when an AI button is clicked, with response storage disabled (`store=False`). No API key is included in prompts, JSON records, or UI messages. Errors use fixed messages and do not display raw provider responses.

AI may summarize and paraphrase supplied information, including the title, but must not introduce new factual claims. Unknowns stay blank and are listed as missing. AI asks 3–5 contextual questions when three or more fields need clarification, prioritizing data/materials, context/need, expected result, and success criteria. A question may clarify related fields; unasked fields remain missing. Nearly complete briefs may need fewer questions, and complete briefs may need none. Local validation rejects obvious unsupported email addresses, URLs, and numeric facts while allowing ordinary rewording. These checks do not establish semantic truth or catch every unsupported claim, so the prompt forbids invention and the business must review and confirm the facts.

Validation also checks exact categories and maxima, integer scores within bounds, zero points for absent categories, score arithmetic, readiness level, and question count (maximum five). In `clarify` mode, 0–5 follow-up questions are valid even if some fields remain missing; the initial question minimum does not apply. Re-analysis uses the original description, all accumulated clarification answers, and the current editable card to update the card and recalculate its score. Blank fields are merged into the missing list automatically; questions do not have to cover every missing field. Invalid/incomplete responses, refusals, and API failures preserve the previous draft. Reanalysis of manual edits must return that exact card unchanged. The initial and previous scores are held in session state; drafts survive sidebar navigation but are not saved across a server restart or new browser session.

По умолчанию каталог сортируется по убыванию рейтинга, при равном рейтинге — по дате публикации (новые выше). Доступны фильтры по теме и уровню готовности. Низкий рейтинг не скрывает задачу и не блокирует предложение команды.

Пример:
## Project structure

```text
app.py                 # Sidebar navigation and three pages
requirements.txt       # Streamlit, OpenAI SDK, python-dotenv
.env.example           # API key and model configuration template
.gitignore
README.md
data/
  tasks.json           # Published tasks
  teams.json           # Seed teams and newly submitted team names
  proposals.json       # Proposals and manual review status
services/
  __init__.py
  scoring.py           # Checklist weights, levels, and suggestions
  ai.py                # Structured API call, grounding and rubric validation
  storage.py           # JSON reads, writes, and record operations
```

Data paths are relative to the project, independent of the working directory. Writes replace each file atomically to reduce partial-write risk. Invalid JSON produces an error instead of silently replacing existing data. This local demo is intended for one server and sequential use; it does not coordinate simultaneous writers. With no authentication, every visitor can access the dashboard, so use synthetic information only.

## Verify the MVP

Любая студенческая команда может открыть задачу и нажать **Submit Proposal**.

Предложение содержит:

- Solution Idea;
- Implementation Plan;
- Timeline;
- Prototype / GitHub Link.
- Что команда считает готовым результатом.

Количество предложений для одной задачи не ограничивается.

---

## Выбор команды бизнесом

### 12. Proposal Comparison

Бизнес получает все предложения в одном интерфейсе и может быстро сравнить их:

| | Team Alpha | Team Nova |
|---|---|---|
| Solution | AI Dashboard | AI Assistant |
| Timeline | 7 days | 10 days |
| Prototype | Available | Available |
| Decision | Select / Reject | Select / Reject |

AI **не выбирает победителя**. Бизнес самостоятельно может выбрать одну, несколько или ни одной команды.

### 13. Несколько команд, отзывы и Team XP

Бизнес может выбрать для одной задачи несколько студенческих команд. Каждая команда работает над своим решением и отдельно показывает результат. Бизнес сам решает, какие предложения принять: одно, несколько или ни одного.

У каждой выбранной команды свой прогресс по задаче. За подтверждённый бизнесом этап команда получает **+10 XP**; для одной задачи учитываются не более двух таких этапов. После сдачи результата бизнес оставляет команде один итоговый отзыв и оценку от 1 до 5 звёзд.

| Оценка | Изменение XP после отзыва |
|---|---:|
| 1 ★ | −20 XP |
| 2 ★ | −10 XP |
| 3 ★ | 0 XP |
| 4 ★ | +20 XP |
| 5 ★ | +40 XP |

При оценке 1–2 звезды бизнес обязательно указывает причину, связанную с согласованными критериями задачи. Оценку можно оставить только после сдачи результата; общий баланс XP команды не может стать отрицательным. XP за подтверждённые этапы сохраняется, а оценка меняет баланс отдельно.

В профиле команды отображаются общий XP, средняя оценка, количество завершённых задач и отзывы бизнеса. Таблица лидеров сортируется по XP, но рядом всегда показывается число оценённых задач: так бизнес видит, на каком опыте основан рейтинг. Рейтинг помогает сравнивать команды, а окончательный выбор остаётся за бизнесом.

---

## AI Safety & Transparency

### 14. Human-in-the-Loop AI

Каждый AI-generated результат помечается как:

> **AI Generated — Review Required**

Пользователь получает действия **Edit** и **Confirm** перед публикацией.

Основные правила:

- AI не должен придумывать отсутствующие факты;
- неизвестные данные остаются `Not provided`;
- AI задаёт уточняющий вопрос вместо заполнения неизвестного поля;
- пользователь может изменить любой AI-generated текст;
- публикация происходит только после подтверждения человеком;
- AI может рекомендовать задачи студентам, но не выбирать команду вместо бизнеса.

---

## MVP-функции

Для хакатона основной приоритет:

**AI Task Analysis → Possible Interpretations → Clarifying Questions → Editable Task Card → Live Readiness Score → Improvement Suggestions → Publish → Catalog → Proposal → Expectation Check → Accept / Reject (в том числе нескольких команд) → Review & Team XP**

Дополнительные функции при наличии времени: Skill Match, achievements, анимация изменения рейтинга и расширенное сравнение предложений.

## План архитектуры и запуск

Проект пока находится на стадии описания: в репозитории нет приложения и команды запуска. Этот раздел фиксирует целевую структуру MVP; после реализации здесь нужно указать фактические зависимости, команды установки и запуска, адрес приложения и способ выбора демонстрационных ролей.

Планируемые компоненты:

1. Интерфейс бизнеса: ввод задачи, выбор интерпретации, ответы на вопросы, редактирование и подтверждение карточки, сравнение предложений, подтверждение этапов и отзывы.
2. Интерфейс команды: общий каталог, фильтры, просмотр карточки, отправка предложения, сдача результата и просмотр профиля.
3. Логика приложения: хранение задач и предложений, расчёт рейтинга задачи по таблице выше, сортировка каталога, ручной выбор команд и расчёт Team XP.
4. AI-модуль: анализ исходного текста и подготовка интерпретаций и уточняющих вопросов. Карточка публикуется только после проверки человеком. При недоступности AI используется локальная заглушка с тем же форматом ответа.

Основные сущности: `TaskDraft`, `TaskCard`, `Team`, `Proposal`, `Milestone`, `Review`. Предложение связывает одну команду с одной задачей; несколько предложений могут быть приняты для одной задачи. Подтверждения этапов и итоговый отзыв хранятся отдельно для каждой пары «задача — команда».

## Контракт AI-функции

Вход AI: исходное описание задачи, уже подтверждённые бизнесом факты и язык ответа. Выход: список возможных интерпретаций, не менее трёх уточняющих вопросов и перечень полей, для которых не хватает данных. AI не заполняет неизвестные поля догадками.

Промпт для MVP:

> Проанализируй описание бизнес-задачи и подтверждённые факты. Предложи до трёх разных интерпретаций результата как гипотезы, задай минимум три конкретных вопроса по отсутствующим данным, пользователям, результату или критериям приёмки. Не добавляй фактов, которых нет во входе. Верни только JSON с полями `interpretations`, `questions`, `missing_fields`. Каждый вопрос должен содержать `field` и `text`.

Пример входа:

```json
{
  "description": "Хотим AI для анализа отзывов",
  "confirmed_facts": {},
  "language": "ru"
}
```

Пример допустимого ответа:

```json
{
  "interpretations": [
    "Дашборд с темами отзывов",
    "Автоматические ответы клиентам",
    "Уведомления о срочных жалобах"
  ],
  "questions": [
    {"field": "data", "text": "Где команда получит отзывы и есть ли к ним доступ?"},
    {"field": "users", "text": "Кто будет использовать результат?"},
    {"field": "success_criteria", "text": "Как вы проверите, что решение работает?"}
  ],
  "missing_fields": ["context", "data", "users", "expected_result", "success_criteria", "constraints", "business_connection"]
}
```

Ответ проверяется перед показом: это должен быть корректный JSON с массивами `interpretations`, `questions`, `missing_fields` и минимум тремя непустыми вопросами. Если ответ некорректен или AI недоступен, приложение показывает ошибку и предлагает повторить запрос либо использует локальную заглушку с заранее заданными вопросами. Сгенерированные варианты помечаются как гипотезы; выбранный вариант и карточку бизнес может изменить перед подтверждением.

## Данные и сценарии проверки

Если организаторы не предоставят данные, для демонстрации готовится набор минимум из **5 черновиков задач**, **5 карточек с рейтингом**, **5 профилей команд** и **5 предложений**. В черновиках должна различаться полнота описания; карточки содержат все поля, необходимые для расчёта рейтинга.

1. Ввести «Хотим AI для анализа отзывов»: увидеть варианты результата и минимум три вопроса; неизвестные поля остаются пустыми, рейтинг — 0/100.
2. Ответить на вопросы, отредактировать и подтвердить карточку: увидеть начисление баллов по критериям, список пропусков и рост рейтинга. Добавление критериев приёмки пересчитывает балл.
3. Опубликовать задачу: она появляется в общем каталоге на месте, соответствующем рейтингу. Задача с низким баллом остаётся видимой и принимает предложения; фильтры по теме и уровню работают.
4. Отправить предложения от двух команд: бизнес видит оба варианта и сравнение ожидаемого результата, затем вручную выбирает одну, обе или ни одной.
5. Подтвердить этап одной команды, принять её результат и оставить отзыв: XP и профиль обновляются. Проверить оценки 1–2 звезды с обязательной причиной и отсутствие отрицательного общего баланса XP.
6. Подать некорректный ответ AI или сделать его недоступным: система показывает ошибку или вопросы из локальной заглушки, не публикует неподтверждённую карточку.

Для защиты достаточно одного сквозного сценария до ручного выбора команды: слабое описание → уточнение → рост рейтинга → публикация → предложение → решение бизнеса. Подтверждение этапа и отзыв показываются после него, если укладываются в пятиминутное демо.
```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tests use temporary copies of JSON files and mock HTTP responses through the real OpenAI SDK; no key, API charges, or external requests are required. They cover the original manual flow and the complete AI draft → questions → answers → improved score → manual edits → reanalysis → confirmation → publication → catalog → proposal → Accept/Reject scenario, plus malformed responses and API failures. Mock tests verify the integration and state transitions, not live model output quality.

For a live smoke test after configuring your key, enter: "We run an online clothing store and many customers abandon their carts. We want students to help us understand why." Verify unknown data, metrics, constraints, and contact stay empty. Answer questions with actual specifics (for example, available anonymized CSV data, a deadline, a deliverable, a measurable criterion, and a contact format), reanalyze, review the score explanation, and publish only after confirming the facts. Then submit a proposal in Catalog and manually review it in Business Dashboard.
4a055f2 (Complete AI analysis and clarification flow)
