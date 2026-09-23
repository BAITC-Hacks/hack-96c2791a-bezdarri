"""TaskForge / Развилка — AI Sana hackathon MVP."""
from html import escape
import streamlit as st
from services.ai import AIError, INSTRUCTIONS, SCHEMA, analyze_task, local_analysis
from services.scoring import FIELDS, TASK_KEYS, TOPICS, has_value, task_readiness
from services.matching import interpretations, skill_match, expectation_check, task_markdown
from services import storage as db

st.set_page_config(page_title="Развилка · TaskForge", page_icon="↗", layout="wide")
st.markdown("""
<style>
.stApp {background:#f6f7fb;color:#16233b}
.block-container {padding-top:2.2rem;max-width:1400px;padding-bottom:4rem}
h1,h2,h3 {letter-spacing:-.035em}
h1 {font-weight:800!important}
[data-testid="stSidebar"] {background:#111c32}
[data-testid="stSidebar"] * {color:#edf1fb}
[data-testid="stSidebar"] [data-baseweb="select"] * {color:#16233b}
[data-testid="stSidebar"] input[role="combobox"] {color:#16233b!important}
[data-testid="stMetric"] {background:white;border:1px solid #e4e8f0;padding:18px;border-radius:16px}
[data-testid="stExpander"] {background:#fff;border-radius:14px;border:1px solid #e3e8f0}
.stButton>button,.stDownloadButton>button {border-radius:10px;font-weight:600}
.hero {background:linear-gradient(110deg,#14243f,#253b64);padding:30px 34px;border-radius:22px;color:white;margin-bottom:24px}
.hero h1 {color:white;font-size:38px;margin:7px 0 10px}
.hero p {color:#d6e0f2;max-width:800px;line-height:1.7}
.eyebrow {font-size:11px;letter-spacing:.18em;color:#b9c9e8;font-weight:700}
.chip {display:inline-block;border-radius:6px;padding:4px 9px;font-size:11px;font-weight:800;background:#e8efff;color:#3057ad;margin-right:5px}
.chip.priority {background:#e1f5e9;color:#19794a}
.chip.ready {background:#e9edff;color:#4c56b4}
.chip.draft {background:#f3ecdf;color:#957026}
.route {display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:12px 0 20px}
.route>div {background:#fff;border:1px solid #e1e7f0;border-radius:12px;padding:14px;font-size:12px}
.route b {display:block;margin-bottom:7px;color:#4762a0}
.route .unknown {border-style:dashed;color:#886c37;background:#fffdf7}
@keyframes grow {from {opacity:.3;transform:translateY(5px)} to {opacity:1;transform:translateY(0)}}
[data-testid="stMetricValue"] {animation:grow .35s ease-out}
@media(max-width:750px) {.route{grid-template-columns:repeat(2,1fr)}.hero h1{font-size:28px}}
</style>
""", unsafe_allow_html=True)
S = st.session_state
STATUS = {"Pending": "На рассмотрении", "Accepted": "Выбрана бизнесом", "Rejected": "Отклонено"}
PAGES = ["Конструктор", "Каталог задач", "Кабинет бизнеса", "Моя команда", "Лидеры", "О проекте"]


def hero(eyebrow, title, subtitle):
    st.markdown(f'<div class="hero"><div class="eyebrow">{escape(eyebrow)}</div><h1>{escape(title)}</h1><p>{escape(subtitle)}</p></div>', unsafe_allow_html=True)


def notify(message):
    S.notice = message
    st.rerun()


def reset_editor(task=None):
    for key in list(S):
        if key.startswith(("card_", "verify_", "answer_", "interpret_")):
            del S[key]
    S.draft = dict(task) if task else {k: "" for k in TASK_KEYS}
    S.draft.setdefault("confirmed_fields", [])
    S.draft.setdefault("topic", "AI")
    S.draft.setdefault("required_skills", [])
    S.edit_id = task.get("id") if task else None
    S.analysis = None
    S.analysis_version = S.get("analysis_version", 0) + 1
    S.business_description = task.get("original_description", "") if task else ""
    S.saved_description = S.business_description
    S.confirm_publish = False
    S.ai_error = None
    S.before_score = task_readiness(task)["score"] if task else 0
    S.interpretation = ""
    S.published_id = None


