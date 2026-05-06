"""Agent基类"""
from abc import ABC, abstractmethod


class BaseAgent(ABC):
    def __init__(self, agent_id, role, name=None):
        self.id = agent_id
        self.role = role
        self.name = name or f"Player{agent_id}"
        self.alive = True

    @abstractmethod
    def speak(self, game_state): pass

    @abstractmethod
    def vote(self, game_state): pass

    @abstractmethod
    def night_action(self, game_state, **kwargs): pass