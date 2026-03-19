from __future__ import annotations

from typing import Any
from aiogram import F
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery, ContentType
from aiogram_dialog import Dialog, Window, DialogManager, StartMode
from aiogram_dialog.widgets.kbd import Button, Group, Select, Row, Back, Cancel, ScrollingGroup
from aiogram_dialog.widgets.text import Const, Format, Case, Multi
from aiogram_dialog.widgets.input import TextInput, MessageInput

from tgbot.misc.bakalavr_data import (
    VagCoefZno2026, RegionData, ALL_SUBJECT_NAMES, CHOOSABLE_SUBJECT_NAMES, BakalavrTestPointsData
)
from tgbot.misc.nmt_scoring import get_scaled_score, calculate_kb_2026, get_raw_score_equivalent
from infrastructure.database.models import User
from infrastructure.database.repo.requests import RequestsRepo

SUGGESTED_SPEC_CODES = ["C1", "C4", "D8", "F2", "F5", "F3", "F1", "E7", "G12"]

_INPUT_LABEL_MAP = {
    "btn_p1": ("ukr_mova",     "Укр. мови"),
    "btn_p2": ("ukr_history",  "Історії"),
    "btn_p3": ("math",         "Математики"),
}


def _build_k_vals(spec: dict | None, fourth_subj_id: str | None) -> dict[str, float]:
    """Returns the coefficient dict for a given spec. All values default to 0."""
    k = {"k1": 0.0, "k2": 0.0, "k3": 0.0, "k4": 0.0, "kt": 0.0, "k4max": 0.0}
    if not spec:
        return k
    k["k1"] = spec["main_block"].get("ukr_mova", 0)
    k["k2"] = spec["main_block"].get("ukr_history", 0)
    k["k3"] = spec["main_block"].get("math", 0)
    if fourth_subj_id:
        k["k4"] = spec["choosable_block"].get(fourth_subj_id, 0)
    k["k4max"] = max(spec["choosable_block"].values()) if spec["choosable_block"] else 0
    k["kt"] = spec.get("tvorchy_konkurs") or 0
    return k


def _build_input_hint(
    current_input: str,
    fourth_subj_id: str | None,
    fourth_subj_name: str,
) -> str:
    """Returns the contextual hint string shown in the score-input field."""
    if current_input == "btn_tk":
        return "Введіть бал за <b>Творчий конкурс</b> (100-200):"

    if current_input == "btn_p4":
        subj_id, display_name = fourth_subj_id, fourth_subj_name
    else:
        subj_id, display_name = _INPUT_LABEL_MAP.get(current_input, (None, ""))

    if subj_id:
        table = BakalavrTestPointsData.get(subj_id, {})
        if table:
            min_tb = min(table.keys(), key=int)
            max_tb = max(table.keys(), key=int)
            return (
                f"Введіть бал з <b>{display_name}</b>:\n"
                f"📥 Тестовий бал ({min_tb}-{max_tb}) АБО\n"
                f"📈 Рейтинговий бал (100-200):"
            )
    return "Введіть бал:"


class CalculatorSG(StatesGroup):
    main = State()
    search_spec = State()
    select_fourth_subject = State()
    input_points = State()
    select_region = State()
    ask_kse = State()

def is_budget_eligible(kb: float, spec_code: str) -> bool:
    # 150+ rule for specific specialties
    high_threshold_specs = ["C1", "C3", "D4", "D8", "D9", "I1", "I2", "I3", "I4", "I8"]
    if any(spec_code.startswith(prefix) for prefix in high_threshold_specs):
        return kb >= 150.0
    return kb >= 130.0