def save_edit(key):
    value = S[f"card_{key}"]
    if key == "required_skills":
        value = [s.strip() for s in value.split(",") if s.strip()]
    S.draft[key] = value.strip() if isinstance(value, str) else value
    S.draft["confirmed_fields"] = [k for k in S.draft.get("confirmed_fields", []) if k != key]
    if f"verify_{key}" in S:
        S[f"verify_{key}"] = False
    S.confirm_publish = False
    S.published_id = None


def confirm_field(key):
    confirmed = set(S.draft.get("confirmed_fields", []))
    if S[f"verify_{key}"] and has_value(S.draft.get(key)):
        confirmed.add(key)
    else:
        confirmed.discard(key)
    S.draft["confirmed_fields"] = sorted(confirmed)
    S.confirm_publish = False


def confirm_all():
    S.draft["confirmed_fields"] = [k for k in TASK_KEYS if has_value(S.draft.get(k))]
    for k in TASK_KEYS:
        S[f"verify_{k}"] = k in S.draft["confirmed_fields"]
    S.confirm_publish = False


def run_analysis(mode):
    description = S.get("business_description", "").strip()
    if not description and mode == "draft":
        S.ai_error = "Сначала опишите бизнес-задачу."
        return
    answers = []
    current = {k: S.draft.get(k, "") for k in TASK_KEYS} if mode != "draft" else None
    if mode == "clarify":
        answers = [{**q, "answer": S.get(f"answer_{S.analysis_version}_{i}", "").strip()} for i, q in enumerate(S.analysis["questions"])]
        answers = [a for a in answers if a["answer"]]
        if not answers:
            S.ai_error = "Ответьте хотя бы на один вопрос. Можно написать «пока не знаю»."
            return
    interpretation = ""
    if mode == "draft":
        choices = S.get("interpret_choices", [])
        interpretation = " ".join([text for title, text in interpretations(description) if title in choices] + [S.get("interpret_own", "").strip()]).strip()
    try:
        if S.get("assistant_mode") == "OpenAI":
            result = analyze_task(description, answers, current, mode, interpretation)
        else:
            result = local_analysis(description, answers, current, interpretation)
    except AIError as error:
        S.ai_error = str(error)
        return
    old = dict(S.draft)
    S.analysis = result
    S.analysis_version = S.get("analysis_version", 0) + 1
    S.draft = {**old, **result["task"], "original_description": description}
    S.draft["confirmed_fields"] = [k for k in old.get("confirmed_fields", []) if mode != "draft" and old.get(k) == S.draft.get(k)]
    S.confirm_publish = False
    S.ai_error = None
    S.published_id = None
    for key in TASK_KEYS:
        S.pop(f"card_{key}", None)
        S.pop(f"verify_{key}", None)


def route(task):
    html = '<div class="route">'
    for title, key in [("01 · Данные", "data_materials"), ("02 · Работа системы", "expected_result"), ("03 · Пользователь", "users"), ("04 · Проверка", "success_criteria")]:
        value = task.get(key, "")
        known = has_value(value) and key in task.get("confirmed_fields", [])
        text = value[:180] if known else "Развилка · нужно уточнить / подтвердить"
        html += f'<div class="{"" if known else "unknown"}"><b>{title}</b>{escape(text)}</div>'
    st.markdown(html + "</div>", unsafe_allow_html=True)


def readiness(task):
    r = task_readiness(task)
    st.metric("Готовность к работе", f'{r["score"]}/100', r["level"], delta_color="off")
    st.progress(r["score"] / 100)
    st.caption(r["source"])
    st.dataframe(r["breakdown"], hide_index=True, width="stretch")
    if r["suggestions"]:
        st.markdown("**Следующие шаги**")
        for text in r["suggestions"]:
            st.caption(text)
    else:
        st.success("Все поля подтверждены. Задача готова к работе!")
    return r


