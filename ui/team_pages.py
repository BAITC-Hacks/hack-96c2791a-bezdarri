"""Team delivery workspace and evidence-based team profiles."""

from datetime import datetime
from urllib.parse import urlparse

import streamlit as st

from services.storage import load_records
from services.workflow import (
    get_engagement,
    leaderboard,
    submit_delivery,
    submit_milestone,
    team_stats,
    update_team_profile,
)
from ui.components import empty_state, go_to, page_header, status_badge, status_label


def _date(value):
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%d.%m.%Y, %H:%M UTC")
    except (ValueError, TypeError):
        return str(value)


def _tags(value):
    if isinstance(value, str):
        return value
    return ", ".join(value or [])


def _link(label, url):
    """Never turn stored data into an unsafe clickable link."""
    try:
        parsed = urlparse(url or "")
    except ValueError:
        return
    if parsed.scheme in {"https", "http"} and parsed.netloc:
        st.link_button(label, url)


def _flash():
    message = st.session_state.pop("team_page_notice", None)
    if message:
        st.success(message)


def _error_text(error):
    messages = {
        "Milestone title is required.": "Добавьте название этапа.",
        "Milestone title must be at most 200 characters.": "Сократите название этапа до 200 символов.",
        "Evidence of completed work is required.": "Опишите выполненную работу и приложите подтверждение.",
        "Evidence of completed work must be at most 12000 characters.": "Сократите описание этапа до 12 000 символов.",
        "Delivery summary is required.": "Опишите результат и то, как бизнес может его проверить.",
        "Delivery summary must be at most 12000 characters.": "Сократите описание результата до 12 000 символов.",
        "Use a valid http:// or https:// URL.": "Укажите корректную ссылку, которая начинается с https:// или http://.",
        "The business must accept this proposal before work can begin.": "Сначала бизнес должен выбрать вашу команду.",
        "This delivery has already been accepted; its work is locked.": "Результат уже принят. Изменить его больше нельзя.",
        "Wait for the business to accept the delivery or request a revision.": "Результат на проверке. Дождитесь приёмки или запроса на доработку.",
        "A team can submit at most two milestones for one task.": "Для одной задачи можно отправить не более двух этапов.",
        "Team not found.": "Команда не найдена. Обновите страницу и выберите другую команду.",
        "Proposal not found.": "Предложение не найдено. Обновите страницу.",
        "The task or team no longer exists.": "Задача или команда больше недоступна. Обновите страницу.",
        "Record not found.": "Профиль больше недоступен. Обновите страницу.",
        "Each skills entry must be at most 60 characters.": "Название каждого навыка должно быть не длиннее 60 символов.",
        "Each interests entry must be at most 60 characters.": "Название каждого интереса должно быть не длиннее 60 символов.",
        "Use at most 20 skills entries.": "Укажите не больше 20 навыков.",
        "Use at most 20 interests entries.": "Укажите не больше 20 интересов.",
    }
    if isinstance(error, OSError):
        return "Не удалось сохранить изменения. Проверьте доступ к папке данных и попробуйте ещё раз."
    return messages.get(str(error), str(error))


def _save(action, message, *args, **kwargs):
    try:
        action(*args, **kwargs)
    except (ValueError, OSError) as error:
        st.error(_error_text(error))
    else:
        st.session_state.team_page_notice = message
        st.rerun()


def _metrics(stats):
    xp, rating, completed, active = st.columns(4)
    xp.metric("Заработано XP", stats["xp"])
    rating.metric("Оценка бизнеса", f"{stats['average_rating']:.1f} / 5" if stats["review_count"] else "Новая")
    rating.caption(f"Отзывов: {stats['review_count']}" if stats["review_count"] else "У команды пока нет оценок")
    completed.metric("Задач выполнено", stats["completed_tasks"])
    active.metric("Сейчас в работе", stats["active_tasks"])


