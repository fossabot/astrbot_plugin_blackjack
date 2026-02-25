"""游戏会话类"""

from __future__ import annotations

import asyncio
import random
from typing import Any, Optional

from .models import BlackjackConfig
from .game_logic import (
    CARDS_TEMPLATE,
    GamePhase,
    HandState,
    PlayerState,
    broadcast,
    calc_score,
    charge,
    is_blackjack,
    get_card_rank,
    get_card_value,
    payout,
    record_stat,
)


class GameSession:
    """游戏会话"""

    def __init__(self, ctx: Any, config: BlackjackConfig, channel_id: str):
        self.ctx = ctx
        self.config = config
        self.channel_id = channel_id
        self.phase: GamePhase = GamePhase.IDLE
        self.players: list[PlayerState] = []
        self.deck: list[str] = []
        self.dealer_hand: list[str] = []
        self.current_player_index: int = 0
        self.is_no_dealer_mode: bool = False
        self._processing: bool = False
        self._timer_task: Optional[asyncio.Task] = None

    async def init(self, is_no_dealer: bool):
        """初始化游戏"""
        self.phase = GamePhase.JOINING
        self.is_no_dealer_mode = is_no_dealer
        self.players = []
        self.deck = []
        self._set_timer(self._handle_join_timeout, self.config.join_phase_timeout)

    async def join(self, user_id: str, username: str, platform: str, bet: float) -> str:
        """加入游戏"""
        if self.phase != GamePhase.JOINING:
            return "🚫 游戏已经开始或未初始化。"
        if self._processing:
            return ""

        if any(p.user_id == user_id for p in self.players):
            return "⚠️ 你已经加入了。"
        if bet < self.config.min_bet:
            return f"⚠️ 最低下注金额为 {self.config.min_bet}。"

        self._processing = True
        paid = await charge(user_id, bet)
        self._processing = False

        if not paid:
            return f"💸 余额不足，无法下注 {bet}。"

        self.players.append(
            PlayerState(
                user_id=user_id,
                username=username,
                platform=platform,
                bet=bet,
                hands=[HandState(cards=[], bet=bet)],
                current_hand_index=0,
                is_busy=False,
            )
        )

        self._set_timer(self._handle_join_timeout, self.config.join_phase_timeout)
        return f"✅ {username} 加入成功 (下注 {bet})。当前玩家: {len(self.players)}人。"

    async def start(self) -> tuple[bool, str]:
        """开始游戏"""
        if self.phase != GamePhase.JOINING:
            return False, "不在准备阶段"
        if not self.players:
            return False, "没有玩家"
        if self.is_no_dealer_mode and len(self.players) < 2:
            return False, "PVP模式至少需要2人"

        self._clear_timer()
        self.phase = GamePhase.DISTRIBUTING
        self._processing = True

        # 洗牌
        self.deck = CARDS_TEMPLATE * self.config.deck_count
        random.shuffle(self.deck)

        # 发牌 (闲2 庄2)
        for p in self.players:
            p.hands[0].cards.append(self._draw_card())
        if not self.is_no_dealer_mode:
            self.dealer_hand.append(self._draw_card())

        await asyncio.sleep(0.5)

        for p in self.players:
            p.hands[0].cards.append(self._draw_card())
        if not self.is_no_dealer_mode:
            self.dealer_hand.append(self._draw_card())

        await self._render_table("🃏 游戏开始！发牌完毕。")
        self._processing = False

        # 检查庄家明牌是否为 A
        if (
            not self.is_no_dealer_mode
            and self.dealer_hand
            and self.dealer_hand[0].endswith("A")
        ):
            self.phase = GamePhase.INSURANCE
            await broadcast("💡 庄家明牌为 A，是否购买保险？(回复 '保险' / '跳过')")
            self._set_timer(self._end_insurance_phase, 10)
            return True, ""

        await self._start_surrender_phase()
        return True, ""

    async def action_hit(self, user_id: str) -> str:
        """要牌"""
        if self._processing:
            return ""
        ctx = self._get_current_ctx(user_id)
        if not ctx:
            return ""

        p, h = ctx
        self._processing = True

        card = self._draw_card()
        h.cards.append(card)
        score = calc_score(h.cards)

        msg = f"🃏 {p.username} 要牌: {card} -> [{score}]"

        if score >= 21:
            h.is_finished = True

        self._processing = False
        asyncio.create_task(self._delayed_process_current_player_turn(0.5))
        return msg

    async def action_stand(self, user_id: str) -> str:
        """停牌"""
        if self._processing:
            return ""
        ctx = self._get_current_ctx(user_id)
        if not ctx:
            return ""

        p, h = ctx
        self._processing = True
        h.is_finished = True
        msg = f"🛑 {p.username} 停牌 [{calc_score(h.cards)}]"

        self._processing = False
        asyncio.create_task(self._delayed_process_current_player_turn(0.1))
        return msg

    async def action_double(self, user_id: str) -> str:
        """加倍"""
        if self._processing:
            return ""
        ctx = self._get_current_ctx(user_id)
        if not ctx:
            return ""

        p, h = ctx
        if len(h.cards) != 2:
            return "⚠️ 只能在首轮加倍。"
        if h.from_split:
            return "⚠️ 分牌后不支持加倍。"

        self._processing = True
        paid = await charge(user_id, h.bet)
        if not paid:
            self._processing = False
            return "💸 余额不足，无法加倍。"

        h.bet *= 2
        h.is_doubled = True

        card = self._draw_card()
        h.cards.append(card)
        h.is_finished = True

        score = calc_score(h.cards)
        msg = f"💰 {p.username} 加倍! 下注 {h.bet}。发牌: {card} -> [{score}]"

        self._processing = False
        asyncio.create_task(self._delayed_process_current_player_turn(1.0))
        return msg

    async def action_split(self, user_id: str) -> str:
        """分牌"""
        if self._processing:
            return ""
        ctx = self._get_current_ctx(user_id)
        if not ctx:
            return ""

        p, h = ctx
        if not self._check_can_split(p):
            return "⚠️ 无法分牌。"

        self._processing = True
        paid = await charge(user_id, h.bet)
        if not paid:
            self._processing = False
            return "💸 余额不足，无法分牌。"

        card1, card2 = h.cards[0], h.cards[1]
        is_split_aces = get_card_rank(card1) == "A"

        h.cards = [card1, self._draw_card()]
        h.from_split = True
        if is_split_aces:
            h.is_finished = True

        p.hands.append(
            HandState(
                cards=[card2, self._draw_card()],
                bet=h.bet,
                is_finished=is_split_aces,
                from_split=True,
            )
        )

        msg = f"🔱 {p.username} 完成分牌!"
        if is_split_aces:
            msg += " (分A只发一张牌)"

        self._processing = False
        asyncio.create_task(self._delayed_process_current_player_turn(1.0))
        return msg

    async def action_surrender(self, user_id: str) -> str:
        """投降"""
        if self.phase != GamePhase.SURRENDER:
            return ""
        p = next((x for x in self.players if x.user_id == user_id), None)
        if not p or p.hands[0].is_surrendered:
            return ""

        p.hands[0].is_surrendered = True
        p.hands[0].is_finished = True
        return f"🏳️ {p.username} 选择投降 (保留一半注金)。"

    async def action_insurance(self, user_id: str) -> str:
        """保险"""
        if self.phase != GamePhase.INSURANCE:
            return ""
        p = next((x for x in self.players if x.user_id == user_id), None)
        if not p or p.hands[0].insurance > 0:
            return ""

        cost = p.hands[0].bet / 2
        paid = await charge(user_id, cost)
        if not paid:
            return "💸 余额不足买保险。"

        p.hands[0].insurance = cost
        return f"🛡️ {p.username} 购买了保险 (花费 {cost})。"

    # ==================== 私有方法 ====================

    def _get_current_ctx(self, user_id: str) -> Optional[tuple[PlayerState, HandState]]:
        """获取当前玩家的上下文"""
        if self.phase != GamePhase.PLAYER_TURN:
            return None
        if self.current_player_index >= len(self.players):
            return None
        p = self.players[self.current_player_index]
        if p.user_id != user_id:
            return None
        return p, p.hands[p.current_hand_index]

    @staticmethod
    def _check_can_split(p: PlayerState) -> bool:
        """检查是否可以分牌"""
        if len(p.hands) >= 2:
            return False
        h = p.hands[p.current_hand_index]
        if len(h.cards) != 2:
            return False
        return get_card_value(h.cards[0]) == get_card_value(h.cards[1])

    def _draw_card(self) -> str:
        """抽牌"""
        if not self.deck:
            self.deck = CARDS_TEMPLATE * self.config.deck_count
            random.shuffle(self.deck)
        return self.deck.pop(0)

    async def _render_table(self, footer: str = ""):
        """渲染牌桌"""
        msg = "♠️♣️ Blackjack Table ♥️♦️\n"
        if not self.is_no_dealer_mode:
            show_hole = self.phase in [GamePhase.SETTLEMENT, GamePhase.DEALER_TURN]
            if self.dealer_hand:
                if show_hole:
                    dealer_cards = self.dealer_hand
                    dealer_score = f" [{calc_score(dealer_cards)}]"
                else:
                    dealer_cards = [self.dealer_hand[0], "🎴"]
                    dealer_score = " [?]"
                msg += f"👨‍💼 庄家: {''.join(dealer_cards)}{dealer_score}\n\n"

        for p in self.players:
            hand_strs = []
            for h in p.hands:
                status = []
                if h.is_surrendered:
                    status.append("🏳️")
                if h.is_doubled:
                    status.append("💰")
                if h.insurance:
                    status.append("🛡️")
                if h.from_split:
                    status.append("🔱")
                hand_str = (
                    f"{''.join(h.cards)} [{calc_score(h.cards)}] {''.join(status)}"
                )
                hand_strs.append(hand_str)
            msg += f"👤 {p.username} (${p.bet}): {' | '.join(hand_strs)}\n"

        msg += f"\n{footer}"
        await broadcast(msg)

    def _set_timer(self, callback, delay: float):
        """设置定时器"""
        self._clear_timer()
        self._timer_task = asyncio.create_task(asyncio.sleep(delay))
        self._timer_task.add_done_callback(lambda _: asyncio.create_task(callback()))

    def _clear_timer(self):
        """清除定时器"""
        if self._timer_task:
            self._timer_task.cancel()
            self._timer_task = None

    async def _delayed_process_current_player_turn(self, delay: float):
        """延迟处理玩家回合"""
        await asyncio.sleep(delay)
        await self._process_current_player_turn()

    async def _start_surrender_phase(self):
        """开始投降阶段"""
        self.phase = GamePhase.SURRENDER
        await broadcast(
            "🏳️ 投降阶段：如牌型不佳，可输入 '投降' (输一半)。\n⏳ 5秒后自动开始玩家回合。"
        )
        self._set_timer(self._start_player_turns, 5)

    async def _end_insurance_phase(self):
        """结束保险阶段"""
        await broadcast("⏰ 保险阶段结束。")
        await self._start_surrender_phase()

    async def start_player_turns(self):
        """开始玩家回合（公共接口）"""
        await self._start_player_turns()

    async def _start_player_turns(self):
        """开始玩家回合"""
        self._clear_timer()
        self.phase = GamePhase.PLAYER_TURN
        self.current_player_index = 0
        await self._process_current_player_turn()

    async def _process_current_player_turn(self):
        """处理当前玩家回合"""
        self._clear_timer()

        if self.current_player_index >= len(self.players):
            await self._start_dealer_turn()
            return

        player = self.players[self.current_player_index]
        hand = player.hands[player.current_hand_index]

        if hand.is_finished or hand.is_surrendered:
            await self._next_hand_or_player()
            return

        if is_blackjack(hand):
            await broadcast(f"⚡️ {player.username} 拿到 Blackjack!")
            hand.is_finished = True
            await self._next_hand_or_player()
            return

        score = calc_score(hand.cards)
        if score >= 21:
            hand.is_finished = True
            reason = "💥 爆牌" if score > 21 else "🛑 21点"
            if score > 21:
                await broadcast(f"💥 {player.username} {reason} ({score})")
            await self._next_hand_or_player()
            return

        prompt = f"👉 轮到 {player.username}"
        if len(player.hands) > 1:
            prompt += f" (手牌 {player.current_hand_index + 1}/{len(player.hands)})"
        prompt += f"\n🃏 当前牌: {''.join(hand.cards)} [{score}]"

        can_split = self._check_can_split(player)
        can_double = len(hand.cards) == 2 and not hand.from_split

        actions = ["要牌", "停牌"]
        if can_double:
            actions.append("加倍")
        if can_split:
            actions.append("分牌")

        prompt += f"\n指令: {' | '.join(actions)}"
        await broadcast(prompt)

        self._set_timer(
            lambda: asyncio.create_task(self._auto_stand(player.username)),
            self.config.player_turn_timeout,
        )

    async def _auto_stand(self, username: str):
        """自动停牌"""
        await broadcast(f"⏰ {username} 操作超时，自动停牌。")
        await self.action_stand(self.players[self.current_player_index].user_id)

    async def _next_hand_or_player(self):
        """切换到下一手牌或下一个玩家"""
        player = self.players[self.current_player_index]

        if player.current_hand_index < len(player.hands) - 1:
            player.current_hand_index += 1
            await asyncio.sleep(0.8)
            await self._process_current_player_turn()
        else:
            self.current_player_index += 1
            await asyncio.sleep(0.8)
            await self._process_current_player_turn()

    async def _start_dealer_turn(self):
        """开始庄家回合"""
        self.phase = GamePhase.DEALER_TURN
        self._clear_timer()

        if self.is_no_dealer_mode:
            return await self._settle_game()

        await broadcast(
            f"👨‍💼 庄家亮牌: {''.join(self.dealer_hand)} [{calc_score(self.dealer_hand)}]"
        )
        await asyncio.sleep(1.0)

        while calc_score(self.dealer_hand) < 17:
            card = self._draw_card()
            self.dealer_hand.append(card)
            await broadcast(
                f"👨‍💼 庄家要牌: {card} -> [{calc_score(self.dealer_hand)}]"
            )
            await asyncio.sleep(1.5)

        d_score = calc_score(self.dealer_hand)
        result = "💥 庄家爆牌!" if d_score > 21 else f"庄家最终点数: {d_score}"
        await broadcast(result)

        return await self._settle_game()

    async def _settle_game(self):
        """结算游戏"""
        self.phase = GamePhase.SETTLEMENT
        self._processing = True
        report = "📊 结算报告\n----------------\n"

        if self.is_no_dealer_mode:
            await self._settle_pvp(report)
        else:
            await self._settle_pve(report)

    async def _settle_pve(self, report_prefix: str):
        """PVE 结算"""
        d_score = calc_score(self.dealer_hand)
        d_is_bj = len(self.dealer_hand) == 2 and d_score == 21
        d_is_bust = d_score > 21

        for p in self.players:
            p_total_profit = 0.0
            p_report = f"{p.username}: "

            for hand in p.hands:
                if hand.is_surrendered:
                    refund = hand.bet / 2
                    await payout(p.user_id, refund)
                    p_total_profit -= refund
                    p_report += "[🏳️投降] "
                    continue

                if hand.insurance > 0:
                    if d_is_bj:
                        ins_return = hand.insurance * 3
                        await payout(p.user_id, ins_return)
                        p_total_profit += ins_return - hand.insurance
                        p_report += "[🛡️保赢] "
                    else:
                        p_total_profit -= hand.insurance
                        p_report += "[🛡️保亏] "

                p_score = calc_score(hand.cards)
                p_is_bj = is_blackjack(hand)

                hand_win_amount = 0.0
                hand_status = ""

                if p_score > 21:
                    hand_status = f"💥爆(-{hand.bet})"
                    p_total_profit -= hand.bet
                elif p_is_bj:
                    if d_is_bj:
                        hand_win_amount = hand.bet
                        hand_status = "🤝BJ平"
                    else:
                        hand_win_amount = hand.bet * 2.5
                        hand_status = f"⚡️BJ胜(+{hand.bet * 1.5})"
                        p_total_profit += hand.bet * 1.5
                elif d_is_bj:
                    hand_status = f"❌败(-{hand.bet})"
                    p_total_profit -= hand.bet
                elif d_is_bust:
                    hand_win_amount = hand.bet * 2
                    hand_status = f"🎉胜(+{hand.bet})"
                    p_total_profit += hand.bet
                elif p_score > d_score:
                    hand_win_amount = hand.bet * 2
                    hand_status = f"🎉胜(+{hand.bet})"
                    p_total_profit += hand.bet
                elif p_score == d_score:
                    hand_win_amount = hand.bet
                    hand_status = "🤝平"
                else:
                    hand_status = f"❌败(-{hand.bet})"
                    p_total_profit -= hand.bet

                if hand_win_amount > 0:
                    await payout(p.user_id, hand_win_amount)
                p_report += f"{hand_status} "

            await record_stat(p.user_id, p.username, p_total_profit)
            report_prefix += f"{p_report}\n"

        await broadcast(report_prefix)
        self.destroy()

    async def _settle_pvp(self, report_prefix: str):
        """PVP 结算"""
        active_players = [p for p in self.players if not p.hands[0].is_surrendered]
        valid_players = [
            p for p in active_players if calc_score(p.hands[0].cards) <= 21
        ]

        pool = 0.0

        for p in self.players:
            if p.hands[0].is_surrendered:
                await payout(p.user_id, p.bet / 2)
                pool += p.bet / 2
                report_prefix += f"{p.username}: 🏳️ 投降\n"
                await record_stat(p.user_id, p.username, -p.bet / 2)
            else:
                pool += p.bet

        if not valid_players:
            report_prefix += "🤷 全员爆牌/投降，系统收回剩余注金。"
        else:
            valid_players.sort(
                key=lambda p: (
                    -1 if is_blackjack(p.hands[0]) else 1,
                    -calc_score(p.hands[0].cards),
                )
            )

            winners = [valid_players[0]]
            best_hand = valid_players[0].hands[0]

            for p in valid_players[1:]:
                h = p.hands[0]
                same_bj = is_blackjack(best_hand) == is_blackjack(h)
                same_score = calc_score(best_hand.cards) == calc_score(h.cards)
                if same_bj and same_score:
                    winners.append(p)
                else:
                    break

            winner_ids = {w.user_id for w in winners}
            for p in self.players:
                if p.user_id not in winner_ids and not p.hands[0].is_surrendered:
                    report_prefix += f"{p.username}: ❌ 输 (-{p.bet})\n"
                    await record_stat(p.user_id, p.username, -p.bet)

            total_win = pool
            per_win = total_win / len(winners)
            for w in winners:
                await payout(w.user_id, per_win)
                profit = per_win - w.bet
                report_prefix += f"{w.username}: 🏆 赢 (+{profit})\n"
                await record_stat(w.user_id, w.username, profit)

        await broadcast(report_prefix)
        self.destroy()

    async def _handle_join_timeout(self):
        """处理加入超时"""
        if not self.players:
            await broadcast("🕐 无人加入，游戏取消。")
            self.destroy()
            return
        if self.is_no_dealer_mode and len(self.players) < 2:
            await broadcast("🕐 人数不足，PVP模式取消，退还注金。")
            await self._refund_all()
            self.destroy()
            return
        await broadcast("🕐 准备时间结束，自动开始！")
        await self.start()

    async def refund_all(self):
        """退还所有注金（公共接口）"""
        await self._refund_all()

    async def _refund_all(self):
        """退还所有注金"""
        for p in self.players:
            await payout(p.user_id, p.bet)

    def destroy(self):
        """销毁游戏会话"""
        self._clear_timer()
        self.phase = GamePhase.ENDED