def constructor():
    hero("AI SANA / BUSINESS WORKSPACE", "Из идеи — в понятную задачу", "Уточняйте детали, подтверждайте факты и показывайте командам, какой результат нужен бизнесу.")
    if "draft" not in S:
        reset_editor()
    tasks = db.load_records("tasks")
    with st.expander("Открыть опубликованную задачу для доработки"):
        if tasks:
            chosen = st.selectbox("Задача", tasks, format_func=lambda t: t["title"], key="edit_choice")
            st.button("Редактировать выбранную", on_click=reset_editor, args=(chosen,))
    a, b = st.columns([3, 1])
    a.caption("01 Идея  →  02 Развилка  →  03 Уточнение  →  04 Подтверждение")
    b.button("Новая задача", on_click=reset_editor, width="stretch")
    if S.get("edit_id"):
        st.info("Изменения опубликованной задачи появятся в каталоге после повторного подтверждения.")
    st.subheader("01 / В чём ваша задача?")
    if "business_description" not in S:
        S.business_description = S.get("saved_description", S.draft.get("original_description", ""))
    st.text_area("Коротко опишите потребность", key="business_description", placeholder="Хотим AI для анализа отзывов", height=100, on_change=lambda: S.update(saved_description=S.business_description))
    with st.expander("Взять пример для защиты"):
        for example in db.load_records("drafts"):
            if st.button(example["text"], key=f'example_{example["id"]}'):
                S.pending_description = example["text"]
                st.rerun()
    st.subheader("02 / Одна фраза — разные результаты")
    st.caption("Возможные интерпретации, а не факты о вашем бизнесе. Выберите одну, несколько или опишите свою.")
    opts = interpretations(S.get("business_description", ""))
    for col, (title, text) in zip(st.columns(3), opts):
        with col:
            with st.container(border=True):
                st.markdown(f"**{title}**")
                st.write(text)
    selected = st.multiselect("Какой результат вам подходит?", [title for title, _ in opts], key="interpret_choices")
    own = st.text_input("Свой вариант или уточнение", key="interpret_own")
    S.interpretation = " ".join([text for title, text in opts if title in selected] + ([own.strip()] if own.strip() else []))
    st.radio("Помощник", ["Локальный помощник", "OpenAI"], key="assistant_mode", horizontal=True, help="Локальный режим использует правила. OpenAI требует ключ в .env.")
    st.button("Разобрать задачу", key="analyze", on_click=run_analysis, args=("draft",), type="primary")
    if S.get("ai_error"):
        st.error(S.ai_error)
    if S.get("analysis"):
        st.info(S.analysis["provider"] + " · Проверьте и подтвердите каждое утверждение.")
        st.subheader("03 / Представим работу над проектом")
        with st.form(f"clarify_{S.analysis_version}"):
            for i, q in enumerate(S.analysis["questions"]):
                st.text_area(q["question"], key=f"answer_{S.analysis_version}_{i}", placeholder="Конкретный ответ или «пока не знаю»", height=80)
            st.form_submit_button("Собрать карточку из ответов", on_click=run_analysis, args=("clarify",))
    st.subheader("04 / Карточка, которую поймёт команда")
    st.caption("Баллы начисляются только после подтверждения. Неизвестное можно оставить пустым.")
    left, right = st.columns([1.8, 1], gap="large")
    with left:
        for key, label in [("title", "Название")] + [(k, label) for k, label, *_ in FIELDS]:
            if f"card_{key}" not in S:
                S[f"card_{key}"] = S.draft.get(key, "")
            if key == "title":
                st.text_input(label, key=f"card_{key}", on_change=save_edit, args=(key,))
            else:
                st.text_area(label, key=f"card_{key}", height=85, on_change=save_edit, args=(key,))
                if f"verify_{key}" not in S:
                    S[f"verify_{key}"] = key in S.draft.get("confirmed_fields", [])
                st.checkbox("Подтверждаю: " + label.lower(), key=f"verify_{key}", disabled=not has_value(S.draft.get(key)), on_change=confirm_field, args=(key,))
        if "card_topic" not in S:
            S.card_topic = S.draft.get("topic", "AI")
        st.selectbox("Тема", TOPICS, key="card_topic", on_change=save_edit, args=("topic",))
        if "card_required_skills" not in S:
            S.card_required_skills = ", ".join(S.draft.get("required_skills", []))
        st.text_input("Полезные навыки через запятую", key="card_required_skills", placeholder="Python, NLP, React", on_change=save_edit, args=("required_skills",))
        st.button("Проверил — подтвердить заполненные поля", on_click=confirm_all, key="confirm_all")
    with right:
        score = readiness(S.draft)
        st.divider()
        st.markdown("**До → После**")
        st.caption(S.draft.get("original_description") or S.get("business_description") or "Исходная идея")
        delta = score["score"] - S.get("before_score", 0)
        st.metric("Рост готовности", f'{S.get("before_score", 0)} → {score["score"]}', f'{delta:+d} баллов', delta_color="off")
        if score["score"] >= 90:
            st.success("🏅 Достижение: ясный бриф")
        elif score["score"] >= 70:
            st.success("✦ Достижение: готов к старту")
        elif score["score"] >= 40:
            st.info("✦ Достижение: первый ориентир")
        st.caption("Низкий балл не закрывает публикацию и отклики.")
    route(S.draft)
    st.checkbox("Я проверил карточку и подтверждаю её публикацию", key="confirm_publish")
    if st.button("Сохранить и опубликовать" if S.get("edit_id") else "Опубликовать в каталоге", key="publish", type="primary", disabled=not S.get("confirm_publish") or bool(S.get("published_id"))):
        saved = db.publish_task(S.draft, S.confirm_publish, S.get("edit_id"))
        S.published_id = saved["id"]
        S.edit_id = saved["id"]
        notify("Задача опубликована. Она доступна всем командам в каталоге.")
    if S.get("published_id"):
        st.success("Опубликовано. Следующий шаг — «Каталог задач».")
    st.download_button("Скачать карточку · Markdown", task_markdown(S.draft), "task-brief.md", mime="text/markdown", key="export_draft")


