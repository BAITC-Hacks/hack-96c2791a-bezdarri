"""Run with: python -m streamlit run app.py"""

from html import escape
import logging
import json

import streamlit as st

from services.ai import AIError, TASK_KEYS, analyze_task
from services.scoring import FIELDS, task_readiness
from services.storage import add_record, load_records, submit_proposal, validate_url
from services.briefs import generate_interpretations
from ui.components import (PAGES, FIELD_LABELS, inject_styles, page_header, empty_state,
                           go_to, section_heading, status_label)
from ui.local_copy import direction_options

st.set_page_config(page_title="TaskForge · от задачи к результату", page_icon="✦", layout="wide")
inject_styles()
st.markdown('<div class="tf-mobile-brand">TF · TaskForge</div>', unsafe_allow_html=True)

# Temporary local diagnostics: state transitions only, never prompts or credentials.
logger = logging.getLogger("taskforge.ui")
logger.setLevel(logging.INFO)
if not logger.handlers:
    logger.addHandler(logging.StreamHandler())
logger.propagate = False


def show_readiness(task, *, prominent=False, previous_score=None, stale=False, summary_container=None):
    result = task_readiness(task)
    with summary_container if summary_container is not None else st.container():
        if prominent:
            st.subheader("Готовность задачи")
            st.caption("Насколько понятно команде, что нужно сделать.")
            score_column, improvement_column = st.columns(2)
            score_column.metric("Готовность", f"{result['score']}/100", status_label(result["level"]), delta_color="off")
            if previous_score is not None:
                improvement_column.metric(
                    "Изменение" if not stale else "Предыдущая оценка",
                    f"{previous_score} → {result['score']}",
                    f"{result['score'] - previous_score:+d} баллов",
                )
        else:
            st.metric("Готовность", f"{result['score']}/100", status_label(result["level"]), delta_color="off")
        st.progress(result["score"] / 100)
        st.caption("Оценка качества с AI" if task.get("ai_analysis") else "Чек-лист заполнения · без AI")
        if task.get("ai_analysis"):
            improvements = sorted(result["breakdown"],
                                  key=lambda row: row["Maximum"] - row["Points"], reverse=True)
            suggestions = [row["Improvement"] for row in improvements
                           if row["Points"] < row["Maximum"] and row["Improvement"].strip()]
        else:
            suggestions = [f"Заполните поле «{FIELD_LABELS[key]}» (+{weight} баллов)."
                           for key, _, weight, _ in FIELDS if not task.get(key, "").strip()]
        suggestions = [suggestion for suggestion in suggestions
                       if suggestion.strip().rstrip(".! ").casefold() not in
                       {"no improvement needed", "no improvements needed", "no improvement necessary",
                        "no action needed", "no changes needed", "none", "n/a"}]
        if result["missing"]:
            st.caption(f"Можно уточнить ещё {len(result['missing'])} полей. Начните с самого важного:")
            for suggestion in suggestions[:2]:
                st.write("• " + suggestion)
        elif not task.get("ai_analysis"):
            st.success("Все поля заполнены. Проверьте содержание перед публикацией.")
        with st.expander("Как считается оценка"):
            categories = {
                "Context and need": "Контекст и проблема", "Data/materials": "Данные и материалы",
                "Expected result": "Ожидаемый результат", "Success criteria": "Критерии успеха",
                "Constraints": "Ограничения", "Users": "Пользователи", "Business contact": "Контакт",
            }
            columns = {"Category": "Критерий", "Points": "Баллы", "Maximum": "Максимум",
                       "Reason": "Обоснование", "Improvement": "Как улучшить"}
            st.table([{columns.get(key, key): categories.get(value, value) if key == "Category" else value
                       for key, value in row.items()} for row in result["breakdown"]])
            st.caption("0–39 · Черновик   /   40–69 · Нужны уточнения   /   70–89 · Можно начинать   /   90–100 · Подробная задача")
            st.caption("Любой балл позволяет опубликовать задачу. В ручном режиме оценивается заполненность, а не качество текста.")
            for suggestion in suggestions[2:]:
                st.write("• " + suggestion)
    return result


def save_card_edit(key):
    st.session_state.draft[key] = st.session_state[f"card_{key}"].strip()
    st.session_state.confirm_publish = False
    if key == "expected_result" and st.session_state.get("selected_direction"):
        if st.session_state.draft[key]:
            st.session_state.selected_direction = {
                "title": "Custom outcome", "outcome": st.session_state.draft[key],
                "source": "Business edit", "user_action": "", "acceptance_hint": "",
            }
        else:
            st.session_state.pop("selected_direction", None)