def _profile_editor(team):
    team_id = team["id"]
    with st.expander("Профиль команды · навыки и интересы"):
        st.caption("Этот профиль увидит бизнес при выборе команды.")
        with st.form(f"team_profile_form_{team_id}"):
            about = st.text_area("О команде", value=team.get("about", ""),
                                 key=f"team_about_{team_id}", max_chars=2000,
                                 placeholder="Кто вы, какие задачи решаете и как организуете работу.")
            skills = st.text_input("Навыки", value=_tags(team.get("skills")),
                                   key=f"team_skills_{team_id}", max_chars=1000,
                                   placeholder="Python, дизайн интерфейсов, анализ данных",
                                   help="Разделяйте навыки запятыми.")
            interests = st.text_input("Интересы", value=_tags(team.get("interests")),
                                      key=f"team_interests_{team_id}", max_chars=1000,
                                      placeholder="Образование, ретейл, экология",
                                      help="Разделяйте интересы запятыми.")
            save = st.form_submit_button("Сохранить профиль", key=f"team_profile_save_{team_id}")
        if save:
            _save(update_team_profile, "Профиль команды обновлён.", team_id,
                  about=about, skills=skills, interests=interests)


def _milestones(proposal_id, engagement):
    milestones = engagement.get("milestones", [])
    confirmed = sum(milestone["status"] == "Confirmed" for milestone in milestones)
    st.caption("Покажите промежуточный результат. За каждый подтверждённый бизнесом этап — +10 XP, максимум два этапа на задачу.")
    st.progress(confirmed / 2, text=f"Подтверждено этапов: {confirmed} из 2")
    for index, milestone in enumerate(milestones, start=1):
        with st.container(border=True, key=f"panel_milestone_{proposal_id}_{milestone['id']}_{index}"):
            st.write(f"{index}. {milestone['title']}")
            st.caption("Подтверждён · +10 XP" if milestone["status"] == "Confirmed" else "На проверке у бизнеса")
            st.write(milestone["evidence"])
            st.caption(_date(milestone.get("confirmed_at") or milestone.get("created_at")))
    if len(milestones) < 2 and engagement["status"] in {"In progress", "Revision requested"}:
        with st.expander("Отправить этап на проверку", expanded=not milestones):
            slot = f"{proposal_id}_{len(milestones)}"
            with st.form(f"milestone_form_{slot}"):
                title = st.text_input("Название этапа", key=f"milestone_title_{slot}",
                                      placeholder="Прототип проверен на трёх пользователях")
                evidence = st.text_area("Что сделано и как это проверить", key=f"milestone_evidence_{slot}",
                                        placeholder="Опишите результат этапа, добавьте выводы теста или ссылку на прототип.")
                submitted = st.form_submit_button("Отправить этап", key=f"milestone_submit_{proposal_id}")
            if submitted:
                _save(submit_milestone, "Этап отправлен. XP начислится после подтверждения бизнесом.", proposal_id, title, evidence)
    elif not milestones:
        st.caption("Промежуточные этапы не отправлялись. Они необязательны для сдачи результата.")


