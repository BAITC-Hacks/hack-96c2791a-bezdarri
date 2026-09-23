"""Run with: python -m streamlit run app.py"""

from urllib.parse import urlparse
from html import escape
import logging

import streamlit as st

from services.ai import AIError, TASK_KEYS, analyze_task
from services.scoring import FIELDS, task_readiness
from services.storage import add_record, load_records, review_proposal, submit_proposal

st.set_page_config(page_title="TaskForge", page_icon=":material/architecture:", layout="wide")

# Presentation only: all user-supplied text in HTML cards is escaped below.
st.markdown("""
<style>
    .block-container { max-width: 1200px; padding-top: 2.2rem; padding-bottom: 3rem; }
    h1, h2, h3 { letter-spacing: -0.035em; overflow-wrap: anywhere; }
    h2 { font-size: 1.65rem; } h3 { font-size: 1.25rem; }
    [data-testid="stCaptionContainer"] { color: #a3aec2; }
    [data-testid="stSidebar"] { border-right: 1px solid #253044; }
    [data-testid="stSidebar"] [role="radiogroup"] { gap: 0.4rem; }
    [data-testid="stSidebar"] [role="radiogroup"] label {
        padding: 0.65rem 0.8rem; border: 1px solid transparent; border-radius: 10px;
    }
    [data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {
        background: #202c47; border-color: #3c4f76;
    }
    [data-testid="stButton"] button, [data-testid="stFormSubmitButton"] button {
        border-radius: 10px; padding: 0.6rem 1.15rem; font-weight: 600;
    }
    [data-testid="stTextInput"] input, [data-testid="stTextArea"] textarea {
        font-size: 0.95rem; line-height: 1.65;
    }
    [data-testid="stMetric"] { background: #141e30; border: 1px solid #2b3b56;
        border-radius: 14px; padding: 1rem 1.25rem; }
    [data-testid="stMetricLabel"] { color: #acb9d0; }
    [data-testid="stMetricValue"] { font-size: clamp(2.2rem, 4vw, 3.7rem);
        font-weight: 700; letter-spacing: -0.05em; font-variant-numeric: tabular-nums; }
    [data-testid="stMetricDelta"] { font-size: 1.05rem; font-weight: 600; }
    [data-testid="stForm"], [data-testid="stVerticalBlockBorderWrapper"] { border-radius: 16px; }
    [data-testid="stExpander"] details { border-color: #2b3850; border-radius: 12px; }
    [data-testid="stExpander"] summary { font-size: 0.85rem; color: #b6c8fa; }
    [data-testid="stTable"] { overflow-x: auto; border: 1px solid #2b3850; border-radius: 12px; }
    [data-testid="stTable"] th { background: #172237; color: #c8d4e9; font-size: 0.8rem; }
    [data-testid="stTable"] td { font-size: 0.88rem; line-height: 1.6; }
    .tf-topbar { display: flex; justify-content: space-between; align-items: center;
        flex-wrap: wrap; gap: 0.7rem; padding-bottom: 1.3rem; border-bottom: 1px solid #253044; }
    .tf-brand { font-size: 1.15rem; font-weight: 800; letter-spacing: 0.12em; color: #f3f6fc; }
    .tf-tagline { color: #a3aec2; font-size: 0.82rem; }
    .tf-hero { padding: 1.7rem 0 1.2rem; }
    .tf-eyebrow { color: #a5bcff; text-transform: uppercase; font-size: 0.7rem;
        font-weight: 700; letter-spacing: 0.16em; margin: 0 0 0.8rem; }
    .tf-hero h1 { font-size: clamp(2.2rem, 4.1vw, 3.6rem); font-weight: 700;
        line-height: 1.12; margin: 0; padding: 0; max-width: 900px; }
    .tf-accent { color: #a5bcff; }
    .tf-hero p { color: #acb7ca; font-size: 1rem; line-height: 1.7;
        max-width: 670px; margin: 1rem 0 0; }
    .tf-flow { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr));
        border: 1px solid #2b3850; border-radius: 14px; background: #111b2c; margin-bottom: 1.1rem; }
    .tf-step { padding: 1rem; border-right: 1px solid #2b3850; }
    .tf-step:last-child { border-right: 0; }
    .tf-step b { color: #a5bcff; font-size: 0.78rem; display: block; margin-bottom: 0.35rem; }
    .tf-step span { font-size: 0.75rem; font-weight: 650; letter-spacing: 0.08em; }
    .tf-section { margin-top: 1.1rem; padding-top: 1.2rem; border-top: 1px solid #253044; }
    .tf-question, .tf-improvement { display: flex; gap: 0.9rem; align-items: baseline; }
    .tf-question { margin: 0.5rem 0; color: #a3aec2; font-size: 0.75rem; letter-spacing: 0.08em; }
    .tf-number { color: #a5bcff; font-size: 0.8rem; font-weight: 700; font-variant-numeric: tabular-nums; }
    .tf-improvement { padding: 0.85rem 0; border-bottom: 1px solid #253044; line-height: 1.65; }
    .tf-card-header { display: flex; justify-content: space-between; gap: 1rem;
        align-items: center; flex-wrap: wrap; margin-bottom: 0.9rem; }
    .tf-card-title { margin: 0 0 0.65rem; padding: 0; font-size: 1.45rem; line-height: 1.35; }
    .tf-badge { display: inline-block; padding: 0.25rem 0.65rem; border-radius: 6px;
        background: #202c40; color: #b7c4da; font-size: 0.75rem; }
    .tf-level { padding: 0.25rem 0.6rem; border: 1px solid; border-radius: 6px;
        font-size: 0.7rem; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; }
    .tf-score strong { font-size: 2rem; letter-spacing: -0.05em; }
    .tf-score small { font-size: 0.8rem; color: #a3aec2; }
    .tf-draft { border-color: #536078; color: #bdc7d8; }
    .tf-working { border-color: #796339; color: #ebca83; }
    .tf-ready { border-color: #39725f; color: #94d5b8; }
    .tf-priority { border-color: #536db3; color: #abc0ff; }
    .tf-legend { margin-top: 2rem; padding-top: 1.2rem; border-top: 1px solid #2b3850; }
    .tf-legend div { display: flex; justify-content: space-between; padding: 0.4rem 0;
        font-size: 0.7rem; letter-spacing: 0.06em; color: #9eacc3; }
    @media (max-width: 640px) {
        .tf-flow { grid-template-columns: repeat(2, minmax(0, 1fr)); }
        .tf-step { border: 0; } .tf-hero { padding-top: 1rem; }
    }
</style>
""", unsafe_allow_html=True)

