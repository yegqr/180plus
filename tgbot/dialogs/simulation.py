import time

from typing import Any
from aiogram import F
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import ContentType, Message
from aiogram_dialog import Dialog, Window, DialogManager, ShowMode
from aiogram_dialog.api.entities import MediaAttachment, MediaId
from aiogram_dialog.widgets.kbd import Button, Row, Cancel, Select, Group, Column, Back
from aiogram_dialog.widgets.media import DynamicMedia
from aiogram_dialog.widgets.text import Const, Format
from aiogram_dialog.widgets.input import MessageInput

from tgbot.services.album_manager import AlbumManager

from infrastructure.database.models import User, Question
from infrastructure.database.repo.requests import RequestsRepo

UKR_LETTERS = "АБВГДЕЄЖЗИІЇЙКЛМНОПРСТУФХЦЧШЩЬЮЯ"
ENG_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

class SimulationSG(StatesGroup):
    select_year = State()
    select_session = State()
    question = State()
    summary = State()
    review = State()
    navigation = State()

# --- Getters ---

async def get_sim_years(dialog_manager: DialogManager, **kwargs):
    repo: RequestsRepo = dialog_manager.middleware_data.get("repo")
    user: User = dialog_manager.middleware_data.get("user")
    years = await repo.questions.get_unique_years(user.selected_subject)
    return {
        "years": [(str(y), y) for y in years],
        "subject": user.selected_subject,
        "has_years": len(years) > 0
    }

async def get_sim_sessions(dialog_manager: DialogManager, **kwargs):
    repo: RequestsRepo = dialog_manager.middleware_data.get("repo")
    user: User = dialog_manager.middleware_data.get("user")
    year = dialog_manager.dialog_data.get("sim_year")
    
    # Fetch all sessions for this year/subject
    all_sessions = await repo.questions.get_unique_sessions(user.selected_subject, year)
    # Fetch completed sessions for this user
    completed = await repo.results.get_completed_sessions(user.user_id, user.selected_subject, year)
    
    # Beautify subject tags
    subject_map = {
        "math": "Math 🔢",
        "mova": "🇺🇦 Mova", 
        "eng": "English 🇬🇧",
        "hist": "History 🇺🇦",
        "physics": "Physics 🧲",
    }
    subj_formatted = subject_map.get(user.selected_subject, user.selected_subject)

    session_items = []
    for s in all_sessions:
        label = s
        if s in completed:
            label += " ✅"
        session_items.append((label, s))

    return {
        "sessions": session_items,
        "year": year,
        "subject": subj_formatted,
        "has_prev": False,
        "has_next": False
    }

async def get_question_data(dialog_manager: DialogManager, **kwargs):
    repo: RequestsRepo = dialog_manager.middleware_data.get("repo")
    user: User = dialog_manager.middleware_data.get("user")
    
    if "q_ids" not in dialog_manager.dialog_data:
        year = dialog_manager.dialog_data.get("sim_year")
        session = dialog_manager.dialog_data.get("sim_session")
        
        questions = await repo.questions.get_questions_by_criteria(user.selected_subject, year, session)
        q_ids = [q.id for q in questions]
        
        if not q_ids:
            return {"has_questions": False, "question_image": None, "counter": "0/0"}
            
        dialog_manager.dialog_data["q_ids"] = q_ids
        dialog_manager.dialog_data["current_index"] = 0 
        dialog_manager.dialog_data["answers"] = {}
        dialog_manager.dialog_data["start_time"] = time.time()
    
    q_ids = dialog_manager.dialog_data["q_ids"]
    current_idx = dialog_manager.dialog_data.get("current_index", 0)
    if not q_ids: return {"has_questions": False}

    current_id = q_ids[current_idx]
    question: Question = await repo.questions.get_question_by_id(current_id)
    

    # Determine if album is active
    is_album = bool(dialog_manager.dialog_data.get("album_message_ids"))
    
    # If album, we don't show DynamicMedia
    image = None
    has_photos = False
    
    if not is_album:
        # Build the combined images list to know which single image to show
        images = []
        if question.image_file_id:
            images.append(question.image_file_id)
        if question.images:
            for img in question.images:
                if img not in images:
                    images.append(img)
                    
        if images:
            current_image_id = images[0]
            has_photos = True
            image = MediaAttachment(type=ContentType.PHOTO, file_id=MediaId(current_image_id))
    
    choice_variants = []
    letters_source = ENG_LETTERS if user.selected_subject == "eng" else UKR_LETTERS

    if question.q_type == "choice":
        count = int(question.correct_answer.get("options", 5))
        choice_variants = [(letters_source[i], letters_source[i]) for i in range(count)]

    match_nums = []
    match_letters = []
    if question.q_type == "match":
        options = str(question.correct_answer.get("options", "3x5")).lower()
        try:
            n, m = map(int, options.split('x'))
        except:
            n, m = 3, 5
        match_nums = [(str(i+1), str(i+1)) for i in range(n)]
        match_letters = [(letters_source[i], letters_source[i]) for i in range(m)]

    answers = dialog_manager.dialog_data.get("answers", {})
    ans_data = answers.get(str(current_id))
    
    current_answer_text = "немає"
    if ans_data:
        if question.q_type == "match":
            pairs = [f"{k}-{v}" for k, v in sorted(ans_data.items())]
            current_answer_text = ", ".join(pairs)
        else:
            current_answer_text = str(ans_data)

    active_num = dialog_manager.dialog_data.get("active_match_num")
    hint = "Обери варіант:" if question.q_type == "choice" else \
           f"Обери літеру для {active_num}:" if active_num else \
           "Обери цифру:" if question.q_type == "match" else \
           "✍️ Напиши цифри відповіді (порядок неважливий, наприклад: 123)" if (question.q_type == "short" and user.selected_subject == "hist") else \
           "Напиши відповідь у чат:"

    material = await repo.materials.get_by_subject(user.selected_subject)
    has_materials = bool(material and material.images)
    show_materials = dialog_manager.dialog_data.get("show_materials", False)

    materials_label = "📚 Довідкові матеріали (Приховати)" if show_materials else "📚 Довідкові матеріали (Показати)"

    return {
        "has_questions": True,
        "question_image": image, # Only for single Mode
        "has_image": has_photos and not is_album,
        "is_album": is_album,
        "counter": f"{current_idx + 1}/{len(q_ids)}",
        "q_type": question.q_type,
        "choice_variants": choice_variants,
        "match_nums": match_nums,
        "match_letters": match_letters,
        "active_num": active_num,
        "current_answer": current_answer_text,
        "hint": hint,
        "has_materials": has_materials,
        "materials_label": materials_label,
    }