def _delivery(proposal_id, engagement):
    delivery = engagement.get("delivery")
    review = engagement.get("review")
    if engagement["status"] == "In progress":
        st.info("Следующий шаг: подготовьте решение и отправьте результат на проверку. Промежуточный прогресс можно показать во вкладке «Этапы».")
    elif engagement["status"] == "Revision requested":
        st.warning("Нужна доработка. Учтите замечания бизнеса и отправьте новую версию результата.")
    elif engagement["status"] == "Delivery submitted":
        st.info("Результат на проверке у бизнеса. Здесь появится приёмка или конкретные замечания для доработки.")
    elif engagement["status"] == "Accepted":
        st.success("Результат принят. Осталось дождаться итоговой оценки и отзыва бизнеса.")
    if delivery:
        with st.container(border=True, key=f"panel_delivery_{proposal_id}"):
            st.caption(f"Версия {delivery.get('version', 1)} · {status_label(delivery['status'])} · {_date(delivery.get('submitted_at'))}")
            st.write(delivery["summary"])
            _link("Открыть результат", delivery.get("url"))
            if delivery.get("feedback"):
                st.markdown("**Замечания бизнеса**")
                st.write(delivery["feedback"])
    if review:
        notice = st.success if review["rating"] >= 4 else st.info
        notice(f"Работа завершена · оценка бизнеса {review['rating']} из 5")
        st.write(review["comment"])
        if review.get("criterion_feedback"):
            st.caption("Комментарий к согласованным критериям")
            st.write(review["criterion_feedback"])
        applied = review.get("xp_applied", review["xp_delta"])
        st.caption(f"XP за оценку: {review['xp_delta']:+d} · изменение баланса: {applied:+d}")
        if applied != review["xp_delta"]:
            st.caption("Штраф ограничен текущим балансом: XP не может стать отрицательным.")
    elif engagement["status"] in {"In progress", "Revision requested"}:
        with st.form(f"delivery_form_{proposal_id}_{delivery.get('version', 0) if delivery else 0}"):
            summary = st.text_area("Результат и способ проверки", value=delivery["summary"] if delivery else "",
                                   key=f"delivery_summary_{proposal_id}",
                                   placeholder="Что вы сделали, каким критериям соответствует решение и как бизнес может его проверить?",
                                   help="Согласованные критерии доступны во вкладке «Договорённости».")
            url = st.text_input("Ссылка на результат · необязательно", value=delivery.get("url", "") if delivery else "",
                                key=f"delivery_url_{proposal_id}", placeholder="https://example.com/demo")
            submitted = st.form_submit_button("Отправить новую версию" if delivery else "Отправить результат",
                                              key=f"delivery_submit_{proposal_id}", type="primary")
        if submitted:
            _save(submit_delivery, "Результат отправлен на проверку бизнесу.", proposal_id, summary, url=url)
    history = engagement.get("delivery_history", [])
    if history:
        with st.expander(f"История версий · {len(history)}"):
            for previous in reversed(history):
                st.caption(f"Версия {previous.get('version', '?')} · {_date(previous.get('submitted_at'))}")
                st.write(previous.get("summary", ""))
                _link("Открыть прошлую версию", previous.get("url"))
                if previous.get("feedback"):
                    st.caption("Замечания к этой версии")
                    st.write(previous["feedback"])


def _brief(proposal, task, engagement):
    agreed = {**task, **{field: engagement[field] for field in ("expected_result", "success_criteria")
                        if engagement and field in engagement}}
    if engagement:
        st.caption("Результат и критерии сохранены на момент начала работы — по ним бизнес проверяет решение.")
    business, team = st.columns(2, gap="large")
    with business:
        st.markdown("**Что нужно бизнесу**")
        for field, label in (("expected_result", "Ожидаемый результат"),
                             ("success_criteria", "Критерии успеха"),
                             ("constraints", "Ограничения"), ("data_materials", "Данные и материалы"),
                             ("contact", "Контакт и взаимодействие")):
            st.caption(label)
            st.write(agreed.get(field) or "Пока не указано")
    with team:
        st.markdown("**Предложение вашей команды**")
        for field, label in (("solution_idea", "Решение"), ("plan", "План"),
                             ("estimated_time", "Срок"), ("definition_of_done", "Когда задача будет выполнена")):
            st.caption(label)
            value = engagement.get(field) if engagement and field == "definition_of_done" else proposal.get(field)
            st.write(value or "Пока не указано")
        _link("Открыть прототип", proposal.get("prototype_url"))


def _proposal_card(proposal, task):
    proposal_id = proposal["id"]
    engagement = get_engagement(proposal_id) if proposal["status"] == "Accepted" and task else None
    with st.container(border=True, key=f"panel_proposal_{proposal_id}"):
        title, badge = st.columns([4, 1])
        with title:
            st.subheader(task.get("title", "Задача больше недоступна"))
        with badge:
            status_badge(engagement["status"] if engagement else proposal["status"])
        if proposal.get("created_at"):
            st.caption("Предложение отправлено " + _date(proposal["created_at"]))
        if proposal["status"] == "Pending":
            st.info("Ожидаем решения бизнеса по предложению. Пока можно выбрать ещё одну задачу в каталоге.")
        elif proposal["status"] == "Rejected":
            st.caption("Бизнес отклонил предложение. Это не влияет на XP команды. Вы можете предложить решение другой задачи.")
        elif not engagement:
            st.warning("Задача больше недоступна. Отправить результат можно будет после восстановления карточки.")
        if not engagement:
            with st.expander("Посмотреть задачу и предложение"):
                _brief(proposal, task, engagement)
            return
        result_tab, milestones_tab, brief_tab = st.tabs(["Результат", "Этапы", "Договорённости"])
        with result_tab:
            _delivery(proposal_id, engagement)
        with milestones_tab:
            _milestones(proposal_id, engagement)
        with brief_tab:
            _brief(proposal, task, engagement)


