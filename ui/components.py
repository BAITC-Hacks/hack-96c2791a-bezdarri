"""Shared presentation helpers; domain values stay independent of UI labels."""

from html import escape
from pathlib import Path

import streamlit as st


PAGES = {
    "Overview": "Обзор",
    "Create Task": "Создать задачу",
    "Catalog": "Каталог задач",
    "Business Dashboard": "Кабинет бизнеса",
    "Team Workspace": "Кабинет команды",
    "Teams & Ratings": "Команды и рейтинг",
}

STATUS_LABELS = {
    "All": "Все", "Pending": "Ждёт решения", "Accepted": "Принято",
    "Rejected": "Отклонено", "Submitted": "На проверке", "Confirmed": "Подтверждено",
    "In progress": "В работе", "Delivery submitted": "Результат на проверке",
    "Revision requested": "Нужны доработки", "Completed": "Завершено",
    "Draft": "Черновик", "Working": "Нужны уточнения", "Ready": "Можно начинать",
    "Priority": "Подробная задача",
}

FIELD_LABELS = {
    "title": "Название задачи", "context": "Что происходит сейчас", "need": "Какую проблему решаем",
    "users": "Кому нужен результат", "data_materials": "Данные и материалы",
    "constraints": "Сроки и ограничения", "expected_result": "Что нужно получить",
    "success_criteria": "Как проверим результат", "contact": "Контакт и формат общения",
}


def inject_styles():
    st.markdown("<style>" + Path(__file__).with_name("styles.css").read_text(encoding="utf-8") + "</style>",
                unsafe_allow_html=True)


def go_to(page):
    st.session_state.page = page


def status_label(status):
    return STATUS_LABELS.get(status, status)


def status_badge(status):
    tone = ("success" if status in {"Accepted", "Confirmed", "Completed", "Ready", "Priority"}
            else "warning" if status in {"Pending", "Submitted", "Delivery submitted", "Revision requested", "Working"}
            else "neutral")
    st.markdown(f'<span class="tf-tag tf-tag-{tone}">{escape(status_label(status))}</span>', unsafe_allow_html=True)


def page_header(eyebrow, title, description):
    st.markdown(f'<div class="tf-page-heading"><div class="tf-eyebrow">{escape(eyebrow)}</div>'
                f'<h1>{escape(title)}</h1><p>{escape(description)}</p></div>', unsafe_allow_html=True)


def empty_state(title, description):
    st.markdown(f'<div class="tf-empty"><div class="tf-empty-mark" aria-hidden="true">＋</div>'
                f'<h3>{escape(title)}</h3><p>{escape(description)}</p></div>', unsafe_allow_html=True)


def section_heading(number, title, description=""):
    st.markdown(f'<div class="tf-section-heading"><span class="tf-step-number">{escape(str(number))}</span>'
                f'<div><h3>{escape(title)}</h3><p>{escape(description)}</p></div></div>', unsafe_allow_html=True)