def choose_direction(option, source):
    state = st.session_state
    state.draft["expected_result"] = option["outcome"]
    state.selected_direction = {**option, "source": source}
    state.direction_description = state.get("business_description", "").strip()
    state.confirm_publish = False


def change_description():
    state = st.session_state
    state.saved_description = state.business_description
    state.confirm_publish = False
    # Old hypotheses remain in the draft until explicitly changed, but cannot be
    # silently carried into a new source description.
    if state.get("direction_description") != state.business_description.strip():
        state.pop("selected_direction", None)
        state.pop("directions", None)


def request_directions(use_ai):
    state = st.session_state
    if not state.get("business_description", "").strip():
        state.direction_error = "Сначала опишите проблему бизнеса в поле выше."
        return
    try:
        with st.spinner("Ищем три возможных результата…"):
            state.directions = generate_interpretations(state.get("business_description", ""), use_ai=use_ai)
        state.direction_error = None
    except (AIError, ValueError) as error:
        state.direction_error = str(error)


def reset_draft():
    state = st.session_state
    for key in list(state):
        if key.startswith(("card_", "answer_")) or key in {
            "draft", "analysis", "analysis_job", "analysis_version", "answer_history",
            "previous_score", "analyzed_description", "saved_description", "business_description",
            "directions", "selected_direction", "direction_description", "direction_error",
            "ai_error", "confirm_publish", "task_industry", "published_signature",
            "saved_industry", "demo_requested", "demo_notice",
        }:
            del state[key]


def direction_picker():
    st.caption("За одной проблемой могут стоять разные решения. Сравните три варианта и выберите нужный результат.")
    ai, guided = st.columns(2)
    ai.button("Предложить 3 варианта с AI", key="explore_ai", on_click=request_directions, args=(True,), use_container_width=True)
    guided.button("Посмотреть варианты без AI", key="explore_guided", on_click=request_directions, args=(False,),
                  help="Готовые шаблоны для обсуждения. Не требуют ключа и не добавляют факты о бизнесе.", use_container_width=True)
    if st.session_state.get("direction_error"):
        st.warning(st.session_state.direction_error)
    result = st.session_state.get("directions")
    if result:
        st.caption("Гипотезы от AI · требуют вашего выбора" if result["source"] == "AI" else "Локальные шаблоны · без AI")
        for index, (column, option) in enumerate(zip(st.columns(3), direction_options(result))):
            with column, st.container(border=True, key=f"panel_direction_{index}"):
                st.markdown(f"**{index + 1:02d} · {option['title']}**")
                st.write(option["outcome"])
                st.caption("Что сможет делать пользователь")
                st.write(option["user_action"])
                st.caption("Как можно проверить результат")
                st.write(option["acceptance_hint"])
                st.button("Выбрать этот результат", key=f"direction_{index}", on_click=choose_direction,
                          args=(option, result["source"]), use_container_width=True)
    if st.session_state.get("selected_direction"):
        st.success("Выбранный результат: " + st.session_state.selected_direction["outcome"])
    st.caption("Выбор заполнит поле «Что нужно получить». Вы сможете отредактировать его в карточке.")


def run_analysis(mode):
    """Save results before spinner cleanup can yield to a queued widget rerun."""
    state = st.session_state
    logger.info("Analyze button triggered: mode=%s", mode)
    description = state.get("business_description", "").strip()
    if mode == "draft" and not description:
        state.ai_error = "Сначала опишите проблему бизнеса."
        return
    answers = list(state.get("answer_history", []))
    if mode == "clarify":
        new_answers = [{**q, "answer": state.get(f"answer_{state.analysis_version}_{i}", "").strip()}
                       for i, q in enumerate(state.analysis["questions"])]
        new_answers = [answer for answer in new_answers if answer["answer"]]
        if not new_answers:
            state.ai_error = "Ответьте хотя бы на один вопрос."
            return
        answers.extend(new_answers)
    source_description = description if mode == "draft" else state.get("analyzed_description", "")
    if mode == "draft" and state.get("selected_direction"):
        source_description += "\nBusiness-selected expected result: " + state.selected_direction["outcome"]
    current_card = None if mode == "draft" else dict(state.draft)
    # Capture a session-owned object before the API call. Mutating this object does
    # not yield to Streamlit, unlike accessing st.session_state after the call.
    job = {"mode": mode, "description": source_description, "answers": answers}
    state.analysis_job = job
    with st.spinner("Собираем карточку и уточняющие вопросы…"):
        try:
            result = analyze_task(source_description, [] if mode == "draft" else answers, current_card, mode)
        except AIError as error:
            job["error"] = str(error)
            logger.info("Analysis failed; preserving current draft and prior result")
        else:
            job["result"] = result
            logger.info("Result stored in session_state job: questions=%s score=%s",
                        len(result["questions"]), result["scoring"]["total_score"])


