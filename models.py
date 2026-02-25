"""数据模型定义"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BlackjackConfig:
    """21点游戏配置"""

    min_bet: int = 10
    deck_count: int = 4
    player_turn_timeout: int = 30
    join_phase_timeout: int = 45


@dataclass
class BlackjackStats:
    """玩家统计数据"""

    user_id: str
    username: str
    wins: int = 0
    loses: int = 0
    draws: int = 0
    bj_count: int = 0
    total_profit: float = 0.0

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "user_id": self.user_id,
            "username": self.username,
            "wins": self.wins,
            "loses": self.loses,
            "draws": self.draws,
            "bj_count": self.bj_count,
            "total_profit": self.total_profit,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BlackjackStats":
        """从字典创建"""
        return cls(
            user_id=data.get("user_id", ""),
            username=data.get("username", ""),
            wins=data.get("wins", 0),
            loses=data.get("loses", 0),
            draws=data.get("draws", 0),
            bj_count=data.get("bj_count", 0),
            total_profit=data.get("total_profit", 0.0),
        )