def current_team():
    teams = db.load_records("teams")
    return next((t for t in teams if t["id"] == S.get("active_team")), teams[0] if teams else None)


def compare_expectation(task, proposal):
    a, b = st.columns(2)
    a.markdown("**Бизнес ожидает**")
    a.write(task.get("expected_result") or "Не указано")
    a.caption("Приёмка: " + (task.get("success_criteria") or "нужно уточнить"))
    b.markdown("**Команда считает готовым**")
    b.write(proposal.get("definition_of_done") or "Не указано")
    check = expectation_check(task, proposal)
    (st.warning if check["missing"] else st.info)(check["message"])
    st.caption("Подсказка по ключевым словам, не семантическая AI-экспертиза. Решение принимает бизнес.")


def proposal_form(task):
    team = current_team()
    if not team:
        st.info("Создайте профиль на странице «Моя команда».")
        return
    tid = task["id"]
    st.caption(f'Отклик от команды {team["name"]}. Сменить её можно в боковом меню.')
    with st.form(f"proposal_{tid}"):
        idea = st.text_area("Идея решения", key=f"idea_{tid}")
        plan = st.text_area("План реализации", key=f"plan_{tid}")
        timeline = st.text_input("Срок", key=f"time_{tid}", placeholder="2 недели")
        url = st.text_input("Прототип / GitHub (необязательно)", key=f"url_{tid}", placeholder="https://…")
        done = st.text_area("Мы считаем задачу выполненной, когда…", key=f"done_{tid}")
        sent = st.form_submit_button("Отправить предложение", key=f"send_{tid}")
    if sent:
        db.submit_proposal(tid, {"team_id": team["id"], "solution_idea": idea, "plan": plan, "estimated_time": timeline, "prototype_url": url, "definition_of_done": done})
        st.success("Предложение отправлено. Решение принимает бизнес.")
        compare_expectation(task, {"definition_of_done": done})


