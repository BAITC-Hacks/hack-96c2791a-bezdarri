"""Russian display copy for fixed local suggestions; AI/user text is untouched."""


_FIELDS = ("title", "outcome", "user_action", "acceptance_hint")

_DIRECTIONS = {
    (
        "Understand feedback",
        "A possible option is a dashboard of feedback themes.",
        "A business representative could inspect themes and decide what to improve.",
        "Which themes should be visible, and how would you verify them against the supplied feedback?",
    ): (
        "Понять отзывы",
        "Возможный вариант — панель, которая показывает темы и проблемы из отзывов.",
        "Представитель бизнеса мог бы изучать повторяющиеся темы и выбирать, что улучшить.",
        "Какие темы важно видеть и как вы проверите, что они соответствуют исходным отзывам?",
    ),
    (
        "Prepare a response",
        "A possible option is an assistant that drafts replies to feedback.",
        "A designated person could review and approve a suggested reply.",
        "Which replies would you accept, and who must approve them before sending?",
    ): (
        "Подготовить ответ",
        "Возможный вариант — помощник, который готовит ответы на отзывы.",
        "Ответственный сотрудник мог бы проверять и одобрять предложенный ответ.",
        "Какие ответы вы готовы принять и кто должен проверять их перед отправкой?",
    ),
    (
        "Notice urgent issues",
        "A possible option is a notification workflow for urgent feedback.",
        "A designated person could receive a flagged item and decide what action to take.",
        "What counts as urgent, who receives the alert, and when should it arrive?",
    ): (
        "Замечать срочные жалобы",
        "Возможный вариант — уведомления об отзывах, на которые нужно быстро отреагировать.",
        "Ответственный сотрудник мог бы получать важные обращения и решать, что делать дальше.",
        "Какие обращения считать срочными, кому отправлять уведомление и как быстро оно должно приходить?",
    ),
    (
        "Understand the problem",
        "A possible option is an evidence-based diagnostic report.",
        "A business representative could use findings to choose the next action.",
        "What business question must the report answer, and what evidence could verify it?",
    ): (
        "Разобраться в проблеме",
        "Возможный вариант — аналитический отчёт с выводами, подкреплёнными данными.",
        "Представитель бизнеса мог бы использовать выводы, чтобы выбрать следующий шаг.",
        "На какой вопрос бизнеса должен ответить отчёт и какими данными можно проверить выводы?",
    ),
    (
        "Try a prototype",
        "A possible option is a small interactive prototype of the intended workflow.",
        "An intended user could try a concrete scenario and assess its usefulness.",
        "Which user scenario should the prototype demonstrate, and what would count as success?",
    ): (
        "Попробовать прототип",
        "Возможный вариант — небольшой интерактивный прототип будущего решения.",
        "Будущий пользователь мог бы пройти конкретный сценарий и оценить, помогает ли решение.",
        "Какой сценарий должен показать прототип и по каким признакам вы поймёте, что он полезен?",
    ),
    (
        "Improve the workflow",
        "A possible option is an assisted workflow for a recurring business task.",
        "A designated person could review a suggested action and decide whether to apply it.",
        "Which recurring step should change, and how would you check that the new process helps?",
    ): (
        "Улучшить рабочий процесс",
        "Возможный вариант — помощник для выполнения повторяющейся рабочей задачи.",
        "Ответственный сотрудник мог бы проверять предложенное действие и решать, применять ли его.",
        "Какой повторяющийся шаг нужно изменить и как вы проверите, что новый процесс помогает?",
    ),
}


def direction_options(result):
    """Translate only known local templates without altering the service result."""
    options = result.get("interpretations", [])
    if result.get("source") != "Guided templates":
        return options
    translated = []
    for option in options:
        values = tuple(option.get(field) for field in _FIELDS)
        replacement = _DIRECTIONS.get(values) if all(isinstance(value, str) for value in values) else None
        translated.append({**option, **dict(zip(_FIELDS, replacement))} if replacement else option)
    return translated