# Temporary local diagnostics: state transitions only, never prompts or credentials.
logger = logging.getLogger("taskforge.ui")
logger.setLevel(logging.INFO)
if not logger.handlers:
    logger.addHandler(logging.StreamHandler())
logger.propagate = False


# Static interface translations only; task content and AI responses keep their language.
TRANSLATIONS = {
    "Language": {"ru": "Язык", "kk": "Тіл"},
    "Task readiness": {"ru": "Готовность задачи", "kk": "Тапсырманың дайындығы"},
    "Readiness score": {"ru": "Оценка готовности", "kk": "Дайындық бағасы"},
    "Readiness improvement": {"ru": "Рост готовности", "kk": "Дайындық өсімі"},
    "Last assessed improvement": {"ru": "Рост по последней оценке", "kk": "Соңғы бағалаудағы өсім"},
    "{points:+d} points": {"ru": "{points:+d} балл.", "kk": "{points:+d} ұпай"},
    "Readiness breakdown": {"ru": "Оценка по категориям", "kk": "Санаттар бойынша баға"},
    "See what is clear, what is missing, and where your brief can improve.": {"ru": "Посмотрите, что уже понятно, каких сведений не хватает и как улучшить описание задачи.", "kk": "Не анық екенін, қандай ақпарат жетіспейтінін және тапсырма сипаттамасын қалай жақсартуға болатынын көріңіз."},
    "Missing information: ": {"ru": "Не хватает информации: ", "kk": "Жетіспейтін ақпарат: "},
    "How to improve": {"ru": "Как улучшить", "kk": "Қалай жақсартуға болады"},
    "Suggestions for increasing the score": {"ru": "Рекомендации для повышения оценки", "kk": "Бағаны арттыруға арналған ұсыныстар"},
    "All readiness fields are filled in. Review the detail with the business contact.": {"ru": "Все поля готовности заполнены. Уточните детали с представителем бизнеса.", "kk": "Дайындыққа қатысты барлық өріс толтырылды. Мәліметтерді бизнес өкілімен нақтылаңыз."},
    "Enter a business problem first.": {"ru": "Сначала опишите проблему бизнеса.", "kk": "Алдымен бизнес мәселесін сипаттаңыз."},
    "Answer at least one clarification question first.": {"ru": "Сначала ответьте хотя бы на один уточняющий вопрос.", "kk": "Алдымен кемінде бір нақтылау сұрағына жауап беріңіз."},
    "Analyzing the business brief…": {"ru": "Анализируем описание задачи…", "kk": "Тапсырма сипаттамасы талданып жатыр…"},
    "Create Task": {"ru": "Создать задачу", "kk": "Тапсырма жасау"},
    "Turn business problems": {"ru": "Превратите проблемы бизнеса", "kk": "Бизнес мәселелерін"},
    "into student-ready challenges.": {"ru": "в понятные задачи для студентов.", "kk": "студенттерге түсінікті тапсырмаларға айналдырыңыз."},
    "AI identifies missing information, asks targeted questions, and helps businesses create actionable challenges.": {"ru": "ИИ находит пробелы в описании, задаёт точные вопросы и помогает бизнесу подготовить задачи, которые можно взять в работу.", "kk": "ЖИ жетіспейтін ақпаратты анықтап, нақты сұрақтар қояды және бизнеске орындауға болатын тапсырмалар дайындауға көмектеседі."},
    "DESCRIBE": {"ru": "ОПИШИТЕ", "kk": "СИПАТТАҢЫЗ"},
    "CLARIFY": {"ru": "УТОЧНИТЕ", "kk": "НАҚТЫЛАҢЫЗ"},
    "IMPROVE": {"ru": "УЛУЧШИТЕ", "kk": "ЖАҚСАРТЫҢЫЗ"},
    "PUBLISH": {"ru": "ОПУБЛИКУЙТЕ", "kk": "ЖАРИЯЛАҢЫЗ"},
    "Quick AI Draft": {"ru": "Быстрый черновик с ИИ", "kk": "ЖИ көмегімен жылдам жоба"},
    "Describe the problem in your own words. AI uses only supplied facts; unknowns stay blank. Review every field before publishing.": {"ru": "Опишите проблему своими словами. ИИ использует только ваши факты и оставляет неизвестное незаполненным. Проверьте все поля перед публикацией.", "kk": "Мәселені өз сөзіңізбен сипаттаңыз. ЖИ тек сіз берген деректерді пайдаланады, белгісіз мәліметтер бос қалады. Жариялау алдында барлық өрісті тексеріңіз."},
    "Business problem": {"ru": "Проблема бизнеса", "kk": "Бизнес мәселесі"},
    "We run an online clothing store and many customers abandon their carts…": {"ru": "У нас интернет-магазин одежды, и многие покупатели бросают корзину, не завершив покупку…", "kk": "Біздің онлайн киім дүкенімізде көптеген сатып алушы себеттегі тауарларды сатып алмай кетеді…"},
    "Analyze with AI": {"ru": "Проанализировать с ИИ", "kk": "ЖИ көмегімен талдау"},
    "02 / Guided interview": {"ru": "02 / Уточняющие вопросы", "kk": "02 / Нақтылау сұрақтары"},
    "Clarification questions": {"ru": "Уточняющие вопросы", "kk": "Нақтылау сұрақтары"},
    "Add the details you know. Your answers help turn the problem into an actionable brief.": {"ru": "Добавьте известные вам детали. Ответы помогут превратить проблему в конкретную задачу.", "kk": "Өзіңіз білетін мәліметтерді қосыңыз. Жауаптарыңыз мәселені нақты тапсырмаға айналдыруға көмектеседі."},
    "CLARIFICATION": {"ru": "УТОЧНЕНИЕ", "kk": "НАҚТЫЛАУ"},
    "Update task with answers": {"ru": "Обновить задачу с учётом ответов", "kk": "Жауаптарды ескеріп тапсырманы жаңарту"},
    "03 / Refine the brief": {"ru": "03 / Доработайте описание", "kk": "03 / Сипаттаманы толықтырыңыз"},
    "Editable task card": {"ru": "Редактируемая карточка задачи", "kk": "Өңдеуге болатын тапсырма карточкасы"},
    "Review the business facts, refine the details, and reanalyze after making changes.": {"ru": "Проверьте факты, уточните детали и запустите анализ повторно после изменений.", "kk": "Деректерді тексеріңіз, мәліметтерді нақтылаңыз және өзгерткеннен кейін талдауды қайта іске қосыңыз."},
    "Title": {"ru": "Название", "kk": "Атауы"},
    "Context": {"ru": "Контекст", "kk": "Жағдай сипаттамасы"},
    "Need": {"ru": "Потребность", "kk": "Қажеттілік"},
    "Users": {"ru": "Пользователи", "kk": "Пайдаланушылар"},
    "Data/materials": {"ru": "Данные и материалы", "kk": "Деректер мен материалдар"},
    "Constraints": {"ru": "Ограничения", "kk": "Шектеулер"},
    "Expected result": {"ru": "Ожидаемый результат", "kk": "Күтілетін нәтиже"},
    "Success criteria": {"ru": "Критерии успеха", "kk": "Табыс өлшемдері"},
    "Contact/interaction format": {"ru": "Контакт и формат взаимодействия", "kk": "Байланыс және өзара әрекеттесу форматы"},
    "Business contact": {"ru": "Контакт представителя бизнеса", "kk": "Бизнес өкілінің байланыс деректері"},
    "Context and need": {"ru": "Контекст и потребность", "kk": "Жағдай мен қажеттілік"},
    "Data and materials": {"ru": "Данные и материалы", "kk": "Деректер мен материалдар"},
    "Business contact and interaction format": {"ru": "Контакт представителя бизнеса и формат взаимодействия", "kk": "Бизнес өкілінің байланыс деректері және өзара әрекеттесу форматы"},
    "Industry (optional)": {"ru": "Отрасль (необязательно)", "kk": "Сала (міндетті емес)"},
    "e.g. Retail, Education, Healthcare": {"ru": "Например: торговля, образование, здравоохранение", "kk": "Мысалы: сауда, білім беру, денсаулық сақтау"},
    "Used only to organize the catalog. Blank industries appear as Other.": {"ru": "Используется только для фильтрации каталога. Если отрасль не указана, отображается «Другое».", "kk": "Тек каталогты реттеу үшін қолданылады. Сала көрсетілмесе, «Басқа» деп көрсетіледі."},
    "Reanalyze edited card": {"ru": "Повторно проанализировать карточку", "kk": "Өңделген карточканы қайта талдау"},
    "The card has changed. The assessment below is for the previous version. Reanalyze the edited card before publishing.": {"ru": "Карточка изменена. Оценка ниже относится к предыдущей версии. Повторно проанализируйте карточку перед публикацией.", "kk": "Карточка өзгертілді. Төмендегі баға алдыңғы нұсқаға қатысты. Жариялау алдында өңделген карточканы қайта талдаңыз."},
    "I reviewed the task card and confirm its business facts.": {"ru": "Я проверил(а) карточку задачи и подтверждаю указанные факты.", "kk": "Тапсырма карточкасын тексердім және ондағы деректерді растаймын."},
    "You can also create a task manually. Until AI analysis succeeds, this is a completion checklist, not a quality score.": {"ru": "Задачу можно создать и вручную. До успешного анализа ИИ оценка показывает заполненность полей, а не качество описания.", "kk": "Тапсырманы қолмен де жасауға болады. ЖИ талдауы сәтті аяқталғанға дейін баға сипаттама сапасын емес, өрістердің толтырылуын көрсетеді."},
    "04 / Share your challenge": {"ru": "04 / Опубликуйте задачу", "kk": "04 / Тапсырманы жариялаңыз"},
    "Publish task": {"ru": "Опубликовать задачу", "kk": "Тапсырманы жариялау"},
    "Enter a title before publishing.": {"ru": "Укажите название перед публикацией.", "kk": "Жариялау алдында атауын енгізіңіз."},
    "Task published. Open Catalog to view it.": {"ru": "Задача опубликована. Откройте каталог, чтобы посмотреть её.", "kk": "Тапсырма жарияланды. Оны көру үшін каталогты ашыңыз."},
    "Submit a team proposal": {"ru": "Подать предложение от команды", "kk": "Команда атынан ұсыныс беру"},
    "Team name": {"ru": "Название команды", "kk": "Команда атауы"},
    "Solution idea": {"ru": "Идея решения", "kk": "Шешім идеясы"},
    "Plan": {"ru": "План", "kk": "Жоспар"},
    "Estimated timeline": {"ru": "Примерные сроки", "kk": "Болжамды мерзім"},
    "e.g. 2 weeks, 20 hours": {"ru": "Например: 2 недели, 20 часов", "kk": "Мысалы: 2 апта, 20 сағат"},
    "Prototype URL (optional)": {"ru": "Ссылка на прототип (необязательно)", "kk": "Прототип сілтемесі (міндетті емес)"},
    "Prototype URL": {"ru": "Ссылка на прототип", "kk": "Прототип сілтемесі"},
    "Submit proposal": {"ru": "Отправить предложение", "kk": "Ұсынысты жіберу"},
    "Fill in team name, solution idea, plan, and estimated time.": {"ru": "Укажите название команды, идею решения, план и примерные сроки.", "kk": "Команда атауын, шешім идеясын, жоспарды және болжамды мерзімді енгізіңіз."},
    "Prototype URL must be a valid http:// or https:// link.": {"ru": "Ссылка на прототип должна быть корректной и начинаться с http:// или https://.", "kk": "Прототип сілтемесі дұрыс болуы және http:// немесе https:// деп басталуы керек."},
    "Proposal submitted as Pending. The business will review it manually.": {"ru": "Предложение отправлено и ожидает рассмотрения. Представитель бизнеса рассмотрит его лично.", "kk": "Ұсыныс жіберілді және қарауды күтуде. Бизнес өкілі оны өзі қарайды."},
    "Other": {"ru": "Другое", "kk": "Басқа"},
    "All": {"ru": "Все", "kk": "Барлығы"},
    "Challenge catalog": {"ru": "Каталог задач", "kk": "Тапсырмалар каталогы"},
    "Real problems.": {"ru": "Реальные задачи.", "kk": "Нақты мәселелер."},
    "Student ingenuity.": {"ru": "Студенческие идеи.", "kk": "Студенттік идеялар."},
    "Discover business problems ready for student teams.": {"ru": "Найдите бизнес-задачу для вашей студенческой команды.", "kk": "Студенттік командаңызға арналған бизнес тапсырмасын табыңыз."},
    "Explore every stage, from an early draft to a priority challenge.": {"ru": "Все стадии готовности: от первого черновика до приоритетной задачи.", "kk": "Алғашқы жобадан басым тапсырмаға дейінгі барлық дайындық деңгейі."},
    "Topic / Industry": {"ru": "Тема / Отрасль", "kk": "Тақырып / Сала"},
    "Readiness level": {"ru": "Уровень готовности", "kk": "Дайындық деңгейі"},
    "Sort": {"ru": "Сортировка", "kk": "Сұрыптау"},
    "Highest readiness": {"ru": "Сначала высокая готовность", "kk": "Алдымен дайындығы жоғары"},
    "Lowest readiness": {"ru": "Сначала низкая готовность", "kk": "Алдымен дайындығы төмен"},
    "{count} of {total} published challenges": {"ru": "Показано задач: {count} из {total}", "kk": "Көрсетілген тапсырмалар: {count} / {total}"},
    "No published tasks match this filter.": {"ru": "Нет опубликованных задач, соответствующих фильтрам.", "kk": "Сүзгілерге сәйкес жарияланған тапсырмалар жоқ."},
    "Business details coming soon.": {"ru": "Подробности задачи появятся позже.", "kk": "Тапсырма мәліметтері кейінірек қосылады."},
    "Full brief and team proposal": {"ru": "Полное описание и предложение команды", "kk": "Толық сипаттама және команда ұсынысы"},
    "Not provided": {"ru": "Не указано", "kk": "Көрсетілмеген"},
    "Student teams ({count})": {"ru": "Студенческие команды ({count})", "kk": "Студенттік командалар ({count})"},
    "Use an existing team name or enter a new one when submitting a proposal.": {"ru": "При подаче предложения выберите название существующей команды или укажите новое.", "kk": "Ұсыныс бергенде бұрыннан бар команданың атауын немесе жаңа атау енгізіңіз."},
    "Business Dashboard": {"ru": "Кабинет бизнеса", "kk": "Бизнес кабинеті"},
    "Good ideas.": {"ru": "Хорошие идеи.", "kk": "Жақсы идеялар."},
    "Your next collaborators.": {"ru": "Ваши будущие партнёры.", "kk": "Болашақ серіктестеріңіз."},
    "Review student proposals and choose who to work with.": {"ru": "Рассматривайте предложения студентов и выбирайте, с кем работать.", "kk": "Студенттердің ұсыныстарын қарап, кіммен жұмыс істейтініңізді таңдаңыз."},
    "Every decision is manual. Accepting a proposal does not reject or select any other team. You can change a decision using the buttons below.": {"ru": "Каждое решение принимаете вы. Принятие одного предложения не влияет на остальные команды. Решение можно изменить кнопками ниже.", "kk": "Әр шешімді өзіңіз қабылдайсыз. Бір ұсынысты қабылдау басқа командаларға әсер етпейді. Шешімді төмендегі батырмалармен өзгертуге болады."},
    "Published challenges": {"ru": "Опубликованные задачи", "kk": "Жарияланған тапсырмалар"},
    "Awaiting review": {"ru": "Ожидают рассмотрения", "kk": "Қарауды күтуде"},
    "Accepted proposals": {"ru": "Принятые предложения", "kk": "Қабылданған ұсыныстар"},
    "Publish a task to start receiving proposals.": {"ru": "Опубликуйте задачу, чтобы получать предложения.", "kk": "Ұсыныстар алу үшін тапсырма жариялаңыз."},
    "Challenge / Proposals": {"ru": "Задача / Предложения", "kk": "Тапсырма / Ұсыныстар"},
    "No proposals yet.": {"ru": "Предложений пока нет.", "kk": "Әзірге ұсыныстар жоқ."},
    "Student team": {"ru": "Студенческая команда", "kk": "Студенттік команда"},
    "Accept": {"ru": "Принять", "kk": "Қабылдау"},
    "Reject": {"ru": "Отклонить", "kk": "Қабылдамау"},
    "Pending": {"ru": "На рассмотрении", "kk": "Қаралуда"},
    "Accepted": {"ru": "Принято", "kk": "Қабылданды"},
    "Rejected": {"ru": "Отклонено", "kk": "Қабылданбады"},
    "From vague business needs to student-ready challenges.": {"ru": "От неопределённых потребностей бизнеса к понятным задачам для студентов.", "kk": "Бұлыңғыр бизнес қажеттіліктерінен студенттерге түсінікті тапсырмаларға."},
    "AI-powered challenge platform": {"ru": "Платформа задач с поддержкой ИИ", "kk": "ЖИ көмегімен тапсырмалар платформасы"},
    "Navigation": {"ru": "Навигация", "kk": "Мәзір"},
    "Catalog": {"ru": "Каталог", "kk": "Каталог"},
    "Readiness levels": {"ru": "Уровни готовности", "kk": "Дайындық деңгейлері"},
    "Draft": {"ru": "Черновик", "kk": "Бастапқы нұсқа"},
    "Working": {"ru": "В работе", "kk": "Толықтыруда"},
    "Ready": {"ru": "Готово", "kk": "Дайын"},
    "Priority": {"ru": "Приоритет", "kk": "Басым"},
    "DRAFT": {"ru": "ЧЕРНОВИК", "kk": "БАСТАПҚЫ НҰСҚА"},
    "WORKING": {"ru": "В РАБОТЕ", "kk": "ТОЛЫҚТЫРУДА"},
    "READY": {"ru": "ГОТОВО", "kk": "ДАЙЫН"},
    "PRIORITY": {"ru": "ПРИОРИТЕТ", "kk": "БАСЫМ"},
    "Could not read or save the app data: {error}. Check the JSON files and folder permissions, then retry.": {"ru": "Не удалось прочитать или сохранить данные приложения: {error}. Проверьте JSON-файлы и права доступа к папке, затем повторите попытку.", "kk": "Қолданба деректерін оқу немесе сақтау мүмкін болмады: {error}. JSON файлдарын және бумаға қол жеткізу рұқсаттарын тексеріп, әрекетті қайталаңыз."},
    "Category": {"ru": "Категория", "kk": "Санат"},
    "Points": {"ru": "Баллы", "kk": "Ұпай"},
    "Maximum": {"ru": "Максимум", "kk": "Ең жоғары ұпай"},
    "Reason": {"ru": "Обоснование", "kk": "Негіздеме"},
    "Improvement": {"ru": "Как улучшить", "kk": "Жақсарту жолы"},
    "Completion checklist (not AI quality scoring)": {"ru": "Проверка заполненности (без оценки качества ИИ)", "kk": "Толтырылуды тексеру (ЖИ сапа бағасы емес)"},
    "AI quality assessment": {"ru": "Оценка качества с помощью ИИ", "kk": "ЖИ арқылы сапаны бағалау"},
    "Describe the business situation and current process.": {"ru": "Опишите ситуацию в бизнесе и текущий процесс.", "kk": "Бизнестегі жағдайды және қазіргі үдерісті сипаттаңыз."},
    "Explain the problem and why it matters.": {"ru": "Объясните проблему и её важность.", "kk": "Мәселені және оның маңызын түсіндіріңіз."},
    "List available datasets, documents, or examples and how to access them.": {"ru": "Перечислите доступные данные, документы или примеры и способы получить к ним доступ.", "kk": "Қолжетімді деректерді, құжаттарды немесе мысалдарды және оларға қол жеткізу жолдарын көрсетіңіз."},
    "Name the deliverable students should produce.": {"ru": "Укажите, какой результат должны подготовить студенты.", "kk": "Студенттер қандай нәтиже дайындауы керек екенін көрсетіңіз."},
    "Define measurable criteria for a successful result.": {"ru": "Определите измеримые критерии успешного результата.", "kk": "Сәтті нәтижені бағалайтын өлшенетін өлшемдерді анықтаңыз."},
    "Specify the deadline, budget, tools, and privacy limits.": {"ru": "Укажите сроки, бюджет, инструменты и ограничения по конфиденциальности.", "kk": "Мерзімді, бюджетті, құралдарды және құпиялылық шектеулерін көрсетіңіз."},
    "Identify who will use the result and their needs.": {"ru": "Укажите, кто будет использовать результат и каковы потребности этих людей.", "kk": "Нәтижені кім пайдаланатынын және олардың қажеттіліктерін анықтаңыз."},
    "Provide a contact and explain how students can ask questions.": {"ru": "Укажите контакт и объясните, как студенты смогут задавать вопросы.", "kk": "Байланыс деректерін беріп, студенттер сұрақтарын қалай қоя алатынын түсіндіріңіз."},
    "Configure OPENAI_API_KEY in your local .env file, then retry.": {"ru": "Укажите OPENAI_API_KEY в локальном файле .env, затем повторите попытку.", "kk": "Жергілікті .env файлында OPENAI_API_KEY мәнін орнатып, әрекетті қайталаңыз."},
    "OpenAI could not complete the analysis. Check your connection, API access, billing, and model configuration, then retry. Your draft is unchanged.": {"ru": "OpenAI не удалось завершить анализ. Проверьте соединение, доступ к API, оплату и настройки модели, затем повторите попытку. Черновик сохранён без изменений.", "kk": "OpenAI талдауды аяқтай алмады. Байланысты, API қолжетімділігін, төлемді және модель баптауларын тексеріп, әрекетті қайталаңыз. Бастапқы нұсқа өзгеріссіз сақталды."},
    "AI returned an incomplete, unsupported, or invalid analysis. Your draft is unchanged. Please retry or clarify the description.": {"ru": "ИИ вернул неполный, неподтверждённый или некорректный анализ. Черновик сохранён без изменений. Повторите попытку или уточните описание.", "kk": "ЖИ толық емес, расталмаған немесе жарамсыз талдау қайтарды. Бастапқы нұсқа өзгеріссіз сақталды. Әрекетті қайталаңыз немесе сипаттаманы нақтылаңыз."},
    "Describe the business situation and current process. (+10 points)": {"ru": "Опишите ситуацию в бизнесе и текущий процесс. (+10 балл.)", "kk": "Бизнестегі жағдайды және қазіргі үдерісті сипаттаңыз. (+10 ұпай)"},
    "Explain the problem and why it matters. (+10 points)": {"ru": "Объясните проблему и её важность. (+10 балл.)", "kk": "Мәселені және оның маңызын түсіндіріңіз. (+10 ұпай)"},
    "List available datasets, documents, or examples and how to access them. (+20 points)": {"ru": "Перечислите доступные данные, документы или примеры и способы получить к ним доступ. (+20 балл.)", "kk": "Қолжетімді деректерді, құжаттарды немесе мысалдарды және оларға қол жеткізу жолдарын көрсетіңіз. (+20 ұпай)"},
    "Name the deliverable students should produce. (+15 points)": {"ru": "Укажите, какой результат должны подготовить студенты. (+15 балл.)", "kk": "Студенттер қандай нәтиже дайындауы керек екенін көрсетіңіз. (+15 ұпай)"},
    "Define measurable criteria for a successful result. (+15 points)": {"ru": "Определите измеримые критерии успешного результата. (+15 балл.)", "kk": "Сәтті нәтижені бағалайтын өлшенетін өлшемдерді анықтаңыз. (+15 ұпай)"},
    "Specify the deadline, budget, tools, and privacy limits. (+10 points)": {"ru": "Укажите сроки, бюджет, инструменты и ограничения по конфиденциальности. (+10 балл.)", "kk": "Мерзімді, бюджетті, құралдарды және құпиялылық шектеулерін көрсетіңіз. (+10 ұпай)"},
    "Identify who will use the result and their needs. (+10 points)": {"ru": "Укажите, кто будет использовать результат и каковы потребности этих людей. (+10 балл.)", "kk": "Нәтижені кім пайдаланатынын және олардың қажеттіліктерін анықтаңыз. (+10 ұпай)"},
    "Provide a contact and explain how students can ask questions. (+10 points)": {"ru": "Укажите контакт и объясните, как студенты смогут задавать вопросы. (+10 балл.)", "kk": "Байланыс деректерін беріп, студенттер сұрақтарын қалай қоя алатынын түсіндіріңіз. (+10 ұпай)"},
    "Changes interface language. Task descriptions and AI responses keep their original language.": {"ru": "Меняет язык интерфейса. Описания задач и ответы ИИ сохраняют исходный язык.", "kk": "Интерфейс тілін өзгертеді. Тапсырма сипаттамалары мен ЖИ жауаптары бастапқы тілінде қалады."},
}