def catalog():
    hero("OPEN TASK CATALOG", "Найдите задачу, в которой вы сильны", "Все задачи открыты каждой команде. Готовность помогает выбрать, а навыки дают ориентир.")
    tasks = [t for t in db.load_records("tasks") if t.get("published", True)]
    a, b, c = st.columns(3)
    a.metric("Открытых задач", len(tasks))
    b.metric("Готовы к старту", sum(task_readiness(t)["score"] >= 70 for t in tasks))
    c.metric("Команд в сообществе", len(db.load_records("teams")))
    query = st.text_input("Поиск задач", placeholder="Название, проблема или технология…", key="catalog_search").casefold()
    a, b, c = st.columns(3)
    topic = a.selectbox("Тема", ["Все"] + TOPICS, key="filter_topic")
    level = b.selectbox("Готовность", ["Все", "Draft", "Workable", "Ready", "Priority"], key="filter_level")
    sort = c.selectbox("Сортировка", ["По готовности", "Сначала новые", "По навыкам"], key="catalog_sort")
    score_range = st.slider("Диапазон готовности", 0, 100, (0, 100), key="score_range")
    team = current_team()
    tasks = [t for t in tasks if (topic == "Все" or t.get("topic") == topic) and (level == "Все" or task_readiness(t)["level"] == level) and score_range[0] <= task_readiness(t)["score"] <= score_range[1] and query in " ".join([str(t.get(k, "")) for k in TASK_KEYS] + t.get("required_skills", [])).casefold()]
    key = (lambda t: t.get("created_at", "")) if sort == "Сначала новые" else (lambda t: (skill_match(t, team or {})["percent"] or 0, task_readiness(t)["score"])) if sort == "По навыкам" else (lambda t: (task_readiness(t)["score"], t.get("created_at", "")))
    tasks.sort(key=key, reverse=True)
    st.caption(f"Найдено {len(tasks)} · Draft тоже доступен для отклика")
    if not tasks:
        st.info("По этим фильтрам задач нет. Расширьте поиск или опубликуйте свою.")
    for task in tasks:
        r = task_readiness(task)
        with st.expander(f'{task["title"]} — {r["score"]}/100 · {r["level"]}'):
            st.markdown(f'<span class="chip {r["level"].lower()}">{r["level"].upper()} · {r["score"]}</span><span class="chip">{escape(task.get("topic", "AI"))}</span>', unsafe_allow_html=True)
            st.write(task.get("need") or task.get("context") or "Требуется уточнение")
            if task.get("synthetic"):
                st.caption("Синтетический пример · контакты и ссылки демонстрационные")
            match = skill_match(task, team or {})
            st.caption(f'{match["percent"]}% Skill Match · ' + " · ".join([f"{s} ✓" for s in match["matched"]] + [f"{s} —" for s in match["missing"]]) if match["percent"] is not None else "Навыки не заданы — совпадение пока не рассчитано.")
            route(task)
            detail, proposal_tab = st.tabs(["Карточка и рейтинг", "Предложить решение"])
            with detail:
                for field, label, *_ in FIELDS:
                    st.markdown(f"**{label}**")
                    st.write(task.get(field) or "Не указано")
                readiness(task)
                st.download_button("Скачать ТЗ", task_markdown(task), f'{task["id"]}.md', key=f'download_{task["id"]}')
            with proposal_tab:
                proposal_form(task)