async def get_calculator_data(dialog_manager: DialogManager, **kwargs) -> dict:
    user: User = dialog_manager.middleware_data.get("user")
    data = user.settings.get("calc", {})

    spec_code = data.get("spec_code")
    spec = next((s for s in VagCoefZno2026 if s["code"] == spec_code), None)
    region_id = data.get("region_id", 27)
    region = next((r for r in RegionData if r["id"] == region_id), RegionData[0])
    courses_active = data.get("courses_active", False)
    scores = data.get("scores", {"ukr_mova": 0, "ukr_history": 0, "math": 0, "fourth_subj": 0, "tvorch": 0})

    fourth_subj_id = data.get("fourth_subj_id")
    fourth_subj_name = CHOOSABLE_SUBJECT_NAMES.get(fourth_subj_id, "Предмет")
    k_vals = _build_k_vals(spec, fourth_subj_id)

    ratings = {
        "ukr_mova":    get_scaled_score("ukr_mova",    scores.get("ukr_mova", 0)),
        "ukr_history": get_scaled_score("ukr_history", scores.get("ukr_history", 0)),
        "math":        get_scaled_score("math",        scores.get("math", 0)),
        "fourth_subj": get_scaled_score(fourth_subj_id, scores.get("fourth_subj", 0)) if fourth_subj_id else 0,
        "tvorch":      float(scores.get("tvorch", 0)),
    }

    final_kb = 0.0
    gk = 1.0
    budget_status = "❌"
    if spec:
        gk = 1.02 if spec.get("osoblyva_pidtrymka") == 1 else 1.0
        ou = 15.0 if spec.get("osoblyva_pidtrymka") == 1 and courses_active else 0.0
        final_kb = calculate_kb_2026(
            p1=ratings["ukr_mova"], k1=k_vals["k1"],
            p2=ratings["ukr_history"], k2=k_vals["k2"],
            p3=ratings["math"], k3=k_vals["k3"],
            p4=ratings["fourth_subj"], k4=k_vals["k4"],
            k4max=k_vals["k4max"],
            tk=ratings["tvorch"], kt=k_vals["kt"],
            ou=ou, rk=region["coef"], gk=gk,
        )
        budget_status = "✅" if is_budget_eligible(final_kb, spec_code) else "❌"

    current_input = dialog_manager.dialog_data.get("current_input", "")
    hint = _build_input_hint(current_input, fourth_subj_id, fourth_subj_name)

    min_thresholds = {
        "ukr_mova":    min(BakalavrTestPointsData["ukr_mova"].keys(), key=int),
        "ukr_history": min(BakalavrTestPointsData["ukr_history"].keys(), key=int),
        "math":        min(BakalavrTestPointsData["math"].keys(), key=int),
        "fourth_subj": min(BakalavrTestPointsData.get(fourth_subj_id, {"0": 0}).keys(), key=int) if fourth_subj_id else 0,
    }

    denom = k_vals["k1"] + k_vals["k2"] + k_vals["k3"] + (k_vals["k4max"] + k_vals["k4"]) / 2 + k_vals["kt"]
    formula = (
        f"<code>({k_vals['k1']}*{ratings['ukr_mova']} + {k_vals['k2']}*{ratings['ukr_history']} + "
        f"{k_vals['k3']}*{ratings['math']} + {k_vals['k4']}*{ratings['fourth_subj']} + "
        f"{k_vals['kt']}*{ratings['tvorch']})/{denom:.1f} * {region['coef']} * {gk} = {final_kb:.3f}</code>"
    ) if spec else ""

    return {
        "spec_name":       spec["name"] if spec else "❌ Не обрано",
        "region_name":     region["region"],
        "rk":              region["coef"],
        "p1_tb": scores.get("ukr_mova", 0),    "p1_rating": ratings["ukr_mova"],    "k1": k_vals["k1"], "p1_min": min_thresholds["ukr_mova"],
        "p2_tb": scores.get("ukr_history", 0), "p2_rating": ratings["ukr_history"], "k2": k_vals["k2"], "p2_min": min_thresholds["ukr_history"],
        "p3_tb": scores.get("math", 0),        "p3_rating": ratings["math"],        "k3": k_vals["k3"], "p3_min": min_thresholds["math"],
        "fourth_subj_name": fourth_subj_name,
        "p4_tb": scores.get("fourth_subj", 0), "p4_rating": ratings["fourth_subj"], "k4": k_vals["k4"], "p4_min": min_thresholds["fourth_subj"],
        "has_tk":     k_vals["kt"] > 0,
        "tk_points":  scores.get("tvorch", 0), "kt": k_vals["kt"],
        "ou_status":  "✅" if courses_active else "❌",
        "ou_allowed": spec.get("osoblyva_pidtrymka") == 1 if spec else False,
        "final_kb":   f"{final_kb:.3f}",
        "budget_status": budget_status,
        "input_hint": hint,
        "show_kse_link": final_kb > 0,
        "formula":    formula,
        "is_kse_spec": spec_code in SUGGESTED_SPEC_CODES,
    }

