"""Enrich bundled synthetic fixtures without removing user-created records."""
from services import storage as db
from services.scoring import TASK_KEYS, task_readiness

drafts = [
    {"id": "draft-1", "text": "Хотим AI для анализа отзывов", "industry": "Сервис", "topic": "AI"},
    {"id": "draft-2", "text": "В кафе остаётся еда. Есть CSV продаж за 3 месяца; хотим планировать закупки.", "industry": "Общепит", "topic": "Data"},
    {"id": "draft-3", "text": "Хотим сайт для записи в библиотеку", "industry": "Образование", "topic": "Web"},
    {"id": "draft-4", "text": "Координатор теряет заявки волонтёров в чатах. Нужна единая доска смен за 2 недели.", "industry": "НКО", "topic": "Automation"},
    {"id": "draft-5", "text": "Нужен учёт возвратной упаковки: 50 тестовых контейнеров, Python, срок 3 недели.", "industry": "Логистика", "topic": "Automation"},
]
specs = [
    dict(title="Отзывы, которые не останутся без ответа", topic="AI", required_skills=["Python", "NLP", "React"],
         context="Демонстрационная сеть кофеен получает отзывы в нескольких каналах.", need="Помочь управляющему вовремя замечать жалобы.",
         users="Управляющие кофейнями: проверяют сигнал и связываются с гостем.",
         data_materials="300 синтетических отзывов в CSV; бизнес передаёт файл на старте. Реальных данных клиентов нет.",
         constraints="Прототип за 2 недели. Только синтетические данные; отправка ответов после проверки человеком.",
         expected_result="Дашборд тем отзывов и срочные уведомления управляющему о негативных отзывах.",
         success_criteria="На 30 размеченных примерах найти не менее 24 негативных отзывов; уведомление поступает за 60 секунд.",
         contact="Демо-менеджер, manager@coffee.example", interaction_format="Созвон по вторникам; обратная связь по критериям в течение 24 часов."),
    dict(title="Онлайн-запись в библиотеку", topic="Web", required_skills=["React", "UX", "JavaScript"],
         context="Демонстрационная библиотека записывает посетителей в учебные комнаты по почте.", need="Убрать пересечения записей и повторные письма.",
         users="Посетители и администраторы библиотеки.", data_materials="Синтетические комнаты и примеры записей; таблица доступна на старте.",
         constraints="", expected_result="Веб-прототип бронирования комнат и инструкция для администратора.",
         success_criteria="На 10 тестовых сценариях не допускается двойное бронирование.",
         contact="", interaction_format=""),
    dict(title="Доска смен для волонтёров", topic="Automation", required_skills=["Python", "SQL"],
         context="Демонстрационный фонд координирует смены в разных чатах.", need="Видеть незакрытые смены в одном месте.",
         users="Координатор волонтёров.", data_materials="", constraints="Срок 2 недели; только вымышленные участники.",
         expected_result="Доска смен с возможностью записаться.", success_criteria="", contact="coordinator@help.example", interaction_format=""),
    dict(title="Почему клиенты не возвращаются?", topic="AI", required_skills=["NLP", "Python"],
         context="Демонстрационная веломастерская получает разрозненные отзывы после ремонта.", need="Понять причины повторных обращений и оттока.",
         users="Владелец мастерской.", data_materials="", constraints="", expected_result="", success_criteria="", contact="", interaction_format=""),
    dict(title="Вернуть упаковку в оборот", topic="Data", required_skills=["Python", "SQL", "Data"],
         context="Демонстрационный сервис доставки отмечает возврат контейнеров на бумаге.", need="Видеть невозвращённые контейнеры и срок выдачи.",
         users="Упаковщики и координаторы доставки.", data_materials="50 синтетических записей о контейнерах; генерация командой на старте.",
         constraints="3 недели; без адресов клиентов и платёжных данных.", expected_result="Реестр выдачи и возврата с отчётом по просрочке.",
         success_criteria="Пройти 50 тестовых операций без дубликатов; просроченные контейнеры определяются верно.",
         contact="", interaction_format=""),
]
existing = db.load_records("tasks")
for i, spec in enumerate(specs, 1):
    task = {**{k: "" for k in TASK_KEYS}, **spec, "id": f"task-{i}", "synthetic": True, "published": True,
        "original_description": drafts[i-1]["text"], "created_at": f"2026-09-{10+i:02}T08:00:00+00:00"}
    task["confirmed_fields"] = [k for k in TASK_KEYS if task.get(k)]
    score = task_readiness(task)
    task.update(readiness_score=score["score"], readiness_level=score["level"])
    old = next((t for t in existing if t["id"] == task["id"]), None)
    if old:
        existing[existing.index(old)] = task
    else:
        existing.append(task)