async def get_nav_data(dialog_manager: DialogManager, **kwargs):
    q_ids = dialog_manager.dialog_data.get("q_ids", [])
    current_idx = dialog_manager.dialog_data.get("current_index", 0)
    
    # Grid of 1..N
    items = [(str(i+1), i) for i in range(len(q_ids))]
    
    return {
        "nav_items": items,
        "total": len(q_ids)
    }

# --- Handlers ---


async def on_year_selected(c: Any, w: Any, dm: DialogManager, item_id: str):
    dm.dialog_data["sim_year"] = int(item_id)
    dm.dialog_data["session_page"] = 0
    await dm.switch_to(SimulationSG.select_session)

async def on_session_selected(c: Any, w: Any, dm: DialogManager, item_id: str):
    dm.dialog_data["sim_session"] = item_id
    
    # Pre-load questions and setup first view
    repo: RequestsRepo = dm.middleware_data.get("repo")
    user: User = dm.middleware_data.get("user")
    year = dm.dialog_data.get("sim_year")
    
    questions = await repo.questions.get_questions_by_criteria(user.selected_subject, year, item_id)
    q_ids = [q.id for q in questions]
    
    if not q_ids:
        # Handle empty session?
        dm.dialog_data["q_ids"] = []
    else:
        dm.dialog_data["q_ids"] = q_ids
        dm.dialog_data["start_time"] = time.time()
        dm.dialog_data["answers"] = {}
        # Initial View
        await update_question_view(dm, 0)
        
    # Check for previous failures in this session
    failed_ids = await repo.logs.get_failed_questions_in_last_sim(user.user_id, item_id)
    if failed_ids:
        # Find Q numbers for these IDs
        # We need to map ID -> Number
        # We have questions objects.
        q_map = {q.id: q.q_number for q in questions}
        failed_nums = sorted([q_map[fid] for fid in failed_ids if fid in q_map])
        
        if failed_nums:
            nums_str = ", ".join(map(str, failed_nums))
            # Just send a message? Or show in window?
            # sending message is easier for now to catch attention
            # "Ця симуляція підступна! Ти її вже вирішував/ла. Be careful на завданнях 2; 4; 22)"
            await c.message.answer(f"⚠️ <b>Ця симуляція підступна!</b> Ти її вже вирішував/ла.\nBe careful на завданнях: <b>{nums_str}</b>")

    await dm.switch_to(SimulationSG.question)