async def save_calc_data(dialog_manager: DialogManager, update_dict: dict) -> None:
    repo: RequestsRepo = dialog_manager.middleware_data.get("repo")
    user: User = dialog_manager.middleware_data.get("user")
    
    if "calc" not in user.settings:
        user.settings["calc"] = {}
    
    user.settings["calc"].update(update_dict)
    await repo.users.update_user_settings(user.user_id, user.settings)

async def on_spec_selected(callback: CallbackQuery, widget: Any, dialog_manager: DialogManager, item_id: str) -> None:
    await save_calc_data(dialog_manager, {"spec_code": item_id})
    await dialog_manager.switch_to(CalculatorSG.main)

async def on_region_selected(callback: CallbackQuery, widget: Any, dialog_manager: DialogManager, item_id: str) -> None:
    await save_calc_data(dialog_manager, {"region_id": int(item_id)})
    await dialog_manager.switch_to(CalculatorSG.main)

async def on_courses_toggle(callback: CallbackQuery, button: Button, dialog_manager: DialogManager) -> None:
    user: User = dialog_manager.middleware_data.get("user")
    current = user.settings.get("calc", {}).get("courses_active", False)
    await save_calc_data(dialog_manager, {"courses_active": not current})

async def on_reset(callback: CallbackQuery, button: Button, dialog_manager: DialogManager) -> None:
    repo: RequestsRepo = dialog_manager.middleware_data.get("repo")
    user: User = dialog_manager.middleware_data.get("user")
    user.settings["calc"] = {}
    await repo.users.update_user_settings(user.user_id, user.settings)
    await callback.answer("Дані скинуто")

async def on_input_points(callback: CallbackQuery, button: Button, dialog_manager: DialogManager) -> None:
    dialog_manager.dialog_data["current_input"] = button.widget_id
    await dialog_manager.switch_to(CalculatorSG.input_points)

async def on_points_entered(message: Message, widget: Any, dialog_manager: DialogManager) -> None:
    user: User = dialog_manager.middleware_data.get("user")
    field = dialog_manager.dialog_data.get("current_input")
    if not field:
        await dialog_manager.switch_to(CalculatorSG.main)
        return

    try:
        val_str = message.text.replace(",", ".")
        val = float(val_str) if field == "btn_tk" else int(message.text)
        
        # Strict validation
        subj_id = None
        if field in ["btn_p1", "btn_p2", "btn_p3", "btn_p4"]:
             subj_id = "fourth_subj" if field == "btn_p4" else {
                "btn_p1": "ukr_mova", "btn_p2": "ukr_history", "btn_p3": "math"
            }[field]
             if field == "btn_p4":
                 calc_data = user.settings.get("calc", {})
                 subj_id = calc_data.get("fourth_subj_id")
        
        if subj_id:
            table = BakalavrTestPointsData.get(subj_id, {})
            if table:
                min_tb = int(min(table.keys(), key=int))
                max_tb = int(max(table.keys(), key=int))
                
                # If user entered a scaled score (100-200), convert it to raw
                if 100 <= val <= 200:
                    val = get_raw_score_equivalent(subj_id, int(val))
                    # Note: val is now a TB
                
                if 0 < val < min_tb:
                    await message.answer(f"⚠️ Цей бал ({val}) нижче порогу ({min_tb} ТБ). Встановлено 0 балів (не склав).")
                    val = 0
                elif not (val == 0 or (min_tb <= val <= max_tb)):
                    await message.answer(f"❌ Невірний бал. Введіть тестовий бал ({min_tb}-{max_tb}) або рейтинговий (100-200).")
                    return
        elif field == "btn_tk":
            if not (100 <= val <= 200):
                await message.answer("❌ Введіть бал творчого конкурсу від 100 до 200.")
                return
        else:
            if not (0 <= val <= 200):
                raise ValueError

        calc_data = user.settings.get("calc", {})
        if "scores" not in calc_data:
            calc_data["scores"] = {"ukr_mova": 0, "ukr_history": 0, "math": 0, "fourth_subj": 0, "tvorch": 0}
        
        mapping = {"btn_p1": "ukr_mova", "btn_p2": "ukr_history", "btn_p3": "math", "btn_p4": "fourth_subj", "btn_tk": "tvorch"}
        score_key = mapping.get(field)
        if score_key:
            calc_data["scores"][score_key] = val
        
        await save_calc_data(dialog_manager, {"scores": calc_data["scores"]})
        await message.delete()
        await dialog_manager.switch_to(CalculatorSG.main)
    except ValueError:
        await message.answer("Введіть коректне число.")