def business():
    hero("BUSINESS CONTROL ROOM", "Сравните подходы. Выберите команды.", "Одна, несколько или ни одной — решение остаётся за вами. Каждая выбранная команда сдаёт собственный результат.")
    tasks = db.load_records("tasks")
    if not tasks:
        st.info("Сначала опубликуйте задачу.")
        return
    task = st.selectbox("Ваша задача", tasks, format_func=lambda t: t["title"], key="business_task")
    proposals = [p for p in db.load_records("proposals") if p["task_id"] == task["id"]]
    x, y, z = st.columns(3)
    x.metric("Предложений", len(proposals))
    y.metric("Выбрано команд", len({p["team_id"] for p in proposals if p["status"] == "Accepted"}))
    z.metric("Сдано решений", sum(bool(p.get("submission")) for p in proposals))
    if not proposals:
        st.info("Откликов пока нет. Откройте каталог и отправьте предложение от команды.")
        return
    st.subheader("Сравнение предложений")
    st.dataframe([{"Команда": p["team_name"], "Идея": p["solution_idea"], "Срок": p["estimated_time"], "Готовый результат": p.get("definition_of_done", ""), "Прототип": p.get("prototype_url") or "Нет", "Статус": STATUS[p["status"]]} for p in proposals], hide_index=True, width="stretch")
    for p in proposals:
        pid = p["id"]
        with st.expander(f'{p["team_name"]} · {STATUS[p["status"]]}', expanded=len(proposals) == 1):
            stats = db.team_stats(p["team_id"])
            st.caption(f'{stats["xp"]} XP · {stats["completed"]} оценённых задач · средняя оценка {stats["average"] or "—"}')
            st.markdown("**Идея:** " + p["solution_idea"])
            st.markdown("**План:** " + p["plan"])
            st.write("Срок: " + p["estimated_time"])
            if p.get("prototype_url") and db.valid_url(p["prototype_url"]):
                st.link_button("Открыть прототип", p["prototype_url"])
            compare_expectation(p.get("agreement") or task, p)
            locked = bool(p.get("milestones") or p.get("submission") or p.get("review"))
            a, b = st.columns(2)
            if a.button("Выбрать команду", key=f"accept_{pid}", type="primary", disabled=locked or p["status"] == "Accepted"):
                db.review_proposal(pid, "Accepted")
                notify("Команда выбрана. Другие предложения остались без изменений.")
            if b.button("Отклонить", key=f"reject_{pid}", disabled=locked or p["status"] == "Rejected"):
                db.review_proposal(pid, "Rejected")
                notify("Предложение отклонено.")
            if p["status"] != "Accepted":
                continue
            st.markdown("**Прогресс команды**")
            milestones = p.get("milestones", [])
            st.progress(min(len(milestones) / 2, 1))
            for m in milestones:
                st.success(f'+10 XP · {m["description"]}')
                st.caption(m["evidence"])
            if not p.get("review"):
                with st.form(f"milestone_{pid}"):
                    description = st.text_input("Завершённый этап", key=f"stage_{pid}")
                    evidence = st.text_area("Что проверено бизнесом", key=f"evidence_{pid}")
                    if st.form_submit_button("Подтвердить этап · +10 XP", key=f"confirm_stage_{pid}"):
                        db.confirm_milestone(pid, description, evidence)
                        notify("Этап подтверждён бизнесом. Команде начислено 10 XP.")
            if p.get("submission"):
                st.markdown("**Команда сдала результат**")
                st.write(p["submission"]["summary"])
                if p["submission"].get("url") and db.valid_url(p["submission"]["url"]):
                    st.link_button("Открыть результат", p["submission"]["url"])
                if not p.get("review"):
                    with st.form(f"review_{pid}"):
                        rating = st.slider("Итоговая оценка", 1, 5, 5, key=f"rating_{pid}")
                        st.caption("1 ★ −20 · 2 ★ −10 · 3 ★ 0 · 4 ★ +20 · 5 ★ +40 XP")
                        st.write("Согласованные критерии: " + (p.get("agreement", {}).get("success_criteria") or "Не определены; объясните, какое согласованное ожидание оцениваете."))
                        comment = st.text_area("Отзыв и причина оценки относительно критериев", key=f"review_text_{pid}")
                        st.checkbox("Оценка относится к согласованным критериям задачи", key=f"review_confirm_{pid}")
                        if st.form_submit_button("Оставить итоговый отзыв", key=f"review_submit_{pid}"):
                            if not S.get(f"review_confirm_{pid}"):
                                st.error("Подтвердите связь оценки с согласованными критериями.")
                            else:
                                db.leave_review(pid, rating, comment)
                                notify("Итоговый отзыв сохранён. XP пересчитан.")
            else:
                st.info("Итоговый отзыв откроется после сдачи результата командой на странице «Моя команда».")
            if p.get("review"):
                review = p["review"]
                st.success(f'{review["rating"]} ★ · {review["xp"]:+d} XP · {review["comment"]}')