async def update_question_view(dm: DialogManager, new_index: int):
    """
    Handles switching questions, sending new albums, and cleaning old ones.
    """
    # 1. Cleanup Old Album
    bot = dm.middleware_data.get("bot")
    old_album_ids = dm.dialog_data.get("album_message_ids")
    
    if old_album_ids:
        # We need chat_id. From event? 
        # dm.event might be CallbackQuery or Message.
        chat_id = dm.middleware_data.get("event_chat").id # Or user.user_id
        # Safe way:
        if dm.event and getattr(dm.event, "chat", None):
             chat_id = dm.event.chat.id
        elif dm.middleware_data.get("event_from_user"):
             chat_id = dm.middleware_data.get("event_from_user").id
             
        await AlbumManager.cleanup_album(bot, chat_id, old_album_ids)
        dm.dialog_data["album_message_ids"] = []

    # 2. Setup New Question
    q_ids = dm.dialog_data.get("q_ids", [])
    if not q_ids:
        dm.dialog_data["current_index"] = 0
        return

    # Wrap index
    if new_index >= len(q_ids): new_index = 0
    if new_index < 0: new_index = len(q_ids) - 1
    
    dm.dialog_data["current_index"] = new_index
    current_id = q_ids[new_index]
    
    repo: RequestsRepo = dm.middleware_data.get("repo")
    question = await repo.questions.get_question_by_id(current_id)
    
    # 3. Check for Album (including materials)
    images = []
    if question.image_file_id:
        images.append(question.image_file_id)
    if question.images:
        for img in question.images:
            if img not in images:
                images.append(img)
    
    if dm.dialog_data.get("show_materials"):
        repo: RequestsRepo = dm.middleware_data.get("repo")
        user: User = dm.middleware_data.get("user")
        material = await repo.materials.get_by_subject(user.selected_subject)
        if material and material.images:
            images = images + material.images
        
    if len(images) > 1:
        # Send Album
        chat_id = dm.middleware_data.get("event_chat").id
        
        # BUG FIX: Delete previous dialog message to prevent "hanging"
        try:
             stack = dm.current_stack()
             if stack and stack.last_message_id:
                 await bot.delete_message(chat_id, stack.last_message_id)
        except Exception:
            pass

        album_ids = await AlbumManager.send_album(bot, chat_id, images, caption=None)
        dm.dialog_data["album_message_ids"] = album_ids
        dm.show_mode = ShowMode.SEND
    else:
        # Single Image -> Use DynamicMedia in Window
        dm.show_mode = ShowMode.EDIT

async def on_choice_selected(c: Any, w: Any, dm: DialogManager, item_id: str):
    q_ids = dm.dialog_data.get("q_ids", [])
    current_id = q_ids[dm.dialog_data.get("current_index", 0)]
    dm.dialog_data["answers"][str(current_id)] = item_id

async def on_match_num_selected(c: Any, w: Any, dm: DialogManager, item_id: str):
    dm.dialog_data["active_match_num"] = item_id

async def on_match_letter_selected(c: Any, w: Any, dm: DialogManager, item_id: str):
    active_num = dm.dialog_data.get("active_match_num")
    if not active_num: return
    
    q_ids = dm.dialog_data.get("q_ids", [])
    current_id = str(q_ids[dm.dialog_data.get("current_index", 0)])
    
    answers = dm.dialog_data.get("answers", {})
    ans_data = answers.get(current_id, {})
    if not isinstance(ans_data, dict): ans_data = {}
    
    ans_data[active_num] = item_id
    answers[current_id] = ans_data
    dm.dialog_data["answers"] = answers
    dm.dialog_data["active_match_num"] = None
async def on_match_clear(c: Any, b: Button, dm: DialogManager):
    q_ids = dm.dialog_data.get("q_ids", [])
    current_id = str(q_ids[dm.dialog_data.get("current_index", 0)])
    if current_id in dm.dialog_data["answers"]:
        del dm.dialog_data["answers"][current_id]
    dm.dialog_data["active_match_num"] = None

async def on_answer_text(m: Message, w: MessageInput, dm: DialogManager):
    dm.show_mode = ShowMode.EDIT
    q_ids = dm.dialog_data.get("q_ids", [])
    if not q_ids: return
    current_id = str(q_ids[dm.dialog_data.get("current_index", 0)])
    dm.dialog_data["answers"][current_id] = m.text
    await m.delete()

async def on_next(c: Any, b: Button, dm: DialogManager):
    dm.dialog_data["active_match_num"] = None
    curr = dm.dialog_data.get("current_index", 0)
    await update_question_view(dm, curr + 1)

async def on_prev(c: Any, b: Button, dm: DialogManager):
    dm.dialog_data["active_match_num"] = None
    curr = dm.dialog_data.get("current_index", 0)
    await update_question_view(dm, curr - 1)

