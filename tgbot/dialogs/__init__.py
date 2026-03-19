from .admin import admin_dialog  # now a package: tgbot/dialogs/admin/
from .main_menu import main_menu_dialog
from .simulation import simulation_dialog
from .random_mode import random_dialog
from .stats import stats_dialog
from .broadcasting import broadcast_dialog
from .subject_menu import subject_menu_dialog

__all__ = ["admin_dialog", "main_menu_dialog", "simulation_dialog", "random_dialog", "stats_dialog", "broadcast_dialog", "subject_menu_dialog"]