# Capture the language for this render, including widget option formatting.
LANGUAGE = st.session_state.get("ui_language", "en")


def t(text, **values):
    translated = TRANSLATIONS.get(text, {}).get(LANGUAGE, text)
    return translated.format(**values) if values else translated


def refresh_language_labels():
    # Streamlit 1.64 needs the selected values resent when format_func changes.
    # Keep their canonical values; only their visible labels change language.
    for key in ("navigation", "catalog_industry", "catalog_readiness", "catalog_sort"):
        if key in st.session_state:
            st.session_state[key] = st.session_state[key]


def show_readiness(task, *, prominent=False, previous_score=None, stale=False, summary_container=None):
    result = task_readiness(task)
    if prominent:
        with summary_container if summary_container is not None else st.container(border=True):
            st.markdown(f'<div class="tf-eyebrow">{t("Task readiness")}</div>', unsafe_allow_html=True)
            score_column, improvement_column = st.columns(2)
            score_column.metric(t("Readiness score"), f"{result['score']}/100", t(result["level"]), delta_color="off")
            if previous_score is not None:
                improvement_column.metric(
                    t("Readiness improvement" if not stale else "Last assessed improvement"),
                    f"{previous_score} → {result['score']}",
                    t("{points:+d} points", points=result['score'] - previous_score),
                )
            st.progress(result["score"] / 100)
            st.caption(t(result["source"]))
    else:
        st.caption(t(result["source"]))
        st.metric(t("Readiness score"), f"{result['score']}/100", t(result["level"]), delta_color="off")
        st.progress(result["score"] / 100)
    st.markdown(f'<div class="tf-section tf-eyebrow">{t("Readiness breakdown")}</div>', unsafe_allow_html=True)
    st.caption(t("See what is clear, what is missing, and where your brief can improve."))
    st.table([{t(column): t(value) if column == "Category" else value
               for column, value in row.items()} for row in result["breakdown"]])
    if result["missing"]:
        st.warning(t("Missing information: ") + ", ".join(t(field) for field in result["missing"]))
        suggestions = result["suggestions"]
        if task.get("ai_analysis"):
            # Display only categories with room to earn points; stored scores and
            # explanations stay unchanged, including full-score categories.
            improvements = sorted(result["breakdown"],
                                  key=lambda row: row["Maximum"] - row["Points"], reverse=True)
            suggestions = [row["Improvement"] for row in improvements
                           if row["Points"] < row["Maximum"] and row["Improvement"].strip()]
        suggestions = [suggestion for suggestion in suggestions
                       if suggestion.strip().rstrip(".! ").casefold() not in
                       {"no improvement needed", "no improvements needed", "no improvement necessary",
                        "no action needed", "no changes needed", "none", "n/a"}]
        if suggestions:
            st.markdown(f'<div class="tf-section tf-eyebrow">{t("How to improve")}</div>', unsafe_allow_html=True)
            st.caption(t("Suggestions for increasing the score"))
            for i, suggestion in enumerate(suggestions, 1):
                st.markdown(f'<div class="tf-improvement"><span class="tf-number">{i:02d}</span>'
                            f'<span>{escape(t(suggestion))}</span></div>', unsafe_allow_html=True)
    elif not task.get("ai_analysis"):
        st.success(t("All readiness fields are filled in. Review the detail with the business contact."))
    return result