async def on_finish(c: Any, b: Button, dm: DialogManager):
    dm.dialog_data["end_time"] = time.time()
    # Results will be saved in summary getter (or here)
    # Cleanup album on finish
    bot = dm.middleware_data.get("bot")
    old_album_ids = dm.dialog_data.get("album_message_ids")
    if old_album_ids:
        chat_id = dm.middleware_data.get("event_chat").id
        await AlbumManager.cleanup_album(bot, chat_id, old_album_ids)
        dm.dialog_data["album_message_ids"] = []

    # Save Result and Logs
    repo: RequestsRepo = dm.middleware_data.get("repo")
    user: User = dm.middleware_data.get("user")
    
    # We need to calculate score here to save it?
    # Or we delegate saving to a service function to avoid code duplication with getter?
    # For now, let's just save the Logs (UserActionLog).
    # ExamResult saving might trigger "completed" flag.
    
    # 1. Calculate Score & Prepare Logs
    answers = dm.dialog_data.get("answers", {})
    q_ids = dm.dialog_data.get("q_ids", [])
    session_id = dm.dialog_data.get("sim_session")
    subject = user.selected_subject
    
    total_score = 0
    total_max = 0
    logs_to_save = []
    
    for q_id_str in q_ids:
        qid = int(q_id_str)
        user_ans = answers.get(str(qid))
        question = await repo.questions.get_question_by_id(qid)
        correct = question.correct_answer
        
        q_score = 0
        q_max = 0
        
        if subject == "hist":
            # OFFICIAL HISTORY SCORING (54 PTS MAX)
            # 1-20: Choice (1), 21-24: Match (4), 25-27: Sequence (3), 28-30: Cluster (3)
            num = question.q_number
            if 1 <= num <= 20:
                q_max = 1
                c_ans = str(correct.get("answer", "")).strip().upper()
                if user_ans and str(user_ans).strip().upper() == c_ans:
                    q_score = 1
            elif 21 <= num <= 24:
                q_max = 4
                target_pairs = correct.get("pairs", {})
                if isinstance(user_ans, dict):
                    for k, v in user_ans.items():
                        if target_pairs.get(str(k)) == str(v):
                            q_score += 1
            elif 25 <= num <= 30:
                q_max = 3
                if user_ans:
                    # Case A: User answered as Match (dict)
                    if isinstance(user_ans, dict):
                         target_pairs = correct.get("pairs", {})
                         matches = 0
                         for k, v in user_ans.items():
                             if target_pairs.get(str(k)) == str(v):
                                 matches += 1
                         # Sequence/Cluster max 3 pts
                         q_score = min(3, matches)
                    
                    # Case B: User answered as String/Digits
                    else:
                        c_str = str(correct.get("answer", ""))
                        c_digits = [c for c in c_str if c.isdigit()]
                        # Fallback for Match stored as String: try keys if values are not digits?
                        # But mostly likely if it's String answer, correct['answer'] should exist.
                        # If not, let's try to extract digits from pairs keys if no answer string.
                        if not c_digits and "pairs" in correct:
                            # Use keys as digits if values seem to be letters
                             c_digits = [str(k) for k in sorted(correct["pairs"].keys()) if str(k).isdigit()]

                        u_str = str(user_ans)
                        u_digits = [c for c in u_str if c.isdigit()]
                        
                        if 25 <= num <= 27:
                            # Sequence: 1 pt per digit in correct position
                            for i in range(min(len(u_digits), len(c_digits))):
                                if u_digits[i] == c_digits[i]:
                                    q_score += 1
                        else:
                            # Cluster (28-30): 1 pt per guessed digit (intersection)
                            correct_set = set(c_digits)
                            user_set = set(u_digits)
                            q_score = len(correct_set.intersection(user_set))
            else:
                # Fallback for unexpected numbers
                q_max = 1
                if user_ans and str(user_ans).strip() == str(correct.get("answer", "")).strip():
                    q_score = 1
        else:
            # STANDARD SCORING FOR OTHER SUBJECTS
            if question.q_type == "choice":
                q_max = 1
                if user_ans and str(user_ans).strip().upper() == str(correct.get("answer")).strip().upper():
                    q_score = 1
            elif question.q_type == "short":
                q_max = 2
                points_if_correct = q_max
                if user_ans:
                    u_str = str(user_ans).strip()
                    c_str = str(correct.get("answer")).strip()
                    is_correct = False
                    try:
                        if float(u_str.replace(",", ".")) == float(c_str.replace(",", ".")): is_correct = True
                    except:
                        if u_str == c_str: is_correct = True
                    
                    if not is_correct and subject in ["mova", "eng"]:
                        if u_str.isdigit() and c_str.isdigit():
                            is_correct = (sorted(u_str) == sorted(c_str))
                    
                    if is_correct:
                        q_score = points_if_correct
            elif question.q_type == "match":
                target_pairs = correct.get("pairs", {})
                q_max = len(target_pairs)
                if isinstance(user_ans, dict):
                    for n, l in user_ans.items():
                        if target_pairs.get(str(n)) == str(l):
                            q_score += 1
        
        total_score += q_score
        total_max += q_max
        
        # Log entry for answered questions
        if user_ans:
            log_ans = str(user_ans)
            if isinstance(user_ans, dict):
                log_ans = ", ".join([f"{k}-{v}" for k, v in sorted(user_ans.items())])
            
            logs_to_save.append({
                "user_id": user.user_id,
                "question_id": qid,
                "answer": log_ans,
                "is_correct": (q_score == q_max),
                "mode": "simulation",
                "session_id": session_id
            })
            
    # 2. Final calculations
    start_time = dm.dialog_data.get("start_time", time.time())
    end_time = dm.dialog_data.get("end_time", time.time())
    duration = int(end_time - start_time)
    
    from tgbot.misc.nmt_scoring import get_nmt_score
    nmt_val = get_nmt_score(subject, total_score, max_possible=total_max)
    nmt_score = nmt_val or 0
    nmt_text = f"<b>{nmt_score}</b>" if nmt_val else "Не склав (менше 100)"

    # 3. Store results for UI
    dm.dialog_data["final_raw_score"] = total_score
    dm.dialog_data["final_max_score"] = total_max
    dm.dialog_data["final_nmt_score"] = nmt_score
    dm.dialog_data["final_nmt_text"] = nmt_text
    dm.dialog_data["final_duration"] = duration
    
    # 4. Save to Database (ONLY IF AT LEAST 1 ANSWER)
    has_answers = (len(answers) > 0)
    
    if has_answers:
        await repo.results.save_result(
            user_id=user.user_id,
            subject=subject,
            year=dm.dialog_data.get("sim_year"),
            session_name=session_id,
            raw_score=total_score,
            nmt_score=nmt_score,
            duration=duration
        )
        if logs_to_save:
            await repo.logs.add_logs_batch(logs_to_save)
    else:
        # If no answers, we don't save result to DB.
        pass
    
    dm.dialog_data["results_saved"] = True
    await dm.switch_to(SimulationSG.summary)

