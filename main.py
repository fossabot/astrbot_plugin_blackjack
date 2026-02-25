"""21点游戏插件主文件"""

from __future__ import annotations

import re
from typing import Optional

from astrbot.api import sp
from astrbot.api.event import AstrMessageEvent, MessageEventResult, MessageChain
from astrbot.api.event.filter import command
from astrbot.api.star import Star

from .game_logic import GamePhase
from .game_session import GameSession
from .models import BlackjackConfig, BlackjackStats

# ========================================================================
# 🚀 插件主类
# ========================================================================


class BlackjackStar(Star):
    """21点游戏插件"""

    author: str = "祁筱欣"
    name: str = "astrbot_plugin_blackjack"
    desc: str = "21点游戏 - 支持PVE和PVP模式，可加倍、分牌、投降、保险"

    def __init__(self, context, config: dict | None = None) -> None:
        super().__init__(context, config)
        self.games: dict[str, GameSession] = {}
        self.config = BlackjackConfig(**(config or {}))

    async def get_session(self, channel_id: str) -> GameSession | None:
        """获取当前会话"""
        return self.games.get(channel_id)

    async def handle_message(self, event: AstrMessageEvent, message: str):
        """处理游戏中的消息"""
        game = await self.get_session(event.session_id)
        if not game or game.phase in [GamePhase.IDLE, GamePhase.ENDED]:
            return

        msg = message.lower()
        user_id = event.session_id
        username = event.get_sender_name() or user_id

        # 加入阶段
        if game.phase == GamePhase.JOINING:
            if msg.startswith("下注") or msg.startswith("bet"):
                match = re.search(r"\d+", msg)
                if match:
                    amount = float(match.group(0))
                    result = await game.join(user_id, username, event.get_platform_id(), amount)
                    if result:
                        await event.send(MessageChain().message(result))
                return
            if msg in ["开始", "start"]:
                success, error = await game.start()
                if not success:
                    await event.send(MessageChain().message(f"🚫 {error}"))
                return

        # 保险阶段
        if game.phase == GamePhase.INSURANCE:
            if msg in ["保险", "yes", "insure"]:
                result = await game.action_insurance(user_id)
                if result:
                    await event.send(MessageChain().message(result))
                return
            if msg in ["跳过", "no", "skip"]:
                return

        # 投降阶段
        if game.phase == GamePhase.SURRENDER:
            if msg in ["投降", "surrender"]:
                result = await game.action_surrender(user_id)
                if result:
                    await event.send(MessageChain().message(result))
                return
            if msg in ["开始", "继续", "start"]:
                await game.start_player_turns()
                return

        # 玩家操作阶段
        if game.phase == GamePhase.PLAYER_TURN:
            if game.current_player_index < len(game.players):
                p = game.players[game.current_player_index]
                if p.user_id == user_id:
                    if msg in ["要牌", "hit", "h"]:
                        result = await game.action_hit(user_id)
                        if result:
                            await event.send(MessageChain().message(result))
                        return
                    if msg in ["停牌", "stand", "s"]:
                        result = await game.action_stand(user_id)
                        if result:
                            await event.send(MessageChain().message(result))
                        return
                    if msg in ["加倍", "double", "d"]:
                        result = await game.action_double(user_id)
                        if result:
                            await event.send(MessageChain().message(result))
                        return
                    if msg in ["分牌", "split", "p"]:
                        result = await game.action_split(user_id)
                        if result:
                            await event.send(MessageChain().message(result))

    # ==================== 命令处理器 ====================

    @command("blackjack", desc="21点游戏")
    async def cmd_blackjack(self, event: AstrMessageEvent):
        """21点游戏主指令

        指令
        blackjack.create [-n]  创建 (加 -n 为PVP)
        blackjack.end 结束当前游戏
        blackjack.stats 查询战绩

        核心规则
        BJ赔3:2 庄<17必拿 分A只发一张"""
        msg = """🃏 21点

指令
▸ blackjack.create [-n]  创建 (加 -n 为PVP)
▸ blackjack.end 结束当前游戏
▸ blackjack.stats 查询战绩

核心规则
▸ BJ赔3:2 庄<17必拿 分A只发一张"""
        event.set_result(MessageEventResult().message(msg).use_t2i(False))

    @command("blackjack.create", desc="创建新游戏", alias={"start"})
    async def cmd_blackjack_create(self, event: AstrMessageEvent, nodealer: bool = False):
        """创建新游戏

        Args:
            event: 消息事件
            nodealer: PVP模式(无庄家)
        """
        channel_id = event.session_id
        if channel_id in self.games:
            event.set_result(MessageEventResult().message("🚫 当前频道已有游戏正在进行。"))
            return

        game = GameSession(self.context, self.config, channel_id)
        self.games[channel_id] = game
        await game.init(nodealer)

        mode = "PVP" if nodealer else "PVE"
        msg = f'🎰 21点游戏已创建 ({mode})\n请发送 "下注 <金额>" 加入游戏。\n发送 "开始" 立即发牌。'
        event.set_result(MessageEventResult().message(msg).use_t2i(False))

    @command("blackjack.end", desc="强制结束当前游戏", alias={"stop", "force_end"})
    async def cmd_blackjack_force_end(self, event: AstrMessageEvent):
        """强制结束当前游戏"""
        channel_id = event.session_id
        game = self.games.get(channel_id)
        if game:
            await game.refund_all()
            game.destroy()
            del self.games[channel_id]
            event.set_result(
                MessageEventResult().message("✅ 游戏已强制结束，注金已退回。")
            )
        else:
            event.set_result(MessageEventResult().message("❓ 当前没有进行中的游戏。"))

    @command("blackjack.stats", desc="查询个人战绩", alias={"stat", "record"})
    async def cmd_blackjack_stats(self, event: AstrMessageEvent):
        """查询个人战绩"""
        user_id = event.session_id
        key = f"blackjack_stats_{user_id}"
        data = await sp.global_get(key, None)

        if not data:
            event.set_result(MessageEventResult().message("📭 你还没有玩过。"))
            return

        stat = BlackjackStats.from_dict(data)
        total = stat.wins + stat.loses + stat.draws
        rate = f"{(stat.wins / total * 100):.1f}" if total > 0 else "0.0"

        msg = f"""📊 {stat.username} 的战绩
💰 总盈亏: {"+" if stat.total_profit > 0 else ""}{stat.total_profit}
🏆 胜: {stat.wins} | ❌ 负: {stat.loses} | 🤝 平: {stat.draws}
📈 胜率: {rate}%"""
        event.set_result(MessageEventResult().message(msg).use_t2i(False))

    @command("blackjack.rank", desc="查看盈亏排行榜", alias={"ranking", "leaderboard"})
    async def cmd_blackjack_rank(self, event: AstrMessageEvent, limit: int = 10):
        """查看盈亏排行榜

        Args:
            event: 消息事件
            limit: 显示数量
        """
        # 获取所有统计数据
        stats_data = []
        for key in await sp.global_get(None, []) or []:
            if key.startswith("blackjack_stats_"):
                data = await sp.global_get(key, None)
                if data:
                    stats_data.append(BlackjackStats.from_dict(data))

        if not stats_data:
            event.set_result(MessageEventResult().message("📊 暂时没有排名数据。"))
            return

        # 按利润降序排序
        stats_data.sort(key=lambda x: x.total_profit, reverse=True)
        stats_data = stats_data[: min(limit, 20)]

        list_str = ""
        for index, stat in enumerate(stats_data):
            symbol = "+" if stat.total_profit > 0 else ""
            prefix = (
                "🥇 "
                if index == 0
                else "🥈 "
                if index == 1
                else "🥉 "
                if index == 2
                else f"{index + 1}. "
            )
            list_str += f"{prefix}{stat.username}: {symbol}{stat.total_profit}\n"

        msg = f"🏆 21点 盈亏排行榜 (Top {len(stats_data)})\n----------------\n{list_str}"
        event.set_result(MessageEventResult().message(msg).use_t2i(False))


# ========================================================================
# 📝 全局实例
# ========================================================================

blackjack_star: Optional[BlackjackStar] = None


def register_star_instance(star_instance: BlackjackStar):
    """注册插件实例"""
    global blackjack_star
    blackjack_star = star_instance
