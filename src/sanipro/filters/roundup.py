import logging

from sanipro import utils
from sanipro.abc import MutablePrompt, Prompt
from sanipro.filters.abc import Command

logger = logging.getLogger(__name__)


class RoundUpCommand(Command):
    def __init__(self, digits: int):
        self.digits = digits

    def execute(self, prompt: Prompt) -> MutablePrompt:
        return [utils.round_token_weight(token, self.digits) for token in prompt]