def apply_analysis_result():
    """Apply a completed request once, before any editable widgets are rendered."""
    state = st.session_state
    job = state.get("analysis_job", {})
    if "error" in job:
        state.ai_error = job["error"]
        state.analysis_job = {}
        return
    if "result" not in job:
        return
    result, mode = job["result"], job["mode"]
    previous = state.get("analysis")
    state.previous_score = previous["scoring"]["total_score"] if previous and mode != "draft" else None
    state.analysis = result
    state.draft = dict(result["task"])
    state.answer_history = [] if mode == "draft" else job["answers"]
    if mode == "draft":
        state.analyzed_description = job["description"]
    state.analysis_version = state.get("analysis_version", 0) + 1
    state.confirm_publish = False
    state.ai_error = None
    state.analysis_job = {}
    logger.info("Result stored in session_state: version=%s questions=%s score=%s",
                state.analysis_version, len(result["questions"]), result["scoring"]["total_score"])


EXAMPLE_DESCRIPTION = (
    "У интернет-магазина много отзывов на товары. Менеджеры читают их вручную и "
    "пропускают повторяющиеся жалобы. Хотим быстро видеть основные проблемы."
)
EXAMPLE_CARD = {
    "title": "Помощник для анализа отзывов магазина",
    "context": "Учебный пример: менеджеры интернет-магазина вручную читают отзывы покупателей.",
    "need": "Помочь менеджеру находить повторяющиеся жалобы и выбирать, на что ответить в первую очередь.",
    "users": "Менеджер по работе с клиентами и руководитель магазина.",
    "data_materials": "Для прототипа используем небольшой набор синтетических отзывов в CSV.",
    "constraints": "Прототип за две недели. Без персональных данных и автоматической отправки ответов.",
    "expected_result": "Дашборд с группами жалоб, примерами отзывов и приоритетом ответа.",
    "success_criteria": "Менеджер загружает CSV, видит группы жалоб и может открыть исходные отзывы каждой группы.",
    "contact": "Учебный заказчик. Обсуждение вопросов в общем чате команды, демонстрация раз в неделю.",
}


def load_example():
    state = st.session_state
    if any(state.get("draft", {}).values()) or state.get("business_description", "").strip() or state.get("saved_description", "").strip():
        state.demo_notice = "Ваш черновик сохранён. Чтобы открыть учебный пример, сначала нажмите «Новый черновик»."
        return
    state.draft = dict(EXAMPLE_CARD)
    state.business_description = EXAMPLE_DESCRIPTION
    state.saved_description = EXAMPLE_DESCRIPTION
    state.task_industry = "Ритейл"
    state.saved_industry = "Ритейл"
    state.confirm_publish = False
    state.demo_notice = "Это учебный пример с вымышленными условиями. Он ещё не опубликован — измените поля или пройдите сценарий как есть."


def save_industry():
    st.session_state.saved_industry = st.session_state.task_industry
    st.session_state.confirm_publish = False


def open_catalog():
    st.session_state.update(catalog_search="", catalog_industry="All", catalog_readiness="All", catalog_sort="Newest first")
    go_to("Catalog")


