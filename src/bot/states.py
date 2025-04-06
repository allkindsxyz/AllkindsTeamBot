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