async def get_summary_data(dialog_manager: DialogManager, **kwargs):
    repo: RequestsRepo = dialog_manager.middleware_data.get("repo")
    user: User = dialog_manager.middleware_data.get("user")
    answers = dialog_manager.dialog_data.get("answers", {})
    q_ids = dialog_manager.dialog_data.get("q_ids", [])
    subject = user.selected_subject
    
    # Use pre-calculated scores from on_finish
    score = dialog_manager.dialog_data.get("final_raw_score", 0)
    max_score = dialog_manager.dialog_data.get("final_max_score", 0)
    nmt_score = dialog_manager.dialog_data.get("final_nmt_score", 0)
    nmt_text_final = dialog_manager.dialog_data.get("final_nmt_text", "—")
    duration = dialog_manager.dialog_data.get("final_duration", 0)
    
    errors = []
    for idx, q_id_str in enumerate(q_ids):
        qid = int(q_id_str)
        user_ans = answers.get(str(qid))
        if not user_ans: continue
        
        question = await repo.questions.get_question_by_id(qid)
        correct = question.correct_answer
        
        # Check if error for display
        is_error = False
        if question.q_type == "choice":
            is_error = (str(user_ans).strip().upper() != str(correct.get("answer")).strip().upper())
        elif question.q_type == "short":
            u_str = str(user_ans).strip()
            c_str = str(correct.get("answer")).strip()
            basic_match = False
            try:
                if float(u_str.replace(",", ".")) == float(c_str.replace(",", ".")): basic_match = True
            except:
                if u_str == c_str: basic_match = True
            
            if not basic_match and subject in ["hist", "mova", "eng"]:
                if u_str.isdigit() and c_str.isdigit():
                    basic_match = (sorted(u_str) == sorted(c_str))
            
            is_error = not basic_match
        elif question.q_type == "match":
            target_pairs = correct.get("pairs", {})
            user_pairs = user_ans if isinstance(user_ans, dict) else {}
            is_error = any(target_pairs.get(str(k)) != str(v) for k, v in user_pairs.items()) or len(user_pairs) != len(target_pairs)

        if is_error:
            if question.q_type == "match":
                u_fmt = ", ".join([f"{k}-{v}" for k, v in sorted((user_ans or {}).items())])
                c_fmt = ", ".join([f"{k}-{v}" for k, v in sorted(correct.get("pairs", {}).items())])
            else:
                u_fmt = str(user_ans)
                c_fmt = str(correct.get("answer"))
            errors.append(f"<b>Питання {idx+1}:</b>\nВаша: <code>{u_fmt}</code>\nПравильна: <code>{c_fmt}</code>")

    errors_text = "\n\n".join(errors) if errors else "🎉 Вітаємо! Ви не допустили жодної помилки."
    
    # Previous Attempt Stats
    current_session = dialog_manager.dialog_data.get("sim_session")
    prev_result = await repo.results.get_last_session_result(user.user_id, subject, current_session)
    
    prev_stats_text = ""
    if prev_result:
        p_dur = prev_result.duration
        p_min = p_dur // 60
        p_sec = p_dur % 60
        prev_stats_text = (
             f"\n\n⏳ <b>Ти вже робив цю симуляцію!</b>\n"
             f"Минулий раз: <b>{prev_result.nmt_score}</b> балів за <b>{p_min} хв {p_sec} сек</b>."
        )

    return {
        "total_q": len(q_ids),
        "score": score,
        "max_score": max_score,
        "nmt_score": nmt_score,
        "nmt_text": nmt_text_final,
        "percent": int(score / max_score * 100) if max_score > 0 else 0,
        "time": f"{duration // 60} хв {duration % 60} сек",
        "prev_stats": prev_stats_text,
        "errors_text": errors_text
    }

