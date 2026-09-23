"""Business decisions, expectation alignment and independently reviewed work."""

import streamlit as st

from services.ai import AIError
from services.briefs import check_expectations
from services.storage import load_records, review_proposal
from services.workflow import (get_engagement, confirm_milestone, request_revision,
                               accept_delivery, leave_review, team_stats)
from ui.components import page_header, empty_state, status_badge, status_label, go_to


GUIDED_COPY = {
    "Local checklist: missing fields and exact text matches only. Meaning and delivery scope still require joint review.":
        "Чек-лист проверяет пропущенные поля и точные совпадения текста. Содержание и объём работы обсудите с командой.",
    "The business has not specified an expected result.": "Вы ещё не указали ожидаемый результат.",
    "The business has not specified acceptance criteria.": "Вы ещё не указали критерии приёмки.",
    "The team has not specified its definition of done.": "Команда ещё не описала, что считает готовым результатом.",
    "The team has not specified an implementation plan.": "Команда ещё не описала план работы.",
    "What concrete result should the team deliver?": "Какой конкретный результат должна сдать команда?",
    "How will the business verify that the result meets its needs?": "Как вы проверите, что результат решает вашу задачу?",
    "What exactly will the team demonstrate when it considers this work complete?": "Что команда покажет, когда сочтёт работу завершённой?",
    "Which steps will connect the proposed work to the expected result?": "Какие шаги приведут от предложенного плана к ожидаемому результату?",
    "Does the team's definition of done cover every part of the business's expected result?": "Обещает ли команда всё, что вы ожидаете получить?",
    "Which demonstration or evidence will verify each success criterion?": "Какие материалы или демонстрация подтвердят каждый критерий успеха?",
    "Are any delivery details still interpreted differently by the two sides?": "Есть ли детали результата, которые вы и команда понимаете по-разному?",
    "Expected result repeats exactly in the team's proposal. Review that wording together.": "Формулировка ожидаемого результата точно повторяется в предложении. Проверьте, что вы одинаково её понимаете.",
    "Success criteria repeats exactly in the team's proposal. Review that wording together.": "Критерии успеха точно повторяются в предложении. Проверьте, что вы одинаково их понимаете.",
}


def action(function, *args, success_message=None, **kwargs):
    try:
        function(*args, **kwargs)
    except ValueError as error:
        st.error(str(error))
    else:
        if success_message:
            st.session_state.business_flash = success_message
        st.rerun()


def expectation_panel(task, proposal):
    st.markdown("**Одинаково ли вы понимаете результат?**")
    left, right = st.columns(2, gap="large")
    with left:
        st.caption("ВЫ ОЖИДАЕТЕ")
        st.write(task.get("expected_result") or "Ожидаемый результат пока не указан.")
        st.caption("Как вы проверите результат")
        st.write(task.get("success_criteria") or "Согласуйте критерии приёмки перед началом работы.")
    with right:
        st.caption("КОМАНДА ОБЕЩАЕТ")
        st.write(proposal.get("definition_of_done") or "В этом предложении ещё нет определения готовности.")
        st.caption("Идея решения")
        st.write(proposal.get("solution_idea") or "Идея пока не описана.")
    guided, ai = st.columns(2)
    mode = None
    if guided.button("Проверить по чек-листу", key=f"compare_{proposal['id']}",
                     help="Проверит пропущенные поля и совпадения текста. Работает без AI.",
                     use_container_width=True):
        mode = False
    if ai.button("Сравнить с AI", key=f"compare_ai_{proposal['id']}",
                 help="AI сопоставит обещанный результат с вашими ожиданиями и предложит вопросы команде.",
                 use_container_width=True):
        mode = True
    cache_key = f"expectations_{proposal['id']}"
    if mode is not None:
        try:
            with st.spinner("Сопоставляем ожидания и предложение…"):
                st.session_state[cache_key] = check_expectations(task, proposal, use_ai=mode)
        except (AIError, ValueError) as error:
            st.error(str(error))
    result = st.session_state.get(cache_key)
    if result:
        source = "Сравнение с AI" if result["source"] == "AI" else "Локальный чек-лист"
        def display_text(value):
            return GUIDED_COPY.get(value, value) if result["source"] == "Guided templates" else value
        with st.container(border=True, key=f"panel_expectations_{proposal['id']}"):
            st.caption(f"{source} · подсказка для обсуждения")
            st.write(display_text(result["summary"]))
            for label, key in (("В чём вы согласны", "agreements"),
                               ("Что стоит уточнить", "gaps"),
                               ("Вопросы команде", "questions")):
                if result[key]:
                    st.markdown(f"**{label}**")
                    for item in result[key]:
                        st.write("• " + display_text(item))