# Preserve user records, marking legacy fields as requiring reconfirmation.
for task in existing:
    task.setdefault("interaction_format", "")
    task.setdefault("confirmed_fields", [])
    task.setdefault("topic", "AI")
    task.setdefault("required_skills", [])
    task.setdefault("published", True)
    score = task_readiness(task)
    task.update(readiness_score=score["score"], readiness_level=score["level"])
db.save_records("tasks", existing)
db.save_records("drafts", drafts)
teams = db.load_records("teams")
profiles = [
    ("Campus Coders", ["AI", "Web"], ["Python", "React", "NLP"]),
    ("Data Sprouts", ["Data", "AI"], ["Python", "SQL", "Machine Learning"]),
    ("Design Hive", ["Web"], ["React", "UX", "JavaScript"]),
    ("Process Pioneers", ["Automation"], ["Python", "SQL", "Automation"]),
    ("Green Byte", ["Data", "Automation"], ["Python", "Data", "SQL"]),
]
for i, (name, interests, skills) in enumerate(profiles, 1):
    team = next((t for t in teams if t["id"] == f"team-{i}"), None)
    values = {"id": f"team-{i}", "name": name, "interests": interests, "skills": skills, "synthetic": True}
    if team:
        team.update(values)
    else:
        teams.append(values)
db.save_records("teams", teams)
proposals = db.load_records("proposals")
ideas = [
    ("task-1", "team-1", "NLP-классификатор и панель управляющего", "Подготовить выборку → классифицировать отзывы → подключить уведомления → проверить критерии", "2 недели", "Дашборд показывает темы; минимум 24 из 30 негативных отзывов найдены, уведомления приходят за 60 секунд."),
    ("task-1", "team-2", "Еженедельный аналитический отчёт", "Очистить тексты → выделить темы → собрать отчёт", "10 дней", "Бизнес получает еженедельный отчёт с основными темами."),
    ("task-2", "team-3", "Прототип записи в библиотеку", "Интервью → макет → календарь → тестирование", "7 дней", "10 тестовых бронирований проходят без пересечений."),
    ("task-3", "team-4", "Доска незакрытых смен", "Согласовать статусы → собрать доску → проверить запись", "2 недели", "Координатор видит свободные смены, а студент может записаться."),
    ("task-4", "team-5", "Сначала исследовать доступные отзывы", "Уточнить источники → собрать тестовые примеры → согласовать критерии", "1 неделя", "Бизнес подтвердил источники отзывов и критерии будущего анализа."),
]
for i, (tid, teamid, idea, plan, timeline, done) in enumerate(ideas, 1):
    pid = f"proposal-demo-{i}"
    if any(p["id"] == pid for p in proposals):
        continue
    task = next(t for t in existing if t["id"] == tid)
    p = {"id": pid, "task_id": tid, "team_id": teamid, "team_name": next(t["name"] for t in teams if t["id"] == teamid),
         "solution_idea": idea, "plan": plan, "estimated_time": timeline, "prototype_url": "https://example.com/prototype",
         "definition_of_done": done, "status": "Pending", "milestones": [], "submission": None, "review": None,
         "agreement": {k: task.get(k, "") for k in ("expected_result", "success_criteria")},
         "synthetic": True, "created_at": f"2026-09-{17+i:02}T09:00:00+00:00"}
    proposals.append(p)
db.save_records("proposals", proposals)
print("Seed ready:", len(existing), "tasks;", len(teams), "teams;", len(proposals), "proposals;", len(drafts), "drafts")