async def get_review_data(dialog_manager: DialogManager, **kwargs):
    repo: RequestsRepo = dialog_manager.middleware_data.get("repo")
    user: User = dialog_manager.middleware_data.get("user")
    
    q_ids = dialog_manager.dialog_data.get("q_ids", [])
    if not q_ids: return {"has_questions": False}
    
    current_idx = dialog_manager.dialog_data.get("review_index", 0)
    current_id = q_ids[current_idx]
    
    question: Question = await repo.questions.get_question_by_id(current_id)
    dialog_manager.dialog_data["current_explanation"] = question.explanation  # For explanation handler
    
    is_album = bool(dialog_manager.dialog_data.get("album_message_ids"))
    
    image = None
    if not is_album:
        images = []
        if question.image_file_id:
            images.append(question.image_file_id)
        if question.images:
            for img in question.images:
                if img not in images:
                    images.append(img)
        if images:
            image = MediaAttachment(type=ContentType.PHOTO, file_id=MediaId(images[0]))
    
    # Get answers
    answers = dialog_manager.dialog_data.get("answers", {})
    user_ans = answers.get(str(current_id))
    correct = question.correct_answer

    # Format answers
    if question.q_type == "match":
        u_sorted = sorted((user_ans or {}).items())
        u_fmt = ", ".join([f"{k}-{v}" for k, v in u_sorted]) or "немає"
        c_fmt = ", ".join([f"{k}-{v}" for k, v in sorted(correct.get("pairs", {}).items())])
    else:
        u_fmt = str(user_ans or "немає")
        c_fmt = str(correct.get("answer"))

    # Determine Correctness Status
    # Re-using scoring logic essentially, or simplest string compare for display
    is_correct = False
    if question.q_type == "choice":
        is_correct = (str(user_ans).strip().upper() == str(correct.get("answer")).strip().upper()) if user_ans else False
    elif question.q_type == "short":
        u_str = str(user_ans).strip() if user_ans else ""
        c_str = str(correct.get("answer")).strip()
        try:
            is_correct = float(u_str.replace(",", ".")) == float(c_str.replace(",", "."))
        except:
            is_correct = (u_str == c_str) if u_str else False
            
        # Flexible digit matching for specific subjects
        if not is_correct and user.selected_subject in ["hist", "mova", "eng"]:
            if u_str.isdigit() and c_str.isdigit():
                is_correct = (sorted(u_str) == sorted(c_str))
    elif question.q_type == "match":
         # Partial not handled in simple boolean, but for icon we can show check if full correct
         target = correct.get("pairs", {})
         if isinstance(user_ans, dict) and len(user_ans) == len(target):
             is_correct = all(target.get(k) == v for k, v in user_ans.items())

    status_text = "✅ <b>Правильно!</b>" if is_correct else "❌ <b>Помилка</b>"

    show_explanation = dialog_manager.dialog_data.get("show_explanation", False)
    import html
    expl_text = html.escape(question.explanation or "") if show_explanation else ""

    return {
        "has_image": bool(image),
        "image": image,
        "counter": f"{current_idx + 1}/{len(q_ids)}",
        "user_fmt": u_fmt,
        "correct_fmt": c_fmt,
        "status_text": status_text,
        "has_explanation": bool(question.explanation),
        "show_explanation": show_explanation,
        "explanation_text": expl_text,
        "has_prev": current_idx > 0,
        "has_next": current_idx < len(q_ids) - 1
    }