def save_card_edit(key):
    st.session_state.draft[key] = st.session_state[f"card_{key}"].strip()
    st.session_state.confirm_publish = False


def run_analysis(mode):
    """Save results before spinner cleanup can yield to a queued widget rerun."""
    state = st.session_state
    logger.info("Analyze button triggered: mode=%s", mode)
    description = state.get("business_description", "").strip()
    if mode == "draft" and not description:
        state.ai_error = "Enter a business problem first."
        return
    answers = list(state.get("answer_history", []))
    if mode == "clarify":
        new_answers = [{**q, "answer": state.get(f"answer_{state.analysis_version}_{i}", "").strip()}
                       for i, q in enumerate(state.analysis["questions"])]
        new_answers = [answer for answer in new_answers if answer["answer"]]
        if not new_answers:
            state.ai_error = "Answer at least one clarification question first."
            return
        answers.extend(new_answers)
    source_description = description if mode == "draft" else state.get("analyzed_description", "")
    current_card = None if mode == "draft" else dict(state.draft)
    # Capture a session-owned object before the API call. Mutating this object does
    # not yield to Streamlit, unlike accessing st.session_state after the call.
    job = {"mode": mode, "description": description, "answers": answers}
    state.analysis_job = job
    with st.spinner(t("Analyzing the business brief…")):
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


