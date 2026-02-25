"""游戏核心逻辑"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from astrbot.api import sp, logger
from .models import BlackjackStats


# ========================================================================
# 🦾 核心逻辑与类型
# ========================================================================


class GamePhase(Enum):
    """游戏阶段"""

    IDLE = "idle"
    JOINING = "joining"
    DISTRIBUTING = "distributing"
    INSURANCE = "insurance"
    SURRENDER = "surrender"
    PLAYER_TURN = "player_turn"
    DEALER_TURN = "dealer_turn"
    SETTLEMENT = "settlement"
    ENDED = "ended"


@dataclass
class HandState:
    """手牌状态"""

    cards: list[str] = field(default_factory=list)
    bet: float = 0.0
    is_finished: bool = False
    is_doubled: bool = False
    is_surrendered: bool = False
    insurance: float = 0.0
    from_split: bool = False


@dataclass
class PlayerState:
    """玩家状态"""

    user_id: str
    username: str
    platform: str
    bet: float
    hands: list[HandState] = field(default_factory=list)
    current_hand_index: int = 0
    is_busy: bool = False


# 牌堆模板
CARDS_TEMPLATE = [
    "♥️A",
    "♥️2",
    "♥️3",
    "♥️4",
    "♥️5",
    "♥️6",
    "♥️7",
    "♥️8",
    "♥️9",
    "♥️10",
    "♥️J",
    "♥️Q",
    "♥️K",
    "♦️A",
    "♦️2",
    "♦️3",
    "♦️4",
    "♦️5",
    "♦️6",
    "♦️7",
    "♦️8",
    "♦️9",
    "♦️10",
    "♦️J",
    "♦️Q",
    "♦️K",
    "♣️A",
    "♣️2",
    "♣️3",
    "♣️4",
    "♣️5",
    "♣️6",
    "♣️7",
    "♣️8",
    "♣️9",
    "♣️10",
    "♣️J",
    "♣️Q",
    "♣️K",
    "♠️A",
    "♠️2",
    "♠️3",
    "♠️4",
    "♠️5",
    "♠️6",
    "♠️7",
    "♠️8",
    "♠️9",
    "♠️10",
    "♠️J",
    "♠️Q",
    "♠️K",
]


def calc_score(hand: list[str]) -> int:
    """计算点数"""
    total = 0
    aces = 0
    for card in hand:
        val_str = card[-1] if len(card) > 1 else "0"
        if val_str in ["J", "Q", "K", "0"]:  # 10 用 0 表示
            total += 10
        elif val_str == "A":
            total += 11
            aces += 1
        elif val_str.isdigit():
            total += int(val_str)
        else:
            # 处理两位数如 10
            if card[-2:].isdigit():
                total += int(card[-2:])

    # A 的动态调整
    while total > 21 and aces > 0:
        total -= 10
        aces -= 1
    return total


def is_blackjack(hand: HandState) -> bool:
    """只有初始两张牌且非分牌产生的21点才是 Blackjack"""
    if hand.from_split:
        return False
    return len(hand.cards) == 2 and calc_score(hand.cards) == 21


def get_card_rank(card: str) -> str:
    """获取牌面值"""
    if len(card) >= 2:
        return card[-1]
    return ""


def get_card_value(card: str) -> int:
    """获取牌数值"""
    rank = get_card_rank(card)
    if rank in ["J", "Q", "K", "0"]:
        return 10
    if rank == "A":
        return 11
    return int(rank) if rank.isdigit() else 0


# ========================================================================
# 💰 货币与统计
# ========================================================================


async def charge(user_id: str, amount: float) -> bool:
    """扣款（简化实现，使用虚拟货币）"""
    key = f"blackjack_balance_{user_id}"
    balance = await sp.global_get(key, 1000.0)  # 默认初始1000
    if balance < amount:
        return False
    await sp.global_put(key, balance - amount)
    return True


async def payout(user_id: str, amount: float):
    """赔付"""
    if amount <= 0:
        return
    key = f"blackjack_balance_{user_id}"
    balance = await sp.global_get(key, 0.0)
    await sp.global_put(key, balance + amount)


async def record_stat(user_id: str, username: str, profit: float):
    """记录统计"""
    key = f"blackjack_stats_{user_id}"
    data = await sp.global_get(key, None)
    if data:
        stat = BlackjackStats.from_dict(data)
    else:
        stat = BlackjackStats(user_id=user_id, username=username)

    stat.total_profit += profit
    if profit > 0:
        stat.wins += 1
    elif profit < 0:
        stat.loses += 1
    else:
        stat.draws += 1

    await sp.global_put(key, stat.to_dict())
    return


async def broadcast(msg: str):
    """广播消息（这里简化处理，实际需要通过 AstrBot 的消息系统）"""
    logger.info(f"[Blackjack] {msg}")