async def update_review_view(dm: DialogManager, new_index: int):
    # 1. Cleanup Old Album
    bot = dm.middleware_data.get("bot")
    old_album_ids = dm.dialog_data.get("album_message_ids")
    
    if old_album_ids:
        chat_id = dm.middleware_data.get("event_chat").id
        await AlbumManager.cleanup_album(bot, chat_id, old_album_ids)
        dm.dialog_data["album_message_ids"] = []

    # 2. Setup New Question
    q_ids = dm.dialog_data.get("q_ids", [])
    if not q_ids:
        dm.dialog_data["review_index"] = 0
        return

    # Wrap index
    if new_index >= len(q_ids): new_index = 0
    if new_index < 0: new_index = len(q_ids) - 1
    
    dm.dialog_data["review_index"] = new_index
    # Reset expansion
    dm.dialog_data["show_explanation"] = False
    
    current_id = q_ids[new_index]
    repo: RequestsRepo = dm.middleware_data.get("repo")
    question = await repo.questions.get_question_by_id(current_id)
    
    # 3. Check for Album
    images = []
    if question.image_file_id:
        images.append(question.image_file_id)
    if question.images:
        for img in question.images:
            if img not in images:
                images.append(img)
        
    if len(images) > 1:
        chat_id = dm.middleware_data.get("event_chat").id
        
        # BUG FIX: Delete previous dialog message
        try:
             stack = dm.current_stack()
             if stack and stack.last_message_id:
                 await bot.delete_message(chat_id, stack.last_message_id)
        except Exception:
            pass

        album_ids = await AlbumManager.send_album(bot, chat_id, images, caption=None)
        dm.dialog_data["album_message_ids"] = album_ids
        dm.show_mode = ShowMode.SEND
    else:
        dm.show_mode = ShowMode.EDIT

async def on_review_next(c: Any, b: Button, dm: DialogManager):
    idx = dm.dialog_data.get("review_index", 0)
    await update_review_view(dm, idx + 1)

async def on_review_prev(c: Any, b: Button, dm: DialogManager):
    idx = dm.dialog_data.get("review_index", 0)
    await update_review_view(dm, idx - 1)

async def on_start_review(c: Any, b: Button, dm: DialogManager):
    await update_review_view(dm, 0)
    await dm.switch_to(SimulationSG.review)

async def on_show_materials(c: Any, b: Button, dm: DialogManager):
    current = dm.dialog_data.get("show_materials", False)
    dm.dialog_data["show_materials"] = not current
    
    # Refresh view with new image set
    curr_idx = dm.dialog_data.get("current_index", 0)
    await update_question_view(dm, curr_idx)

async def on_quit_review(c: Any, b: Button, dm: DialogManager):
    # Cleanup album
    bot = dm.middleware_data.get("bot")
    old_album_ids = dm.dialog_data.get("album_message_ids")
    if old_album_ids:
        chat_id = dm.middleware_data.get("event_chat").id
        await AlbumManager.cleanup_album(bot, chat_id, old_album_ids)
        dm.dialog_data["album_message_ids"] = []
    await dm.done()


async def on_show_explanation(c: Any, b: Button, dm: DialogManager):
    # Toggle explanation visibility
    current = dm.dialog_data.get("show_explanation", False)
    dm.dialog_data["show_explanation"] = not current

async def on_open_nav(c: Any, b: Button, dm: DialogManager):
    # Determine source mode (question or review)
    # We can check current state or just look at stack?
    state = dm.current_context().state
    if state == SimulationSG.question:
        dm.dialog_data["nav_mode"] = "question"
    elif state == SimulationSG.review:
        dm.dialog_data["nav_mode"] = "review"
        
    await dm.switch_to(SimulationSG.navigation)

async def on_nav_selected(c: Any, w: Any, dm: DialogManager, item_id: str):
    idx = int(item_id)
    mode = dm.dialog_data.get("nav_mode", "question")
    
    if mode == "question":
        await update_question_view(dm, idx)
        await dm.switch_to(SimulationSG.question)
    elif mode == "review":
        await update_review_view(dm, idx)
        await dm.switch_to(SimulationSG.review)

async def on_nav_back(c: Any, b: Button, dm: DialogManager):
    mode = dm.dialog_data.get("nav_mode", "question")
    if mode == "question":
        await dm.switch_to(SimulationSG.question)
    elif mode == "review":
        await dm.switch_to(SimulationSG.review)



# --- Dialog ---

