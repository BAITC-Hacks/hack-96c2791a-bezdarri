"""A read-only introduction and clear entry points for the shared demo."""

import streamlit as st

from services.storage import load_records
from ui.components import go_to, page_header


def _open_demo():
    """The task editor decides whether it is safe to fill an empty draft."""
    st.session_state.demo_requested = True
    go_to("Create Task")


def _workspace_metrics():
    tasks = load_records("tasks")
    teams = load_records("teams")
    proposals = load_records("proposals")
    engagements = load_records("engagements")
    accepted = {(row["team_id"], row["task_id"]) for row in proposals
                if row.get("status") == "Accepted"}
    completed = {(row["team_id"], row["task_id"]) for row in engagements
                 if (row.get("delivery") or {}).get("status") == "Accepted"}
    st.subheader("В рабочем пространстве")
    st.caption("Текущие задачи, команды и результаты.")
    task_count, team_count, active_count, completed_count = st.columns(4)
    task_count.metric("Задач опубликовано", len(tasks))
    team_count.metric("Студенческих команд", len(teams))
    active_count.metric("Проектов в работе", len(accepted - completed))
    completed_count.metric("Результатов принято", len(completed))


def overview():
    page_header(
        "БИЗНЕС × СТУДЕНЧЕСКИЕ КОМАНДЫ",
        "От задачи — к общему результату",
        "Сформулируйте, что нужно бизнесу. Найдите команду, договоритесь о результате "
        "и превратите выполненную работу в подтверждённый опыт.",
    )

    business, students = st.columns(2, gap="large")
    with business, st.container(border=True, key="panel_overview_business"):
        st.markdown('<div class="tf-eyebrow">ДЛЯ БИЗНЕСА</div>', unsafe_allow_html=True)
        st.subheader("У меня есть задача")
        st.write("Опишите проблему своими словами. Уточните результат, сравните предложения "
                 "и выберите одну или несколько команд.")
        st.button("Создать задачу", key="overview_create", type="primary",
                  use_container_width=True, on_click=go_to, args=("Create Task",))
        st.button("Открыть кабинет бизнеса", key="overview_business",
                  use_container_width=True, on_click=go_to, args=("Business Dashboard",))
    with students, st.container(border=True, key="panel_overview_students"):
        st.markdown('<div class="tf-eyebrow">ДЛЯ СТУДЕНТОВ</div>', unsafe_allow_html=True)
        st.subheader("Хочу решить задачу")
        st.write("Выберите интересный проект, предложите решение и покажите результат. "
                 "Подтверждённая работа пополнит портфолио.")
        st.button("Найти задачу в каталоге", key="overview_catalog", type="primary",
                  use_container_width=True, on_click=go_to, args=("Catalog",))
        st.button("Открыть кабинет команды", key="overview_team",
                  use_container_width=True, on_click=go_to, args=("Team Workspace",))

    with st.container(border=True, key="panel_overview_demo"):
        description, action = st.columns([3, 1.4], vertical_alignment="center")
        with description:
            st.markdown("**Первый раз в TaskForge? Начните с примера.**")
            st.caption("Разберите задачу об отзывах клиентов, выберите нужный результат "
                       "и посмотрите, как устроена карточка. Ваш текущий черновик сохранится.")
        with action:
            st.button("Попробовать на примере", key="overview_demo",
                      use_container_width=True, on_click=_open_demo)

    st.subheader("Как задача становится результатом")
    steps = (
        ("01 · УТОЧНИТЬ", "Выбрать направление",
         "«Развилка» показывает три возможных решения. Бизнес выбирает, какое ему нужно."),
        ("02 · ДОГОВОРИТЬСЯ", "Сравнить ожидания",
         "Команды объясняют, что считают готовым результатом. Бизнес выбирает исполнителей."),
        ("03 · СДЕЛАТЬ", "Показать работу",
         "Команда делится прогрессом и сдаёт результат. Бизнес принимает его или просит доработки."),
        ("04 · ПОДТВЕРДИТЬ", "Получить отзыв",
         "Оценка бизнеса влияет на XP. Проект и отзыв появляются в профиле команды."),
    )
    for column, (number, title, description) in zip(st.columns(4), steps):
        with column, st.container(border=True, key=f"panel_overview_step_{number[:2]}"):
            st.markdown(f'<div class="tf-eyebrow">{number}</div>', unsafe_allow_html=True)
            st.markdown(f"**{title}**")
            st.caption(description)

    _workspace_metrics()

    task_score, team_score = st.columns(2, gap="large")
    with task_score, st.container(border=True, key="panel_overview_task_score"):
        st.markdown("**Готовность задачи · 0–100**")
        st.write("Помогает увидеть, что уже понятно и что стоит уточнить перед стартом. "
                 "Ручной чек-лист показывает заполненность, AI-оценка — качество описания по рубрике.")
        st.caption("Задачи с низким баллом тоже доступны в каталоге.")
    with team_score, st.container(border=True, key="panel_overview_team_score"):
        st.markdown("**Репутация команды · XP и отзывы**")
        st.write("Складывается из подтверждённых этапов и оценок бизнеса. "
                 "Рядом с XP видны выполненные проекты и число отзывов.")
        st.button("Посмотреть команды и рейтинг", key="overview_ratings",
                  use_container_width=True, on_click=go_to, args=("Teams & Ratings",))

    with st.expander("Демонстрация за 5 минут: от первого описания до отзыва"):
        st.write("1. Откройте пример. В «Развилке» выберите вариант решения и заполните карточку.")
        st.write("2. Подтвердите задачу и опубликуйте. В каталоге отправьте предложения двух команд.")
        st.write("3. В кабинете бизнеса сравните ожидания и примите обе команды — решения независимы.")
        st.write("4. От одной команды отправьте этап и результат. Бизнес подтверждает этап, "
                 "может запросить доработку и затем принимает результат.")
        st.write("5. Оставьте оценку 5 ★ и отзыв. Команда получит 50 XP: "
                 "+10 за подтверждённый этап и +40 за отзыв.")
        st.caption("Сценарий можно пройти с локальными подсказками без AI. "
                   "Команды и бизнес выбираются в одном демонстрационном пространстве.")