def create_task():
    st.markdown(f'<section class="tf-hero"><div class="tf-eyebrow">{t("Create Task")}</div>'
                f'<h1>{t("Turn business problems")}<br><span class="tf-accent">{t("into student-ready challenges.")}</span></h1>'
                f'<p>{t("AI identifies missing information, asks targeted questions, and helps businesses create actionable challenges.")}</p></section>', unsafe_allow_html=True)
    st.markdown(f'<div class="tf-flow"><div class="tf-step"><b>01</b><span>{t("DESCRIBE")}</span></div>'
                f'<div class="tf-step"><b>02</b><span>{t("CLARIFY")}</span></div>'
                f'<div class="tf-step"><b>03</b><span>{t("IMPROVE")}</span></div>'
                f'<div class="tf-step"><b>04</b><span>{t("PUBLISH")}</span></div></div>', unsafe_allow_html=True)
    state = st.session_state
    if "draft" not in state:
        state.draft = {key: "" for key in TASK_KEYS}
    apply_analysis_result()
    st.subheader(t("Quick AI Draft"))
    st.caption(t("Describe the problem in your own words. AI uses only supplied facts; unknowns stay blank. Review every field before publishing."))
    # Keep the draft across sidebar navigation; widget state alone is discarded by Streamlit.
    if "business_description" not in state:
        state.business_description = state.get("saved_description", "")
    st.text_area(t("Business problem"), key="business_description", placeholder=t("We run an online clothing store and many customers abandon their carts…"),
                 on_change=lambda: state.update(saved_description=state.business_description))
    st.button(t("Analyze with AI"), key="analyze", type="primary", on_click=run_analysis, args=("draft",))
    if state.get("ai_error"):
        st.error(t(state.ai_error))
    # Render the existing score summary above the long editable card.
    readiness_summary = st.container(border=True)
    analysis = state.get("analysis")
    logger.info("Rendering section reached: analysis_present=%s", analysis is not None)
    if analysis:
        st.markdown(f'<div class="tf-section tf-eyebrow">{t("02 / Guided interview")}</div>', unsafe_allow_html=True)
        st.subheader(t("Clarification questions"))
        st.caption(t("Add the details you know. Your answers help turn the problem into an actionable brief."))
        with st.form(f"clarifications_{state.analysis_version}"):
            for i, question in enumerate(analysis["questions"]):
                st.markdown(f'<div class="tf-question"><span class="tf-number">{i + 1:02d}</span>'
                            f'<span>{t("CLARIFICATION")}</span></div>', unsafe_allow_html=True)
                st.text_area(question["question"], key=f"answer_{state.analysis_version}_{i}")
            st.form_submit_button(t("Update task with answers"), key=f"clarifications_{state.analysis_version}_submit",
                                  on_click=run_analysis, args=("clarify",))
    st.markdown(f'<div class="tf-section tf-eyebrow">{t("03 / Refine the brief")}</div>', unsafe_allow_html=True)
    st.subheader(t("Editable task card"))
    st.caption(t("Review the business facts, refine the details, and reanalyze after making changes."))
    labels = {"title": "Title", "data_materials": "Data/materials", "contact": "Contact/interaction format"}
    for key in ("title", "context", "need", "users", "data_materials", "constraints", "expected_result", "success_criteria", "contact"):
        state[f"card_{key}"] = state.draft[key]
        widget = st.text_input if key == "title" else st.text_area
        widget(t(labels.get(key, key.replace("_", " ").capitalize())), key=f"card_{key}",
               on_change=save_card_edit, args=(key,))
    task = dict(state.draft)
    industry = st.text_input(t("Industry (optional)"), key="task_industry",
                             placeholder=t("e.g. Retail, Education, Healthcare"),
                             help=t("Used only to organize the catalog. Blank industries appear as Other."))
    st.button(t("Reanalyze edited card"), key="rescore", on_click=run_analysis, args=("rescore",))
    stale = bool(analysis and task != analysis["task"])
    if analysis:
        if stale:
            st.warning(t("The card has changed. The assessment below is for the previous version. Reanalyze the edited card before publishing."))
        result = show_readiness({**analysis["task"], "ai_analysis": analysis}, prominent=True,
                                previous_score=state.get("previous_score"), stale=stale,
                                summary_container=readiness_summary)
        confirmed = st.checkbox(t("I reviewed the task card and confirm its business facts."), key="confirm_publish")
    else:
        st.caption(t("You can also create a task manually. Until AI analysis succeeds, this is a completion checklist, not a quality score."))
        result = show_readiness(task, prominent=True, summary_container=readiness_summary)
        confirmed = True
    st.markdown(f'<div class="tf-section tf-eyebrow">{t("04 / Share your challenge")}</div>', unsafe_allow_html=True)
    if st.button(t("Publish task"), key="publish", type="primary", disabled=stale or not confirmed):
        if not task["title"]:
            st.error(t("Enter a title before publishing."))
        else:
            values = {**task, "industry": industry.strip(),
                      "readiness_score": result["score"], "readiness_level": result["level"]}
            if analysis:
                values["ai_analysis"] = analysis
            add_record("tasks", values)
            st.success(t("Task published. Open Catalog to view it."))