async def on_spec_search(message: Message, widget: Any, dialog_manager: DialogManager) -> None:
    dialog_manager.dialog_data["search_query"] = message.text
    await message.delete()

async def get_search_results(dialog_manager: DialogManager, **kwargs) -> dict:
    query = dialog_manager.dialog_data.get("search_query", "").lower()
    if not query:
        # Show suggested specialties by default
        results = [
            {"name": s["name"], "code": s["code"]}
            for s in VagCoefZno2026
            if s["code"] in SUGGESTED_SPEC_CODES
        ]
        return {"specs": results}
    
    results = [
        {"name": s["name"], "code": s["code"]}
        for s in VagCoefZno2026
        if query in s["name"].lower() or query in s["code"].lower()
    ]
    return {"specs": results[:20]}

async def on_fourth_subj_selected(callback: CallbackQuery, widget: Any, dialog_manager: DialogManager, item_id: str) -> None:
    await save_calc_data(dialog_manager, {"fourth_subj_id": item_id})
    await dialog_manager.switch_to(CalculatorSG.main)

async def on_region_btn_click(callback: CallbackQuery, button: Button, dialog_manager: DialogManager) -> None:
    await dialog_manager.switch_to(CalculatorSG.select_region)

async def on_search_btn_click(callback: CallbackQuery, button: Button, dialog_manager: DialogManager) -> None:
    await dialog_manager.switch_to(CalculatorSG.search_spec)

async def on_fourth_subject_btn_click(callback: CallbackQuery, button: Button, dialog_manager: DialogManager) -> None:
    await dialog_manager.switch_to(CalculatorSG.select_fourth_subject)

async def on_back_to_main(callback: CallbackQuery, button: Button, dialog_manager: DialogManager) -> None:
    await dialog_manager.switch_to(CalculatorSG.main)

async def on_ask_kse_btn_click(callback: CallbackQuery, button: Button, dialog_manager: DialogManager) -> None:
    await dialog_manager.switch_to(CalculatorSG.ask_kse)