def team_page():
    hero("TEAM WORKSPACE", "Покажите, что умеет ваша команда", "Навыки помогают найти задачу. Репутация растёт за подтверждённый результат.")
    team = current_team()
    with st.expander("Создать команду"):
        with st.form("new_team"):
            name = st.text_input("Название команды", key="new_team_name")
            interests = st.multiselect("Интересы", TOPICS, key="new_interests")
            skills = st.text_input("Навыки и технологии через запятую", key="new_skills")
            if st.form_submit_button("Создать профиль", key="create_team"):
                created = db.save_team(name, interests, skills.split(","))
                S.pending_team = created["id"]
                notify("Профиль создан.")
    if not team:
        return
    stats = db.team_stats(team["id"])
    a, b, c = st.columns(3)
    a.metric("Team XP", stats["xp"])
    b.metric("Средняя оценка", f'{stats["average"]} ★' if stats["average"] else "Пока нет")
    c.metric("Завершено и оценено", stats["completed"])
    with st.expander("Профиль · " + team["name"]):
        with st.form(f'profile_{team["id"]}'):
            name = st.text_input("Название", team["name"])
            interests = st.multiselect("Интересы", TOPICS, default=[i for i in team.get("interests", []) if i in TOPICS])
            skills = st.text_input("Навыки", ", ".join(team.get("skills", [])))
            if st.form_submit_button("Сохранить профиль"):
                db.save_team(name, interests, skills.split(","), team["id"])
                notify("Профиль обновлён.")
    st.caption("🏅 " + ("Первый результат" if stats["completed"] else "Первый результат — после завершения задачи") + " · " + ("Надёжный партнёр" if stats["completed"] >= 3 and (stats["average"] or 0) >= 4 else "Надёжный партнёр — 3 оценки, средняя ≥ 4"))
    tasks = {t["id"]: t for t in db.load_records("tasks")}
    proposals = [p for p in db.load_records("proposals") if p["team_id"] == team["id"]]
    st.subheader("Мои предложения и работа")
    if not proposals:
        st.info("Найдите интересную задачу в каталоге и отправьте предложение.")
    for p in proposals:
        with st.expander(f'{tasks.get(p["task_id"], {}).get("title", "Задача")} · {STATUS[p["status"]]}'):
            st.write(p["solution_idea"])
            st.caption("Мы считаем задачу выполненной, когда: " + p.get("definition_of_done", "не указано"))
            st.write(f'Подтверждено этапов: {len(p.get("milestones", []))}')
            if p["status"] == "Accepted" and not p.get("review"):
                with st.form(f'result_{p["id"]}'):
                    summary = st.text_area("Что выполнено и как проверить", value=(p.get("submission") or {}).get("summary", ""), key=f'result_summary_{p["id"]}')
                    url = st.text_input("Ссылка на результат (необязательно)", value=(p.get("submission") or {}).get("url", ""), key=f'result_url_{p["id"]}')
                    if st.form_submit_button("Сдать результат бизнесу", key=f'submit_result_{p["id"]}'):
                        db.submit_result(p["id"], summary, url)
                        notify("Результат сдан. Теперь бизнес может оставить итоговую оценку.")
            if p.get("review"):
                st.success(f'{p["review"]["rating"]} ★ · {p["review"]["comment"]}')
    st.subheader("Отзывы бизнеса")
    for review in stats["reviews"]:
        with st.container(border=True):
            st.write(f'{review["rating"]} ★ · {tasks.get(review["task_id"], {}).get("title", "Задача")}')
            st.write(review["comment"])
    if not stats["reviews"]:
        st.caption("Пока нет отзывов.")