def create_task():
    page_header("ДЛЯ БИЗНЕСА", "Понятная задача — сильный результат",
                "Опишите проблему, договоритесь о результате и пригласите команды предложить решение.")
    state = st.session_state
    if "draft" not in state:
        state.draft = {key: "" for key in TASK_KEYS}
    apply_analysis_result()
    if state.pop("demo_requested", False):
        load_example()
    if state.get("demo_notice"):
        st.info(state.demo_notice)
    if "business_description" not in state:
        state.business_description = state.get("saved_description", "")
    with st.container(border=True, key="panel_brief_intro"):
        section_heading("01", "Начните с проблемы", "Несколько предложений своими словами. AI поможет собрать карточку, а детали можно заполнить вручную.")
        st.text_area("Что вы хотите улучшить?", key="business_description", height=110,
                     placeholder="Например: получаем сотни отзывов и не успеваем замечать повторяющиеся жалобы…",
                     on_change=change_description)
        analyze, example = st.columns([1, 1])
        analyze.button("Сформировать с AI", key="analyze", type="primary", on_click=run_analysis, args=("draft",), use_container_width=True)
        example.button("Подставить пример", key="load_example", on_click=load_example, use_container_width=True,
                       help="Готовая учебная карточка без запроса к AI. Ваш заполненный черновик сохранится.")
        with st.expander("Развилка · какое решение вам действительно нужно?", expanded=bool(state.get("directions"))):
            direction_picker()
        if state.get("ai_error"):
            st.error(state.ai_error)
    analysis = state.get("analysis")
    if analysis and analysis["questions"]:
        with st.container(border=True, key="panel_clarifications"):
            st.subheader("Уточним детали")
            st.caption("Ответьте на вопросы, чтобы команда лучше поняла задачу. Неизвестное можно пропустить.")
            with st.form(f"clarifications_{state.analysis_version}"):
                for i, question in enumerate(analysis["questions"]):
                    st.text_area(question["question"], key=f"answer_{state.analysis_version}_{i}", height=90)
                st.form_submit_button("Учесть ответы", key="clarify", on_click=run_analysis, args=("clarify",), type="primary")
    editor, summary = st.columns([1.8, 1], gap="large")
    with editor, st.container(border=True, key="panel_card_editor"):
        section_heading("02", "Проверьте карточку", "Заполните известные факты. Изменения сохраняются в черновике при переключении страниц.")
        tabs = st.tabs(["Задача", "Результат", "Условия"])
        groups = [
            ("title", "context", "need", "users"),
            ("expected_result", "success_criteria"),
            ("data_materials", "constraints", "contact"),
        ]
        placeholders = {
            "title": "Коротко: что нужно сделать?",
            "context": "Как сейчас устроен процесс?",
            "need": "Что мешает бизнесу и почему это важно?",
            "users": "Кто будет пользоваться решением?",
            "expected_result": "Например, дашборд, прототип или аналитический отчёт.",
            "success_criteria": "Что заказчик должен увидеть или проверить, чтобы принять работу?",
            "data_materials": "Какие данные доступны команде? Есть ли пример?",
            "constraints": "Срок, бюджет, инструменты и ограничения доступа.",
            "contact": "Как задать вопрос заказчику и как часто обсуждать прогресс?",
        }
        for tab, keys in zip(tabs, groups):
            with tab:
                for key in keys:
                    state[f"card_{key}"] = state.draft[key]
                    widget = st.text_input if key == "title" else st.text_area
                    kwargs = {} if key == "title" else {"height": 100}
                    widget(FIELD_LABELS[key], key=f"card_{key}", placeholder=placeholders[key],
                           on_change=save_card_edit, args=(key,), **kwargs)
                if "contact" in keys:
                    if "task_industry" not in state:
                        state.task_industry = state.get("saved_industry", "")
                    st.text_input("Отрасль · необязательно", key="task_industry", placeholder="Например, ритейл или образование",
                                  on_change=save_industry)
    task = dict(state.draft)
    industry = state.get("task_industry", "").strip()
    stale = bool(analysis and task != analysis["task"])
    with summary:
        readiness_summary = st.container(border=True, key="panel_readiness")
        if analysis:
            result = show_readiness({**analysis["task"], "ai_analysis": analysis}, prominent=True,
                                    previous_score=state.get("previous_score"), stale=stale,
                                    summary_container=readiness_summary)
        else:
            result = show_readiness(task, prominent=True, summary_container=readiness_summary)
        if stale:
            st.warning("Карточка изменилась. Обновите AI-оценку перед публикацией.")
        st.button("Обновить AI-оценку", key="rescore", on_click=run_analysis, args=("rescore",), use_container_width=True,
                  help="Проверить качество заполненной карточки с AI. В ручном режиме этот шаг необязателен.")
        st.caption("Готовность относится к задаче. Команды получают XP позже — за подтверждённую работу.")
    with st.container(border=True, key="panel_publish"):
        section_heading("03", "Опубликуйте задачу", "После публикации студенты смогут предложить решения. Вы сами решите, кого пригласить.")
        confirmed = st.checkbox("Я проверил карточку и подтверждаю факты о задаче.", key="confirm_publish")
        signature = json.dumps({"task": task, "industry": industry}, sort_keys=True, ensure_ascii=False)
        already_published = state.get("published_signature") == signature
        if st.button("Опубликовать задачу", key="publish", type="primary",
                     disabled=stale or already_published or bool(analysis and not confirmed)):
            if not task["title"]:
                st.error("Укажите название задачи во вкладке «Задача».")
            elif not confirmed:
                st.error("Проверьте карточку и подтвердите факты перед публикацией.")
            else:
                values = {**task, "industry": industry, "readiness_score": result["score"], "readiness_level": result["level"]}
                if analysis:
                    values["ai_analysis"] = analysis
                if state.get("selected_direction"):
                    values["selected_direction"] = state.selected_direction
                add_record("tasks", values)
                state.published_signature = signature
                already_published = True
        if already_published:
            st.success("Задача опубликована. Теперь команды могут отправлять предложения.")
            st.button("Посмотреть в каталоге →", key="view_published", on_click=open_catalog)
        download, reset = st.columns(2)
        download.download_button("Скачать карточку", data=json.dumps(task, ensure_ascii=False, indent=2),
                                 file_name="task-brief.json", mime="application/json", key="export_draft", use_container_width=True)
        reset.button("Новый черновик", key="new_brief", on_click=reset_draft, use_container_width=True,
                     help="Очистить текущий черновик и начать другую задачу. Опубликованные задачи сохранятся.")