async def on_kse_question_sent(message: Message, widget: Any, dialog_manager: DialogManager) -> None:
    user: User = dialog_manager.middleware_data.get("user")
    repo: RequestsRepo = dialog_manager.middleware_data.get("repo")
    config = dialog_manager.middleware_data.get("config")
    bot = message.bot
    
    # Get current calculator data for context
    calc_data = await get_calculator_data(dialog_manager)
    
    # Get user stats for more context
    stats = await repo.results.get_user_stats(user.user_id)
    
    subj_stats_lines = []
    for s in stats.get("subject_stats", []):
        subj_stats_lines.append(f"   • {s['subject']}: {s['avg']} (Прогноз: {s['median']})")
    
    # Format duration
    avg_dur = stats.get("avg_duration", 0)
    minutes = avg_dur // 60
    seconds = avg_dur % 60
    duration_text = f"{minutes:02d}:{seconds:02d}"

    stats_info = (
        f"📊 <b>Статистика симуляцій:</b>\n"
        f"📝 Всього спроб: {stats['total_sims']}\n"
        f"✅ Правильних: {stats['sim_correct']} (сим), {stats['rand_correct']} (ранд)\n"
        f"⏱ Середній час тесту: {duration_text}\n"
        + ("\n".join(subj_stats_lines) if subj_stats_lines else "<i>(даних по предметах немає)</i>")
    )
    
    context_info = (
        f"🙋‍♀️ <b>Нове питання по KSE!</b>\n"
        f"👤 Користувач: {user.full_name}\n"
        f"🔗 Тег: @{user.username if user.username else 'відсутній'}\n"
        f"🆔 ID: <code>{user.user_id}</code>\n\n"
        f"💬 <b>Питання:</b>\n{message.text or message.caption or '<i>(тільки фото)</i>'}\n\n"
        f"🧮 <b>Дані калькулятора:</b>\n"
        f"🎓 Спеціальність: {calc_data['spec_name']}\n"
        f"📍 Регіон: {calc_data['region_name']}\n"
        f"🔥 КБ: {calc_data['final_kb']}\n"
        f"🏛 Бюджет: {calc_data['budget_status']}\n\n"
        f"{stats_info}"
    )
    
    for admin_id in config.tg_bot.admin_ids:
        try:
            if message.photo:
                await bot.send_photo(
                    chat_id=admin_id,
                    photo=message.photo[-1].file_id,
                    caption=context_info[:1024]
                )
            else:
                await bot.send_message(
                    chat_id=admin_id,
                    text=context_info
                )
        except Exception:
            logger.warning(f"Failed to notify admin {admin_id} about KSE question", exc_info=True)

    await message.answer("✅ Дякуємо! Ваше питання надіслано координаторці KSE. Очікуйте на відповідь!")
    await dialog_manager.switch_to(CalculatorSG.main)

async def get_subjects_data(dialog_manager: DialogManager, **kwargs) -> dict:
    return {"subjects": [{"id": k, "name": v} for k, v in CHOOSABLE_SUBJECT_NAMES.items()]}

async def get_regions_data(dialog_manager: DialogManager, **kwargs) -> dict:
    return {"regions": RegionData}