def proposal_form(task_id):
    with st.form(f"proposal_{task_id}", clear_on_submit=False):
        st.subheader(t("Submit a team proposal"))
        values = {
            "team_name": st.text_input(t("Team name"), key=f"proposal_{task_id}_team_name"),
            "solution_idea": st.text_area(t("Solution idea"), key=f"proposal_{task_id}_solution_idea"),
            "plan": st.text_area(t("Plan"), key=f"proposal_{task_id}_plan"),
            "estimated_time": st.text_input(t("Estimated timeline"), key=f"proposal_{task_id}_estimated_time", placeholder=t("e.g. 2 weeks, 20 hours")),
            "prototype_url": st.text_input(t("Prototype URL (optional)"), key=f"proposal_{task_id}_prototype_url", placeholder="https://example.com/demo"),
        }
        submitted = st.form_submit_button(t("Submit proposal"), key=f"proposal_{task_id}_submit")
    if submitted:
        values = {key: value.strip() for key, value in values.items()}
        if any(not values[key] for key in ("team_name", "solution_idea", "plan", "estimated_time")):
            st.error(t("Fill in team name, solution idea, plan, and estimated time."))
            return
        url = urlparse(values["prototype_url"])
        if values["prototype_url"] and (url.scheme not in ("http", "https") or not url.netloc):
            st.error(t("Prototype URL must be a valid http:// or https:// link."))
            return
        submit_proposal(task_id, values)
        st.success(t("Proposal submitted as Pending. The business will review it manually."))