def leaderboard():
    hero("COMMUNITY / VERIFIED PROGRESS", "За репутацией стоит работа", "XP за подтверждённые этапы и отзывы. Рядом всегда виден объём оценённого опыта.")
    rows = []
    for team in db.load_records("teams"):
        stats = db.team_stats(team["id"])
        rows.append({"Команда": team["name"], "XP": stats["xp"], "Средняя оценка": stats["average"], "Оценённых задач": stats["completed"], "Подтверждённых этапов": stats["milestones"], "Навыки": ", ".join(team.get("skills", []))})
    rows.sort(key=lambda r: (-r["XP"], -r["Оценённых задач"], r["Команда"]))
    st.dataframe([{"Место": i, **row} for i, row in enumerate(rows, 1)], hide_index=True, width="stretch")
    st.info("Рейтинг помогает сравнить команды. Он не назначает исполнителей и не ограничивает каталог.")
    st.caption("Этап +10 XP, максимум 2 на задачу. Отзыв: 1 ★ −20, 2 ★ −10, 3 ★ 0, 4 ★ +20, 5 ★ +40. Баланс не опускается ниже нуля.")


def about():
    hero("AI SANA / HACKATHON MVP", "Понятная задача — сильный результат", "От короткой идеи до выбора команды, сдачи решения и отзыва бизнеса.")
    st.markdown("**Сценарий:** идея → интерпретация → вопросы → подтверждённая карточка → каталог → предложение → выбор → этап → сдача → отзыв.")
    st.info("Демо без регистрации: переключение команды не является авторизацией. Используйте синтетические данные. JSON рассчитан на один серверный процесс.")
    st.write("Рейтинг детерминированный. OpenAI помогает формулировать и уточнять. Локальный режим — обозначенная заглушка. Сопоставление ожиданий — подсказка по ключевым словам.")
    with st.expander("AI-контракт: промпт, вход и выход"):
        st.code(INSTRUCTIONS, language="text")
        st.json({"mode": "draft", "description": "Хотим AI для анализа отзывов", "confirmed_interpretation": "", "current_card": {}, "answers": []})
        st.json(SCHEMA)
        st.caption("При ошибке API, JSON, схемы или неподтверждённых числах/ссылках/контактах результат отклоняется. Черновик сохраняется. Семантическая истинность требует проверки человеком.")
    with st.expander("Формула рейтинга"):
        st.dataframe(task_readiness({})["breakdown"], hide_index=True)
        st.write("Пустые поля и «пока не знаю» = 0. Редактирование снимает подтверждение. Контекст и потребность — по 10; контакт и обратная связь — по 5.")
    st.link_button("Страница хакатона", "https://learn.spira.to/hackathons/df4743f5-c492-415c-b45a-1f13adb78e06")


if S.get("pending_description"):
    S.business_description = S.pop("pending_description")
    S.saved_description = S.business_description
if S.get("pending_team"):
    S.active_team = S.pop("pending_team")
with st.sidebar:
    st.markdown("## ↗ Развилка")
    st.caption("TASKFORGE · AI SANA")
    st.divider()
    page = st.radio("Пространство", PAGES, key="navigation", label_visibility="collapsed")
    st.divider()
    try:
        teams = db.load_records("teams")
    except (OSError, ValueError):
        st.error("Не удалось прочитать профили команд. Проверьте data/teams.json; исходные данные не изменены.")
        st.stop()
    ids = [t["id"] for t in teams]
    if ids:
        if S.get("active_team") not in ids:
            S.active_team = ids[0]
        names = {t["id"]: t["name"] for t in teams}
        st.selectbox("Активная команда", ids, format_func=lambda tid: names[tid], key="active_team")
    st.caption("Демонстрационные роли · без входа")
    st.divider()
    st.caption("ГОТОВНОСТЬ ЗАДАЧ")
    st.caption("Draft 0–39\n\nWorkable 40–69\n\nReady 70–89\n\nPriority 90–100")
    st.caption("Решение всегда за человеком.")
if S.get("notice"):
    st.success(S.pop("notice"))
try:
    dict(zip(PAGES, [constructor, catalog, business, team_page, leaderboard, about]))[page]()
except (OSError, ValueError) as error:
    st.error(str(error))