def team_workspace():
    page_header("ДЛЯ СТУДЕНТОВ", "Кабинет команды", "Ваши предложения, прогресс и результаты — всё по каждой задаче в одном месте.")
    _flash()
    teams = sorted(load_records("teams"), key=lambda team: team["name"].casefold())
    if not teams:
        empty_state("Начните с первой задачи", "Откройте каталог и отправьте предложение от имени команды. Здесь появится её рабочее пространство.")
        st.button("Найти задачу", key="team_empty_catalog", type="primary", on_click=go_to, args=("Catalog",))
        return
    by_id = {team["id"]: team for team in teams}
    selected, catalog = st.columns([3, 1], vertical_alignment="bottom")
    with selected:
        team_id = st.selectbox("Команда", list(by_id), format_func=lambda value: by_id[value]["name"],
                               key="team_workspace_select", help="В демо можно открыть рабочее пространство любой команды.")
    with catalog:
        st.button("Найти задачу", key="team_catalog", on_click=go_to, args=("Catalog",), use_container_width=True)
    _metrics(team_stats(team_id))
    _profile_editor(by_id[team_id])
    proposals = [proposal for proposal in load_records("proposals") if proposal.get("team_id") == team_id]
    tasks = {task["id"]: task for task in load_records("tasks")}
    st.subheader("Задачи команды")
    filter_labels = {"All": "Все", "Accepted": "Команда выбрана", "Pending": "Ждём решения", "Rejected": "Отклонены"}
    choice = st.radio("Статус предложения", list(filter_labels), format_func=filter_labels.get,
                      horizontal=True, key="team_work_filter", label_visibility="collapsed")
    matches = [proposal for proposal in proposals if choice == "All" or proposal["status"] == choice]
    if not matches:
        if proposals:
            empty_state("Здесь пока нет задач", "Выберите другой статус или откройте вкладку «Все».")
        else:
            empty_state("У команды пока нет предложений", "Найдите подходящую задачу в каталоге и расскажите, как вы её решите.")
    priorities = {"Accepted": 0, "Pending": 1, "Rejected": 2}
    for proposal in sorted(matches, key=lambda row: (priorities.get(row["status"], 3), row.get("created_at", ""))):
        _proposal_card(proposal, tasks.get(proposal["task_id"], {}))


def _reviewed_work(team):
    reviews = team["reviews"]
    if not reviews:
        st.info("У команды пока нет оценок. Изучите её навыки, предложение и прототип.")
    for index, review in enumerate(sorted(reviews, key=lambda row: row.get("created_at", ""), reverse=True)):
        with st.container(border=True, key=f"panel_review_{team['id']}_{review['task_id']}_{index}"):
            st.write(review["task_title"])
            st.caption(f"{review['rating']} из 5 ★ · {_date(review.get('created_at'))} · {review['xp_delta']:+d} XP за оценку")
            st.write(review["comment"])
            if review.get("criterion_feedback"):
                st.caption("Комментарий к критериям")
                st.write(review["criterion_feedback"])
                if review.get("success_criteria"):
                    st.caption("Согласованные критерии успеха")
                    st.write(review["success_criteria"])
            if review.get("summary"):
                with st.expander("Посмотреть результат"):
                    st.write(review["summary"])
                    _link("Открыть результат", review.get("url"))
    for index, project in enumerate(team.get("completed_projects", [])):
        if project.get("review"):
            continue
        with st.container(border=True, key=f"panel_project_{team['id']}_{project['task_id']}_{index}"):
            st.write(project["task_title"])
            st.caption("Результат принят · отзыв ещё не оставлен")
            st.write(project["summary"])
            _link("Открыть результат", project.get("url"))