calculator_dialog = Dialog(
    Window(
        Multi(
            Const("🧮 <b>Калькулятор вступу 2026</b>\n"),
            Format("🎓 <b>Спеціальність:</b> {spec_name}"),
            Format("📍 <b>Регіон:</b> {region_name} (к: {rk})"),
            Const("\n📥 <b>Введіть свої бали:</b>"),
            Format("‣ Укр. мова: <b>{p1_tb}</b> → <b>{p1_rating}</b>"),
            Format("‣ Історія: <b>{p2_tb}</b> → <b>{p2_rating}</b>"),
            Format("‣ Математика: <b>{p3_tb}</b> → <b>{p3_rating}</b>"),
            Format("‣ {fourth_subj_name}: <b>{p4_tb}</b> → <b>{p4_rating}</b>"),
            Case({True: Format("‣ Творчий: <b>{tk_points}</b>"), False: Const("")}, selector="has_tk"),
            
            Const("\n🏆 <b>Ваш Конкурсний Бал (КБ):</b>"),
            Format("🔥 <b>{final_kb}</b>"),
            Format("🏛 <b>Бюджет: {budget_status}</b>"),
            
            Case({
                True: Multi(
                    Format("\n🧮 <b>Повний розрахунок:</b>\n{formula}"),
                    Const('\n<a href="https://university.kse.ua/bakalavrat">Ці можливості, мабуть, не для тебе... 🎓</a>'),
                ),
                False: Const("")
            }, selector="show_kse_link"),
            
            Const("\nℹ️ <b>Шпаргалка:</b>"),
            Const("• <b>ТБ (Тестовий бал)</b> — бали за правильні відповіді."),
            Const("• <b>КБ (Конкурсний бал)</b> — твій підсумковий бал для рейтингу."),
            sep="\n"
        ),
        Group(
            Row(
                Button(Const("🔎 Пошук спеціальності"), id="btn_search", on_click=on_search_btn_click),
                Button(Format("⚡ 4-й предмет"), id="btn_choose_p4", on_click=on_fourth_subject_btn_click),
            ),
            Row(
                Button(Const("📝 Укр"), id="btn_p1", on_click=on_input_points),
                Button(Const("📜 Іст"), id="btn_p2", on_click=on_input_points),
                Button(Const("📐 Мат"), id="btn_p3", on_click=on_input_points),
                Button(Const("🚀 4-й"), id="btn_p4", on_click=on_input_points),
            ),
            Row(
                Button(Const("📍 Регіон"), id="btn_region", on_click=on_region_btn_click),
                Button(Format("🎓 Курси: {ou_status}"), id="btn_ou", on_click=on_courses_toggle, when="ou_allowed"),
            ),
            Button(Const("🎨 Творчий конкурс"), id="btn_tk", on_click=on_input_points, when="has_tk"),
            Button(Const("🙋‍♀️ Поставити питання KSE"), id="btn_ask_kse", on_click=on_ask_kse_btn_click),
            Row(
                Button(Const("🔄 Скинути"), id="btn_reset", on_click=on_reset),
                Cancel(Const("❌ Вихід")),
            ),
        ),
        state=CalculatorSG.main,
        getter=get_calculator_data,
    ),
    Window(
        Const("🔍 <b>Пошук спеціальності</b>\nВведіть код або назву:"),
        MessageInput(on_spec_search),
        ScrollingGroup(
            Select(Format("{item[code]} {item[name]}"), id="s_spec", item_id_getter=lambda x: x["code"], items="specs", on_click=on_spec_selected),
            id="spec_scroll", width=1, height=8
        ),
        Button(Const("⬅️ Назад"), id="btn_back_spec", on_click=on_back_to_main),
        state=CalculatorSG.search_spec,
        getter=get_search_results,
    ),
    Window(
        Const("⚡ <b>Обери 4-й предмет:</b>"),
        Group(
            Select(Format("{item[name]}"), id="s_fourth", item_id_getter=lambda x: x["id"], items="subjects", on_click=on_fourth_subj_selected),
            width=2
        ),
        Button(Const("⬅️ Назад"), id="btn_back_fourth", on_click=on_back_to_main),
        state=CalculatorSG.select_fourth_subject,
        getter=get_subjects_data,
    ),
    Window(
        Const("📍 <b>Обери регіон вступу:</b>"),
        ScrollingGroup(
            Select(Format("{item[region]} (к: {item[coef]})"), id="s_region", item_id_getter=lambda x: str(x["id"]), items="regions", on_click=on_region_selected),
            id="reg_scroll", width=1, height=10
        ),
        Button(Const("⬅️ Назад"), id="btn_back_region", on_click=on_back_to_main),
        state=CalculatorSG.select_region,
        getter=get_regions_data,
    ),
    Window(
        Format("⌨️ {input_hint}"),
        MessageInput(on_points_entered),
        Button(Const("⬅️ Назад"), id="btn_back_points", on_click=on_back_to_main),
        state=CalculatorSG.input_points,
        getter=get_calculator_data
    ),
    Window(
        Const("🙋‍♀️ <b>Є питання щодо вступу в KSE?</b>\n\n"
              "Напишіть його нижче. Ми передамо ваше запитання координаторці KSE, і вона зв'яжеться з вами!"),
        MessageInput(on_kse_question_sent, content_types=[ContentType.TEXT, ContentType.PHOTO]),
        Button(Const("⬅️ Назад"), id="btn_back_kse", on_click=on_back_to_main),
        state=CalculatorSG.ask_kse,
        getter=get_calculator_data
    )
)