simulation_dialog = Dialog(
    Window(
        Format("📚 <b>Обери рік НМТ для предмета {subject}:</b>"),
        Group(
            Select(Format("{item[0]}"), id="sim_y", item_id_getter=lambda x: x[1], items="years", on_click=on_year_selected),
            width=3
        ),
        Const("На жаль, для цього предмета ще немає завантажених питань.", when=~F["has_years"]),
        Cancel(Const("🔙 Назад")),
        state=SimulationSG.select_year,
        getter=get_sim_years,
    ),
    Window(
        Format("📚 <b>{subject} {year} рік: Обери сесію:</b>"),
        Column(
            Select(Format("{item[0]}"), id="sim_s", item_id_getter=lambda x: x[1], items="sessions", on_click=on_session_selected),
        ),
        Back(Const("🔙 До років")),
        state=SimulationSG.select_session,
        getter=get_sim_sessions,
    ),
    Window(
        DynamicMedia("question_image", when="has_image"),
        Format("Питання {counter}\nВідповідь: <b>{current_answer}</b>\n\n<i>{hint}</i>", when="has_questions"),
        Const("Питань немає.", when=~F["has_questions"]),
        
        Group(
            Select(Format("{item[0]}"), id="ans_choice", item_id_getter=lambda x: x[1], items="choice_variants", on_click=on_choice_selected),
            width=5, when=F["has_questions"] & (F["q_type"] == "choice")
        ),
        Row(
            Select(
                Format("·{item[0]}·" if F["active_num"] == F["item"][0] else "{item[0]}"),
                id="match_n", item_id_getter=lambda x: x[1], items="match_nums", on_click=on_match_num_selected
            ),
            when=F["has_questions"] & (F["q_type"] == "match") & ~F["active_num"]
        ),
        Row(
            Select(Format("{item[0]}"), id="match_l", item_id_getter=lambda x: x[1], items="match_letters", on_click=on_match_letter_selected),
            when=F["has_questions"] & (F["q_type"] == "match") & F["active_num"]
        ),
        Button(
            Format("{materials_label}"), 
            id="btn_materials", 
            on_click=on_show_materials, 
            when=F["has_questions"] & F["has_materials"] & ~F["answered"]
        ),
        
        MessageInput(on_answer_text, content_types=[ContentType.TEXT]),
        
        Row(
            Button(Const("⬅️"), id="prev", on_click=on_prev, when="has_questions"),
            Button(Format("{counter}"), id="count", on_click=on_open_nav, when="has_questions"), 
            Button(Const("➡️"), id="next", on_click=on_next, when="has_questions"),
        ),
        Button(Const("🏁 Завершити тест"), id="finish", on_click=on_finish, when="has_questions"),
        state=SimulationSG.question,
        getter=get_question_data,
    ),
    Window(
        Format("<b>🏁 Тест завершено!</b>\n\n"
               "Питань: <b>{total_q}</b>\n"
               "Ваш бал: <b>{score}</b> з <b>{max_score}</b>\n"
               "Бал НМТ: {nmt_text}\n"
               "Час: <b>{time}</b>\n"
               "{prev_stats}"),
        Button(Const("🔍 Переглянути відповіді"), id="review", on_click=on_start_review),
        Button(Const("🚀 В головне меню"), id="to_main", on_click=lambda c, b, d: d.done()),
        state=SimulationSG.summary,
        getter=get_summary_data,
    ),
    Window(
        DynamicMedia("image", when=F["has_image"] & ~F["show_explanation"]),
        Format("<b>Питання {counter}</b>\n{status_text}\n\n💡 <i>Ваша відповідь:</i> <b>{user_fmt}</b>\n✅ <i>Правильна:</i> <b>{correct_fmt}</b>"),
        
        # Inline Explanation
        Format("\n💡 <b>Пояснення:</b>\n{explanation_text}", when="show_explanation"),

        # Explanation Button
        Button(Const("💡 Показати пояснення"), id="expl_rev", on_click=on_show_explanation, when=F["has_explanation"] & ~F["show_explanation"]),
        Button(Const("🙈 Сховати пояснення"), id="expl_hide", on_click=on_show_explanation, when=F["show_explanation"]),
        
        Row(
            Button(Const("⬅️"), id="prev_rev", on_click=on_review_prev, when="has_prev"),
            Button(Format("{counter}"), id="cnt_rev", on_click=on_open_nav),
            Button(Const("➡️"), id="next_rev", on_click=on_review_next, when="has_next"),
        ),
        Button(Const("🔙 Назад до результатів"), id="rev_back", on_click=on_quit_review),
        state=SimulationSG.review,
        getter=get_review_data,
    ),
    Window(
        Format("🗺 <b>Навігація</b>\nВсього питань: {total}"),
        Group(
             Select(
                 Format("{item[0]}"), 
                 id="nav_grid", 
                 item_id_getter=lambda x: x[1], 
                 items="nav_items", 
                 on_click=on_nav_selected
             ),
             width=6
        ),
        Button(Const("🔙 Назад"), id="nav_back", on_click=on_nav_back),
        state=SimulationSG.navigation,
        getter=get_nav_data
    ),

)