def _xp_history(team):
    ledger = team["ledger"]
    if ledger:
        st.dataframe([
            {"Дата": _date(entry.get("created_at")), "Задача": entry["task_title"],
             "Событие": "Подтверждён этап" if entry["kind"] == "milestone" else "Отзыв бизнеса",
             "Изменение XP": entry["xp_delta"], "Начислено": entry["xp_applied"],
             "Баланс": entry["xp_after"]}
            for entry in reversed(ledger)
        ], hide_index=True, use_container_width=True)
    else:
        st.caption("Начислений пока нет. XP появляется после подтверждения работы бизнесом.")
    with st.expander("Как начисляется XP"):
        st.write("За подтверждённый этап команда получает +10 XP, максимум за два этапа на задачу. Итоговая оценка отдельно меняет баланс.")
        st.table({"Оценка бизнеса": ["1 ★", "2 ★", "3 ★", "4 ★", "5 ★"],
                  "Изменение XP": ["−20", "−10", "0", "+20", "+40"]})
        st.caption("Один итоговый отзыв на команду и задачу. Для оценки 1–2 бизнес указывает невыполненный критерий. Баланс не опускается ниже нуля.")


def _public_profile(team):
    st.subheader(team["name"])
    _metrics(team)
    if team.get("about"):
        st.write(team["about"])
    st.caption("Навыки: " + (_tags(team.get("skills")) or "пока не добавлены"))
    st.caption("Интересы: " + (_tags(team.get("interests")) or "пока не добавлены"))
    portfolio, history = st.tabs(["Работы и отзывы", "История XP"])
    with portfolio:
        _reviewed_work(team)
    with history:
        _xp_history(team)


def teams_page():
    page_header("СООБЩЕСТВО", "Команды и рейтинг", "Сравните навыки, выполненные задачи и отзывы — и выберите команду под свою задачу.")
    _flash()
    teams = leaderboard()
    if not teams:
        empty_state("Здесь появятся команды", "Команда попадает в список после первого предложения по задаче.")
        st.button("Открыть каталог", key="ratings_empty_catalog", type="primary", on_click=go_to, args=("Catalog",))
        return
    count, complete, checkpoints = st.columns(3)
    count.metric("Команд", len(teams))
    complete.metric("Проектов выполнено", sum(team["completed_tasks"] for team in teams))
    checkpoints.metric("Этапов подтверждено", sum(team["confirmed_milestones"] for team in teams))
    query = st.text_input("Поиск команды", key="team_search", placeholder="Название, навык или интерес").strip().casefold()
    matches = [(rank, team) for rank, team in enumerate(teams, start=1)
               if not query or query in " ".join((team["name"], team.get("about", ""), _tags(team.get("skills")), _tags(team.get("interests")))).casefold()]
    if not matches:
        empty_state("Команды не найдены", "Попробуйте другой навык или очистите строку поиска.")
        return
    st.caption("Рейтинг по заработанному XP. Рядом с оценкой указано число отзывов, чтобы было понятно, на каком опыте она основана.")
    st.dataframe([
        {"Место": rank, "Команда": team["name"], "XP": team["xp"],
         "Оценка": f"{team['average_rating']:.1f} / 5" if team["review_count"] else "Новая команда",
         "Отзывов": team["review_count"], "Выполнено задач": team["completed_tasks"],
         "Навыки": _tags(team.get("skills")) or "—"}
        for rank, team in matches
    ], hide_index=True, use_container_width=True)
    by_id = {team["id"]: team for _, team in matches}
    team_id = st.selectbox("Подробнее о команде", list(by_id), format_func=lambda value: by_id[value]["name"],
                           key="team_profile_select")
    with st.container(border=True, key=f"panel_profile_{team_id}"):
        _public_profile(by_id[team_id])