def proposal_form(task_id):
    with st.form(f"proposal_{task_id}", clear_on_submit=False):
        st.subheader("Предложите своё решение")
        st.caption("Расскажите, что вы сделаете и как бизнес сможет проверить результат. Все поля, кроме ссылки, обязательны.")
        values = {
            "team_name": st.text_input("Название команды", key=f"team_{task_id}", help="Укажите существующее название или придумайте новое — профиль появится после отправки."),
            "solution_idea": st.text_area("Идея решения", key=f"idea_{task_id}", height=90),
            "plan": st.text_area("План работы", key=f"plan_{task_id}", height=90),
            "definition_of_done": st.text_area("Мы считаем задачу выполненной, когда…", key=f"done_{task_id}", height=90,
                help="Опишите результат, который заказчик сможет увидеть и принять."),
            "estimated_time": st.text_input("Сколько времени понадобится", key=f"timeline_{task_id}", placeholder="Например, 2 недели"),
            "prototype_url": st.text_input("Ссылка на прототип · необязательно", key=f"url_{task_id}", placeholder="https://example.com/demo"),
        }
        submitted = st.form_submit_button("Отправить предложение", key=f"proposal_submit_{task_id}", type="primary")
    if submitted:
        values = {key: value.strip() for key, value in values.items()}
        if any(not values[key] for key in ("team_name", "solution_idea", "plan", "estimated_time", "definition_of_done")):
            st.error("Укажите команду, идею, план, срок и условие готовности результата.")
            return
        try:
            validate_url(values["prototype_url"])
        except ValueError:
            st.error("Ссылка на прототип должна начинаться с http:// или https:// и содержать адрес сайта.")
            return
        submit_proposal(task_id, values)
        st.success("Предложение отправлено. После решения бизнеса статус появится в кабинете команды.")
        st.button("В кабинет команды →", key=f"proposal_next_{task_id}", on_click=go_to, args=("Team Workspace",))


def task_industry(task):
    """Older JSON records need no migration to appear in the catalog."""
    industry = task.get("industry")
    return industry.strip() if isinstance(industry, str) and industry.strip() else "Other"