def task_industry(task):
    """Older JSON records need no migration to appear in the catalog."""
    industry = task.get("industry")
    return industry.strip() if isinstance(industry, str) and industry.strip() else "Other"


def catalog():
    st.markdown(f'<section class="tf-hero"><div class="tf-eyebrow">{t("Challenge catalog")}</div>'
                f'<h1>{t("Real problems.")}<br><span class="tf-accent">{t("Student ingenuity.")}</span></h1>'
                f'<p>{t("Discover business problems ready for student teams.")}</p></section>', unsafe_allow_html=True)
    st.caption(t("Explore every stage, from an early draft to a priority challenge."))
    published = load_records("tasks")
    topic_column, readiness_column, sort_column = st.columns(3)
    industries = sorted({task_industry(task) for task in published}, key=str.casefold)
    topic = topic_column.selectbox(t("Topic / Industry"), ["All"] + [name for name in industries if name != "All"], key="catalog_industry",
                                   format_func=lambda value: t(value) if value in ("All", "Other") else value)
    level = readiness_column.selectbox(t("Readiness level"), ["All", "Draft", "Working", "Ready", "Priority"], key="catalog_readiness", format_func=t)
    order = sort_column.selectbox(t("Sort"), ["Highest readiness", "Lowest readiness"], key="catalog_sort", format_func=t)
    tasks = sorted(published, key=lambda task: task_readiness(task)["score"], reverse=order == "Highest readiness")
    tasks = [task for task in tasks
             if (level == "All" or task_readiness(task)["level"] == level)
             and (topic == "All" or task_industry(task) == topic)]
    st.caption(t("{count} of {total} published challenges", count=len(tasks), total=len(published)))
    if not tasks:
        st.info(t("No published tasks match this filter."))
    for task in tasks:
        result = task_readiness(task)
        with st.container(border=True):
            st.markdown(
                f'<div class="tf-card-header"><span class="tf-level tf-{result["level"].lower()}">{t(result["level"])}</span>'
                f'<div class="tf-score"><strong>{result["score"]}</strong><small> / 100</small></div></div>'
                f'<h3 class="tf-card-title">{escape(task["title"])}</h3>'
                f'<span class="tf-badge">{escape(t("Other") if task_industry(task) == "Other" else task_industry(task))}</span>',
                unsafe_allow_html=True,
            )
            preview = " ".join((task.get("need") or task.get("context") or t("Business details coming soon.")).split())
            st.write(preview if len(preview) <= 220 else preview[:217] + "…")
            with st.expander(f"{task['title']} — {result['score']}/100 · {t(result['level'])}"):
                st.caption(t("Full brief and team proposal"))
                for key, label, _, _ in FIELDS:
                    st.markdown(f"**{t(label)}**")
                    st.write(task.get(key) or t("Not provided"))
                show_readiness(task)
                proposal_form(task["id"])
    teams = load_records("teams")
    with st.expander(t("Student teams ({count})", count=len(teams))):
        for team in teams:
            st.write(team["name"])
        st.caption(t("Use an existing team name or enter a new one when submitting a proposal."))