def work_review(proposal):
    work = get_engagement(proposal["id"])
    status_badge(work["status"])
    milestones = work.get("milestones", [])
    if milestones:
        confirmed_count = sum(stage["status"] == "Confirmed" for stage in milestones)
        st.markdown(f"**Промежуточные этапы · подтверждено {confirmed_count} из {len(milestones)}**")
    for stage in milestones:
        with st.expander(f"{stage['title']} · {status_label(stage['status'])}",
                         expanded=stage["status"] == "Submitted" and not work.get("review")):
            st.caption("Что команда сделала")
            st.write(stage["evidence"])
            if stage["status"] == "Submitted" and not work.get("review"):
                if st.button("Подтвердить этап · +10 XP", key=f"confirm_{stage['id']}",
                             help="Подтвердите, если представленные материалы показывают выполненную работу."):
                    action(confirm_milestone, proposal["id"], stage["id"],
                           success_message="Этап подтверждён. Команда получила +10 XP.")
            elif stage["status"] == "Submitted":
                st.caption("Этап не был подтверждён до итогового отзыва. XP за него не начислены.")
            else:
                st.caption("Работа подтверждена · +10 XP уже начислены.")
    if not milestones:
        st.caption("Команда может прислать до двух промежуточных этапов. За каждый подтверждённый этап она получит +10 XP.")
    delivery = work.get("delivery")
    if not delivery:
        st.info("Команда работает над задачей. Когда она сдаст итоговый результат, здесь появятся материалы для проверки.")
        return
    st.markdown("**Итоговый результат**")
    st.write(delivery["summary"])
    if delivery.get("url"):
        st.link_button("Открыть результат команды ↗", delivery["url"], use_container_width=True)
    if delivery.get("feedback"):
        st.info("Ваши замечания: " + delivery["feedback"])
    if delivery["status"] == "Submitted":
        st.caption("Проверьте материалы по согласованным критериям. Можно принять результат или попросить доработку.")
        if st.button("Принять готовый результат", key=f"delivery_accept_{proposal['id']}",
                     type="primary", use_container_width=True):
            action(accept_delivery, proposal["id"],
                   success_message="Результат принят. Теперь оцените работу команды и оставьте отзыв.")
        with st.expander("Нужна доработка?"):
            with st.form(f"revision_form_{proposal['id']}"):
                feedback = st.text_area("Что нужно исправить?", key=f"revision_{proposal['id']}",
                                        placeholder="Укажите, какой критерий пока не выполнен и что вы хотите увидеть в следующей версии.")
                if st.form_submit_button("Вернуть на доработку", use_container_width=True):
                    if not feedback.strip():
                        st.error("Опишите, что команде нужно исправить.")
                    else:
                        action(request_revision, proposal["id"], feedback,
                               success_message="Замечания сохранены. Команда увидит их в своём кабинете и сможет прислать новую версию.")
    elif delivery["status"] == "Revision requested":
        st.caption("Ожидаем новую версию от команды. Ваши замечания доступны в её кабинете.")
    review = work.get("review")
    if review:
        applied = review.get("xp_applied", review["xp_delta"])
        st.success(f"Отзыв опубликован · {review['rating']} из 5 ★ · изменение баланса: {applied:+d} XP")
        if applied != review["xp_delta"]:
            st.caption(f"За эту оценку предусмотрено {review['xp_delta']:+d} XP. Списание ограничено текущим балансом: он не может стать отрицательным.")
        st.write(review["comment"])
        if review.get("criterion_feedback"):
            st.caption("Замечание к согласованным критериям")
            st.write(review["criterion_feedback"])
        return
    if delivery["status"] == "Accepted":
        st.markdown("**Последний шаг — отзыв о работе**")
        st.caption("Отзыв появится в профиле команды и поможет другим заказчикам. Для одной команды по этой задаче можно оставить один итоговый отзыв.")
        with st.expander("Как оценка влияет на XP"):
            st.write("1 ★ → −20 XP · 2 ★ → −10 XP · 3 ★ → 0 XP · 4 ★ → +20 XP · 5 ★ → +40 XP")
            st.caption("Начисления за подтверждённые этапы остаются в истории. Итоговая оценка отдельно меняет баланс, который не опускается ниже нуля.")
        with st.form(f"review_form_{proposal['id']}"):
            rating = st.select_slider("Как вы оцениваете работу команды?", options=[1, 2, 3, 4, 5],
                                      value=3, key=f"rating_{proposal['id']}",
                                      help="1 — результат сильно не соответствует ожиданиям; 5 — отличная работа.")
            comment = st.text_area("Ваш отзыв", key=f"review_comment_{proposal['id']}",
                                   placeholder="Что получилось хорошо? Что команда могла бы сделать лучше?")
            reason = st.text_area("Какой согласованный критерий не выполнен?", key=f"review_reason_{proposal['id']}",
                                  placeholder="Обязательно для оценки 1–2. Например: уведомления приходят только раз в день вместо согласованного времени.",
                                  help="Для оценки 3–5 это поле можно оставить пустым.")
            confirmed = st.checkbox("Я проверил результат и подтверждаю итоговую оценку.", key=f"review_confirm_{proposal['id']}")
            if st.form_submit_button("Опубликовать отзыв", type="primary", use_container_width=True):
                if not confirmed:
                    st.error("Подтвердите итоговую оценку перед публикацией.")
                elif not comment.strip():
                    st.error("Добавьте отзыв о работе команды.")
                elif rating <= 2 and not reason.strip():
                    st.error("Для оценки 1–2 укажите, какой согласованный критерий команда не выполнила.")
                else:
                    action(leave_review, proposal["id"], rating, comment, criterion_feedback=reason,
                           success_message="Отзыв опубликован. Рейтинг и история XP команды обновлены.")