def catalog():
    page_header("ДЛЯ КОМАНД", "Найдите задачу для своей команды",
                "Выберите интересную проблему, изучите ожидаемый результат и предложите свой подход.")
    published = load_records("tasks")
    if not published:
        empty_state("Здесь появятся задачи бизнеса", "Создайте первую задачу или откройте учебный пример в разделе «Обзор».")
        st.button("Создать задачу", on_click=go_to, args=("Create Task",))
        return
    query = st.text_input("Поиск по задачам", key="catalog_search", placeholder="Название, проблема или ожидаемый результат…").strip().casefold()
    topic_column, readiness_column, sort_column = st.columns(3)
    industries = sorted({task_industry(task) for task in published}, key=str.casefold)
    topic = topic_column.selectbox("Отрасль", ["All"] + [name for name in industries if name != "All"], key="catalog_industry",
                                   format_func=lambda value: {"All": "Все отрасли", "Other": "Другое"}.get(value, value))
    level = readiness_column.selectbox("Готовность задачи", ["All", "Draft", "Working", "Ready", "Priority"], key="catalog_readiness", format_func=status_label)
    sort_labels = {"Highest readiness": "Сначала подробные", "Lowest readiness": "Сначала требующие уточнений", "Newest first": "Сначала новые"}
    order = sort_column.selectbox("Порядок", list(sort_labels), key="catalog_sort", format_func=sort_labels.get)
    if order == "Newest first":
        tasks = sorted(published, key=lambda task: task.get("created_at", ""), reverse=True)
    else:
        tasks = sorted(published, key=lambda task: task.get("created_at", ""), reverse=True)
        tasks.sort(key=lambda task: task_readiness(task)["score"], reverse=order == "Highest readiness")
    tasks = [task for task in tasks
             if (level == "All" or task_readiness(task)["level"] == level)
             and (topic == "All" or task_industry(task) == topic)
             and (not query or query in " ".join(str(task.get(key, "")) for key in ("title", "context", "need", "expected_result")).casefold())]
    st.caption(f"Найдено: {len(tasks)} из {len(published)} · Балл показывает готовность задачи, а не её сложность. Откликнуться можно на любую.")
    if not tasks:
        empty_state("Ничего не нашлось", "Попробуйте другую формулировку или сбросьте фильтры.")
        st.button("Сбросить фильтры", key="reset_catalog", on_click=open_catalog)
    for task in tasks:
        result = task_readiness(task)
        with st.container(border=True, key=f"panel_task_{task['id']}"):
            st.markdown(
                f'<div class="tf-card-header"><div><h3 class="tf-card-title">{escape(task["title"])}</h3>'
                f'<span class="tf-badge">{escape("Другое" if task_industry(task) == "Other" else task_industry(task))}</span></div>'
                f'<div class="tf-score tf-{result["level"].lower()}"><strong>{result["score"]}</strong>'
                f'<small> / 100</small><span>{status_label(result["level"])}</span></div></div>',
                unsafe_allow_html=True,
            )
            preview = " ".join((task.get("need") or task.get("context") or "Детали можно уточнить у заказчика.").split())
            st.write(preview if len(preview) <= 220 else preview[:217] + "…")
            if task.get("expected_result"):
                outcome = " ".join(task["expected_result"].split())
                st.caption("Результат: " + (outcome if len(outcome) <= 160 else outcome[:157] + "…"))
            with st.expander(f"{task['title']} — {result['score']}/100 · Подробнее и отклик"):
                brief, response = st.tabs(["Карточка задачи", "Предложить решение"])
                with brief:
                    for key, _, _, _ in FIELDS:
                        st.markdown(f"**{FIELD_LABELS[key]}**")
                        st.write(task.get(key) or "Пока не указано · можно уточнить у заказчика")
                    show_readiness(task)
                    st.download_button("Скачать условия задачи", data=json.dumps(task, ensure_ascii=False, indent=2),
                                       file_name=f"task-{task['id']}.json", mime="application/json", key=f"export_{task['id']}")
                with response:
                    proposal_form(task["id"])


from ui.business_page import dashboard
from ui.team_pages import team_workspace, teams_page
from ui.overview import overview

st.sidebar.markdown('<div class="tf-brand"><span class="tf-brand-mark">TF</span><span class="tf-brand-name">TaskForge</span></div>'
                    '<p class="tf-brand-subtitle">Реальные задачи. Проверенный опыт.</p>', unsafe_allow_html=True)
st.sidebar.caption("РАБОЧЕЕ ПРОСТРАНСТВО")
page = st.sidebar.radio("Разделы", list(PAGES), format_func=PAGES.get, key="page", label_visibility="collapsed")
st.sidebar.divider()
with st.sidebar.expander("Как пройти весь сценарий"):
    st.write("1. Бизнес публикует задачу.\n\n2. Команда предлагает решение.\n\n3. Бизнес приглашает команду.\n\n4. Команда сдаёт результат.\n\n5. Бизнес принимает работу и оставляет отзыв.")
    st.button("Открыть обзор", key="sidebar_overview", on_click=go_to, args=("Overview",), use_container_width=True)
st.sidebar.caption("Демо для хакатона · без регистрации")
st.sidebar.caption("Переключайтесь между кабинетами, чтобы попробовать обе роли.")
try:
    {"Overview": overview, "Create Task": create_task, "Catalog": catalog, "Business Dashboard": dashboard,
     "Team Workspace": team_workspace, "Teams & Ratings": teams_page}[page]()
except (OSError, ValueError) as error:
    st.error("Не удалось прочитать или сохранить данные. Попробуйте ещё раз.")
    with st.expander("Подробности ошибки"):
        st.code(str(error), language="text")
