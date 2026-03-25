import logging
from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.filters.command import CommandObject
from aiogram.types import Message, ReplyKeyboardRemove, CallbackQuery
from aiogram_dialog import DialogManager, StartMode, ShowMode

from infrastructure.database.models import User
from infrastructure.database.repo.requests import RequestsRepo
from tgbot.dialogs.main_menu import MainSG

logger = logging.getLogger(__name__)
user_router = Router()


@user_router.message(CommandStart())
async def user_start(
    message: Message,
    command: CommandObject,
    dialog_manager: DialogManager,
    user: User,
    repo: RequestsRepo,
) -> None:
    # Handle /start in a specific topic
    if message.message_thread_id:
        topic_ids = user.settings.get("topic_ids", {})
        # middleware SHOULD have set selected_subject already, but let's be safe
        subject = None
        for s, tid in topic_ids.items():
            if tid == message.message_thread_id:
                subject = s
                break
        
        if subject:
            from tgbot.dialogs.subject_menu import SubjectMenuSG
            user.selected_subject = subject # Update in-memory for this request
            await dialog_manager.start(SubjectMenuSG.menu, mode=StartMode.RESET_STACK, show_mode=ShowMode.SEND)
            return

    # Track referral join for new users (/start <code>)
    is_new_user = user.settings == {}
    if is_new_user and command.args:
        try:
            ref_link = await repo.referrals.get_by_code(command.args)
            if ref_link and ref_link.is_active:
                await repo.stats.add_join_stat(user.user_id, f"ref_{command.args}")
        except Exception:
            logger.warning("Failed to record referral join", exc_info=True)

    # Check if really new for onboarding
    if user.settings == {}:
        onboarding_video = await repo.settings.get_setting("onboarding_video")
        if not onboarding_video:
            config = dialog_manager.middleware_data.get("config")
            onboarding_video = config.misc.onboarding_video

        if onboarding_video:
            try:
                await message.answer_video(
                    video=onboarding_video,
                    caption="🕹️ Глянь коротке відео про те, як використати бота на 100%!"
                )
            except Exception:
                logger.warning("Failed to send onboarding video on /start", exc_info=True)

    # Remove any existing reply keyboard silently
    tmp_msg = await message.answer("...", reply_markup=ReplyKeyboardRemove())
    await tmp_msg.delete()

    # Topic Creation / Renaming Logic
    from tgbot.services.topic_manager import TopicManager
    await TopicManager.ensure_topics(message.bot, user, repo, dialog_manager, rename_if_exists=True)

    # Use StartMode.RESET_STACK to prevent stacking infinite dialogs
    await dialog_manager.start(MainSG.menu, mode=StartMode.RESET_STACK)

@user_router.message(F.message_thread_id)
async def handle_topic_messages(message: Message, dialog_manager: DialogManager, user: User) -> None:
    """
    Fallback handler for any message in a subject topic.
    If no dialog is active, it starts the SubjectMenuSG.
    """
    topic_ids = user.settings.get("topic_ids", {})
    subject = None
    for s, tid in topic_ids.items():
        if tid == message.message_thread_id:
            subject = s
            break
    
    if subject:
        from tgbot.dialogs.subject_menu import SubjectMenuSG
        # Show mode SEND because we want to push the menu to the user
        await dialog_manager.start(SubjectMenuSG.menu, mode=StartMode.RESET_STACK, show_mode=ShowMode.SEND)

@user_router.message(Command("help"))
async def user_help(message: Message, dialog_manager: DialogManager, repo: RequestsRepo) -> None:
    onboarding_video = await repo.settings.get_setting("onboarding_video")
    if not onboarding_video:
        config = dialog_manager.middleware_data.get("config")
        onboarding_video = config.misc.onboarding_video

    if onboarding_video:
        try:
            await message.answer_video(
                video=onboarding_video,
                caption="🕹️ Глянь коротке відео про те, як використати бота на 100%!"
            )
            return
        except Exception:
            logger.warning("Failed to send onboarding video on /help", exc_info=True)
            
    await message.answer(
        "👋 <b>Привіт! Це NMT Bot.</b>\n\n"
        "Я допоможу тобі підготуватися до НМТ з історії, математики, української та англійської мов.\n"
        "Обери предмет у головному меню та практикуйся у режимах Рандом або Симуляція!\n\n"
        "Якщо виникли питання, пиши сюди: @support_username" # Placeholder
    )

@user_router.message(~F.message_thread_id)
async def handle_general_messages(message: Message, dialog_manager: DialogManager, user: User, repo: RequestsRepo) -> None:
    """
    Catch-all for messages in the general chat.
    Ensures topics exist (via middleware) and then shows main menu.
    """
    await dialog_manager.start(MainSG.menu, mode=StartMode.RESET_STACK)

@user_router.callback_query(F.data == "start_menu")
async def on_click_start_menu(callback: CallbackQuery, dialog_manager: DialogManager, repo: RequestsRepo) -> None:
    # Removed delete() to keep welcome message as per request
    
    # Check DB for onboarding video first
    onboarding_video = await repo.settings.get_setting("onboarding_video")
    
    # Fallback to config if not set in DB
    if not onboarding_video:
        config = dialog_manager.middleware_data.get("config")
        onboarding_video = config.misc.onboarding_video

    if onboarding_video:
        try:
            await callback.bot.send_video(
                chat_id=callback.from_user.id,
                video=onboarding_video,
                caption="🕹️ Глянь коротке відео про те, як використати бота на 100%!"
            )
        except Exception:
            logger.warning("Failed to send onboarding video in start_menu callback", exc_info=True)

    try:
        await dialog_manager.start(MainSG.menu, mode=StartMode.RESET_STACK, show_mode=ShowMode.SEND)
    except Exception:
        logger.warning("Failed to start main menu dialog", exc_info=True)
        
    await callback.answer()