def _next_step(proposal, work):
    if proposal["status"] == "Pending":
        return "Сравните ожидания и план. Если предложение подходит, пригласите команду к работе."
    if proposal["status"] == "Rejected":
        return "Предложение отклонено. Вы можете пересмотреть решение и пригласить команду."
    if work.get("review"):
        return "Работа завершена, отзыв опубликован. Результат и оценка доступны в профиле команды."
    delivery = work.get("delivery") or {}
    if delivery.get("status") == "Submitted":
        return "Команда сдала результат. Проверьте его и примите работу или оставьте замечания."
    if delivery.get("status") == "Accepted":
        return "Вы приняли результат. Осталось оставить итоговую оценку и отзыв."
    if delivery.get("status") == "Revision requested":
        return "Ожидаем доработку. Команда видит замечания и сможет прислать новую версию."
    if any(stage["status"] == "Submitted" for stage in work.get("milestones", [])):
        return "Есть этапы на проверке. Подтвердите выполненную работу, чтобы начислить команде XP."
    return "Команда приглашена. Промежуточные этапы и итоговый результат появятся здесь после отправки."


def dashboard():
    page_header("КАБИНЕТ БИЗНЕСА", "От предложения к результату",
                "Сравнивайте команды, приглашайте подходящие и оценивайте выполненную работу. По одной задаче могут работать несколько команд.")
    message = st.session_state.pop("business_flash", None)
    if message:
        st.success(message)
    tasks = load_records("tasks")
    proposals = load_records("proposals")
    task_count, pending_count, accepted_count = st.columns(3)
    task_count.metric("Опубликовано задач", len(tasks))
    pending_count.metric("Ждут вашего решения", sum(p["status"] == "Pending" for p in proposals))
    accepted_count.metric("Принято предложений", sum(p["status"] == "Accepted" for p in proposals))
    if not tasks:
        empty_state("Начните с первой задачи", "Опишите вашу задачу и опубликуйте её. Здесь появятся предложения студенческих команд.")
        st.button("Создать задачу", key="business_create_task", type="primary", on_click=go_to, args=("Create Task",))
        return
    if not proposals:
        empty_state("Пока нет предложений", "Ваши задачи уже в каталоге. После отклика команды вы сможете сравнить её план с ожиданиями и пригласить её к работе.")
        st.button("Посмотреть задачи в каталоге", key="business_open_catalog", on_click=go_to, args=("Catalog",))
        return
    st.subheader("Предложения по вашим задачам")
    search_column, status_column = st.columns([2, 1])
    query = search_column.text_input("Найти задачу", key="dashboard_search", placeholder="Название задачи")
    status = status_column.selectbox("Решение по предложению", ["All", "Pending", "Accepted", "Rejected"],
                                     key="dashboard_status", format_func=lambda value: "Все предложения" if value == "All" else status_label(value))
    stats = {t["id"]: team_stats(t["id"]) for t in load_records("teams")}
    visible = 0
    shown_work = set()
    for task in tasks:
        if query.casefold() not in task["title"].casefold():
            continue
        matches = [p for p in proposals if p["task_id"] == task["id"] and (status == "All" or p["status"] == status)]
        if not matches:
            continue
        visible += len(matches)
        st.subheader(task["title"])
        st.caption(f"Предложений: {len(matches)} · решение по каждой команде принимается отдельно")
        if len(matches) > 1:
            with st.expander("Сравнить команды в таблице", expanded=True):
                rows = []
                for proposal in matches:
                    profile = stats.get(proposal.get("team_id"), {})
                    avg = profile.get("average_rating")
                    rows.append({"Команда": proposal["team_name"],
                                 "Обещанный результат": proposal.get("definition_of_done") or "Не указан",
                                 "Срок": proposal.get("estimated_time", ""), "XP": profile.get("xp", 0),
                                 "Оценка": f"{avg:.1f} из 5" if avg is not None else "Пока нет",
                                 "Отзывов": profile.get("review_count", 0),
                                 "Решение": status_label(proposal["status"])})
                st.dataframe(rows, hide_index=True, use_container_width=True)
        for proposal in matches:
            with st.container(border=True, key=f"panel_proposal_{proposal['id']}"):
                profile = stats.get(proposal.get("team_id"), {})
                title_column, badge_column = st.columns([3, 1])
                title_column.subheader(proposal["team_name"])
                with badge_column:
                    status_badge(proposal["status"])
                avg = profile.get("average_rating")
                reputation = f"{avg:.1f} из 5 ★ · отзывов: {profile.get('review_count', 0)}" if avg is not None else "Новая команда · пока без отзывов"
                st.caption(f"{profile.get('xp', 0)} XP · завершено задач: {profile.get('completed_tasks', 0)} · {reputation}")
                work = get_engagement(proposal["id"])
                st.info(_next_step(proposal, work))
                with st.expander("Ожидания и предложение команды", expanded=proposal["status"] == "Pending"):
                    expectation_panel(task, proposal)
                with st.expander("План, сроки и прототип"):
                    st.markdown("**План работы**")
                    st.write(proposal.get("plan") or "Пока не указан.")
                    st.markdown("**Предполагаемый срок**")
                    st.write(proposal.get("estimated_time") or "Пока не указан.")
                    st.markdown("**Прототип**")
                    st.write(proposal.get("prototype_url") or "Команда ещё не добавила ссылку.")
                work_started = bool(work.get("milestones") or work.get("delivery") or work.get("review"))
                accept, reject = st.columns(2)
                if accept.button("Команда приглашена" if proposal["status"] == "Accepted" else "Пригласить команду",
                                 key=f"accept_{proposal['id']}", disabled=proposal["status"] == "Accepted",
                                 type="primary" if proposal["status"] == "Pending" else "secondary",
                                 use_container_width=True):
                    action(review_proposal, proposal["id"], "Accepted",
                           success_message="Команда приглашена к работе. Она может отправлять этапы и результат из своего кабинета.")
                if reject.button("Отклонить предложение", key=f"reject_{proposal['id']}",
                                 disabled=proposal["status"] == "Rejected" or (work_started and proposal["status"] == "Accepted"),
                                 use_container_width=True,
                                 help="Когда работа началась, проверяйте результат и запрашивайте доработку в разделе ниже."):
                    action(review_proposal, proposal["id"], "Rejected", success_message="Предложение отклонено. Остальные команды по задаче остаются без изменений.")
                if proposal["status"] == "Accepted":
                    pair = (proposal["team_id"], task["id"])
                    if pair in shown_work:
                        st.caption("История работы этой команды общая для всех её предложений по задаче. Она показана у первого приглашённого предложения выше.")
                    else:
                        shown_work.add(pair)
                        with st.container():
                            st.markdown("**Работа команды: этапы, результат и отзыв**")
                            work_review(proposal)
    if not visible:
        empty_state("Подходящих предложений нет", "Попробуйте другое название задачи или выберите «Все предложения» в фильтре.")
