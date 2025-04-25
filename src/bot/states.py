from aiogram.fsm.state import State, StatesGroup


class TeamCreation(StatesGroup):
    """States for team creation flow."""
    waiting_for_name = State()
    waiting_for_description = State()
    confirm_creation = State()


class TeamJoining(StatesGroup):
    """States for team joining flow."""
    waiting_for_code = State()


class QuestionFlow(StatesGroup):
    """States for question answering flow."""
    viewing_question = State()
    answering = State()
    creating_question = State()
    reviewing_question = State()
    choosing_correction = State()
    confirming_delete = State()


class MatchingStates(StatesGroup):
    finding_matches = State()
    waiting_for_chat_confirmation = State()


class GroupOnboarding(StatesGroup):
    """States for onboarding a user to a group (nickname, photo)."""
    waiting_for_nickname = State()
    waiting_for_photo = State()


class GroupFlow(StatesGroup):
    """States for group management flow."""
    creating_group = State()
    entering_name = State()
    entering_description = State()
    confirming_creation = State()
    # Group management states
    waiting_for_rename = State()
    waiting_for_description_edit = State()