def dashboard():
    st.markdown(f'<section class="tf-hero"><div class="tf-eyebrow">{t("Business Dashboard")}</div>'
                f'<h1>{t("Good ideas.")}<br><span class="tf-accent">{t("Your next collaborators.")}</span></h1>'
                f'<p>{t("Review student proposals and choose who to work with.")}</p></section>', unsafe_allow_html=True)
    st.caption(t("Every decision is manual. Accepting a proposal does not reject or select any other team. You can change a decision using the buttons below."))
    tasks = load_records("tasks")
    proposals = load_records("proposals")
    task_count, pending_count, accepted_count = st.columns(3)
    task_count.metric(t("Published challenges"), len(tasks))
    pending_count.metric(t("Awaiting review"), sum(proposal["status"] == "Pending" for proposal in proposals))
    accepted_count.metric(t("Accepted proposals"), sum(proposal["status"] == "Accepted" for proposal in proposals))
    if not tasks:
        st.info(t("Publish a task to start receiving proposals."))
    for task in tasks:
        st.markdown(f'<div class="tf-section tf-eyebrow">{t("Challenge / Proposals")}</div>', unsafe_allow_html=True)
        st.subheader(task["title"])
        matches = [proposal for proposal in proposals if proposal["task_id"] == task["id"]]
        if not matches:
            st.caption(t("No proposals yet."))
        for proposal in matches:
            with st.container(border=True):
                st.markdown(f'<div class="tf-card-header"><div><div class="tf-eyebrow">{t("Student team")}</div>'
                            f'<h3 class="tf-card-title">{escape(proposal["team_name"])}</h3></div>'
                            f'<span class="tf-badge">{escape(t(proposal["status"]))}</span></div>', unsafe_allow_html=True)
                for key, label in (("solution_idea", "Solution idea"), ("plan", "Plan"), ("estimated_time", "Estimated timeline"), ("prototype_url", "Prototype URL")):
                    st.markdown(f"**{t(label)}**")
                    st.write(proposal.get(key) or t("Not provided"))
                accept, reject = st.columns(2)
                if accept.button(t("Accept"), key=f"accept_{proposal['id']}", disabled=proposal["status"] == "Accepted"):
                    review_proposal(proposal["id"], "Accepted")
                    st.rerun()
                if reject.button(t("Reject"), key=f"reject_{proposal['id']}", disabled=proposal["status"] == "Rejected"):
                    review_proposal(proposal["id"], "Rejected")
                    st.rerun()


st.sidebar.markdown('<div class="tf-brand">TASKFORGE</div>', unsafe_allow_html=True)
st.sidebar.selectbox("Language / Язык / Тіл", ["en", "ru", "kk"], key="ui_language",
                     format_func={"en": "English", "ru": "Русский", "kk": "Қазақша"}.get,
                     help=t("Changes interface language. Task descriptions and AI responses keep their original language."),
                     on_change=refresh_language_labels)
st.markdown('<div class="tf-topbar"><span class="tf-brand">TASKFORGE</span>'
            f'<span class="tf-tagline">{t("From vague business needs to student-ready challenges.")}</span></div>', unsafe_allow_html=True)
st.sidebar.caption(t("AI-powered challenge platform"))
page = st.sidebar.radio(t("Navigation"), ["Create Task", "Catalog", "Business Dashboard"], key="navigation", format_func=t)
st.sidebar.markdown(f'<div class="tf-legend"><p class="tf-eyebrow">{t("Readiness levels")}</p>'
                    f'<div><span>{t("Draft").upper()}</span><span>0–39</span></div>'
                    f'<div><span>{t("Working").upper()}</span><span>40–69</span></div>'
                    f'<div><span>{t("Ready").upper()}</span><span>70–89</span></div>'
                    f'<div><span>{t("Priority").upper()}</span><span>90–100</span></div></div>', unsafe_allow_html=True)
try:
    {"Create Task": create_task, "Catalog": catalog, "Business Dashboard": dashboard}[page]()
except (OSError, ValueError) as error:
    st.error(t("Could not read or save the app data: {error}. Check the JSON files and folder permissions, then retry.", error=error))
