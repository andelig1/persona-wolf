"""游戏引擎 - 裁判模式

负责：分配角色、分发信息到Agent记忆、调用Agent、验证结果、判定胜负
不再直接控制Agent行为，每个AI Agent通过ReAct推理自主决策
"""
import random
from typing import List, Dict, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# sentinel: 区分 "API 未提供投票值" 与 "明确弃权 (None)"
_VOTE_NOT_PROVIDED = object()

from .phase_controller import Phase, PhaseController
from .role_manager import RoleManager
from .rule_checker import RuleChecker
from agents.react_agent import ReActWerewolfAgent
from agents.human_agent import HumanAgent
from agents.base_agent import BaseAgent
from memory.event_recorder import EventRecorder
from utils.logger import reset_logger


class GameEngine:
    """游戏引擎 - 裁判模式"""

    def __init__(self, num_players: int = 4, human_player_id: int = 1):
        self.num_players = num_players
        self.human_player_id = human_player_id

        # 核心组件
        self.role_manager = RoleManager()
        self.phase_controller = PhaseController()
        self.rule_checker = RuleChecker(self.role_manager)
        self.event_recorder = EventRecorder()

        # 游戏状态
        self.agents: Dict[int, BaseAgent] = {}
        self.alive_players: List[int] = []
        self.history: List[Dict] = []
        self.winner: Optional[str] = None

        # 发言顺序缓存 —— 避免同一轮内多次调用 _get_speaking_order() 产生不同随机结果
        # 导致 resume_from 位置与发言顺序对不上
        self._cached_order_key = None
        self._cached_order = None

        # 夜晚状态
        self.werewolf_kill_target: Optional[int] = None
        self.witch_has_save: bool = True
        self.witch_has_poison: bool = True
        self.seer_check_result: Optional[Tuple[int, str]] = None

    def initialize(self):
        """初始化游戏（随机分配角色）"""
        self.role_manager.assign_roles(self.num_players, self.human_player_id)
        self._init_agents_and_state()

    def initialize_with_roles(self, human_role: str = None):
        """初始化游戏（支持指定人类玩家角色）"""
        self.role_manager.assign_roles_with_human_choice(
            self.num_players, self.human_player_id, human_role
        )
        self._init_agents_and_state()

    def _init_agents_and_state(self):
        """初始化Agent和游戏状态"""
        reset_logger()  # 新游戏 => 新日志文件
        self._create_agents()
        self.alive_players = list(range(1, self.num_players + 1))  # 玩家编号从1开始
        self.phase_controller.start_game()
        self.history = []
        self.event_recorder.clear()
        self.last_night_dead = []  # 记录昨晚死亡的玩家，用于计算发言顺序

        # 给每个Agent记录初始信息
        for pid in range(2, self.num_players + 1):
            role = self.role_manager.get_player_role(pid)
            agent = self.agents[pid]
            agent.memory.add_memory(
                "phase_change",
                f"游戏开始，你是{pid}号玩家，身份是{role}",
                {"day": 0, "phase": "start", "player_id": pid}
            )

    def _create_agents(self):
        """创建Agent：AI用ReActWerewolfAgent，人类用HumanAgent"""
        import random
        all_personalities = ["rational", "agitative", "conservative", "impulsive", "slacker"]
        random.shuffle(all_personalities)

        ai_count = self.num_players - 1
        if ai_count > 5:
            extra = ai_count - 5
            for _ in range(extra):
                all_personalities.append(random.choice(["rational", "agitative", "conservative"]))
        personality_idx = 0

        for pid in range(1, self.num_players + 1):  # 玩家编号从1开始
            role = self.role_manager.get_player_role(pid)
            name = self.role_manager.player_names.get(pid, f"玩家{pid}")

            if pid == self.human_player_id:
                self.agents[pid] = HumanAgent(pid, role, name)
            else:
                personality = all_personalities[personality_idx % len(all_personalities)]
                personality_idx += 1
                self.agents[pid] = ReActWerewolfAgent(pid, role, personality, name)

    def get_game_state(self) -> Dict:
        """获取当前游戏状态"""
        return {
            "day": self.phase_controller.day,
            "phase": self.phase_controller.current_phase.value,
            "alive_players": self.alive_players.copy(),
            "player_roles": self.role_manager.player_roles.copy(),
            "player_names": self.role_manager.player_names.copy(),
            "num_players": self.num_players,
            "witch_has_save": self.witch_has_save,
            "witch_has_poison": self.witch_has_poison,
            "werewolf_kill_target": self.werewolf_kill_target,
        }

    def _distribute_info_to_memories(self, event_type: str, content: str,
                                      target: int = None, day: int = None,
                                      visibility: str = "public",
                                      player_id: int = -1,
                                      round_num: int = 1,
                                      position: int = 1,
                                      total_speakers: int = None):
        """推送游戏事件到相关Agent的记忆"""
        day = day or self.phase_controller.day
        if total_speakers is None:
            total_speakers = len(self.alive_players)

        metadata = {
            "day": day,
            "target": target,
            "player_id": player_id,
            "round_num": round_num,
            "position": position,
            "total_speakers": total_speakers,
        }

        self.event_recorder.record(
            event_type, player_id, content,
            target=target, day=day,
            phase=self.phase_controller.current_phase.value,
            visibility=visibility,
        )

        for pid, agent in self.agents.items():
            if pid not in self.alive_players and event_type != "eliminate":
                continue
            should_receive = False
            if visibility == "public":
                should_receive = True
            elif visibility == "werewolf" and self.role_manager.get_player_role(pid) == "狼人":
                should_receive = True
            elif visibility == "seer" and pid == player_id:
                should_receive = True
            elif visibility == "witch" and self.role_manager.get_player_role(pid) == "女巫":
                should_receive = True

            if should_receive:
                agent.memory.add_memory(event_type, content, metadata)

    # === 阶段方法（供CLI run()和API层调用）===

    # === 夜晚子阶段（供 night_step 和 night_step_stream 共用）===

    def _night_wolf_phase(self, game_state: dict, human_actions: dict,
                          pre_set_wolf_target: int = None):
        """执行狼人阶段，设置 self.werewolf_kill_target"""
        wolves = self.role_manager.get_alive_by_role("狼人", self.alive_players)
        if not wolves:
            return
        wolf_agent = self.agents[wolves[0]]

        if isinstance(wolf_agent, HumanAgent):
            target = human_actions.get("werewolf_target")
            if target is None and pre_set_wolf_target is not None:
                target = pre_set_wolf_target
            if target is None:
                while True:
                    try:
                        target = int(input("\n   狼人请选择你们要刀的对象: "))
                        if target in self.alive_players and target not in wolves:
                            break
                        print("   无效选择，请重新选择（不能杀自己或队友）")
                    except ValueError:
                        print("   请输入数字")
            self.werewolf_kill_target = target
        else:
            if pre_set_wolf_target is not None:
                self.werewolf_kill_target = pre_set_wolf_target
            else:
                action = wolf_agent.night_action(game_state, wolf_teammates=wolves)
                if action and action.get("type") == "kill":
                    self.werewolf_kill_target = action.get("target")

        if self.werewolf_kill_target is not None:
            self._distribute_info_to_memories(
                "kill", f"狼人选择击杀{self.werewolf_kill_target}号",
                target=self.werewolf_kill_target, visibility="werewolf",
                player_id=wolves[0],
            )

    def _night_seer_phase(self, game_state: dict, human_actions: dict):
        """执行预言家阶段，设置 self.seer_check_result"""
        seers = self.role_manager.get_alive_by_role("预言家", self.alive_players)
        if not seers:
            return
        seer_agent = self.agents[seers[0]]

        if isinstance(seer_agent, HumanAgent):
            target = human_actions.get("seer_target")
            if target is None:
                while True:
                    try:
                        target = int(input("\n   预言家请选择你要查验的对象: "))
                        if target in self.alive_players and target != seers[0]:
                            break
                        print("   无效选择，请重新选择")
                    except ValueError:
                        print("   请输入数字")
            if target is not None:
                role = self.role_manager.get_player_role(target)
                self.seer_check_result = (target, role)
                seer_agent.memory.set_role_knowledge(target, role)
                seer_agent.memory.add_memory(
                    "check_result", f"你查验了{target}号，身份是{role}",
                    {"day": self.phase_controller.day, "target": target}
                )
                role_desc = "好人" if role in ["村民", "预言家", "女巫"] else "坏人"
                print(f"\n   ┌─────────────────────────────┐")
                print(f"   │  他的身份是 {role_desc}              │")
                print(f"   │  ({target} 号玩家是 {role})         │")
                print(f"   └─────────────────────────────┘")
        else:
            action = seer_agent.night_action(game_state)
            if action and action.get("type") == "check":
                target = action.get("target")
                if target in self.alive_players and target != seers[0]:
                    role = self.role_manager.get_player_role(target)
                    self.seer_check_result = (target, role)
                    seer_agent.memory.set_role_knowledge(target, role)
                    seer_agent.memory.add_memory(
                        "check_result", f"你查验了{target}号，身份是{role}",
                        {"day": self.phase_controller.day, "target": target}
                    )
                    role_desc = "好人" if role in ["村民", "预言家", "女巫"] else "坏人"
                    print(f"\n   ┌─────────────────────────────┐")
                    print(f"   │  他的身份是 {role_desc}              │")
                    print(f"   │  ({target} 号玩家是 {role})         │")
                    print(f"   └─────────────────────────────┘")

    def _night_witch_phase(self, game_state: dict, human_actions: dict):
        """执行女巫阶段，返回 (saved: bool, poisoned: int or None)"""
        witches = self.role_manager.get_alive_by_role("女巫", self.alive_players)
        if not witches:
            return False, None

        witch_agent = self.agents[witches[0]]
        saved = False
        poisoned = None

        if isinstance(witch_agent, HumanAgent):
            if self.werewolf_kill_target is not None and self.witch_has_save:
                choice = human_actions.get("witch_save_choice")
                if choice is None:
                    choice = input("\n   请问你是否要使用解药救人？(y/n): ").lower()
                if choice == 'y':
                    saved = True
                    self.witch_has_save = False
                    print(f"\n   ✓ 女巫使用解药，救活了 {self.werewolf_kill_target} 号玩家")
            elif self.werewolf_kill_target is not None and not self.witch_has_save:
                print(f"\n   ⚠️ 解药已使用，无法救人")

            if not saved and self.witch_has_poison:
                poison_target = human_actions.get("witch_poison")
                if poison_target is not None and poison_target != 'n' and poison_target != 'no':
                    if isinstance(poison_target, int) and poison_target in self.alive_players:
                        poisoned = poison_target
                        self.witch_has_poison = False
                    elif isinstance(poison_target, str):
                        while True:
                            try:
                                poison_choice = int(input("   请选择毒杀目标: "))
                                if poison_choice in self.alive_players:
                                    break
                                print("   无效选择")
                            except ValueError:
                                print("   请输入数字")
                        if poison_choice and poison_choice in self.alive_players:
                            poisoned = poison_choice
                            self.witch_has_poison = False
        else:
            game_state_copy = game_state.copy()
            game_state_copy["werewolf_kill_target"] = self.werewolf_kill_target
            action = witch_agent.night_action(
                game_state_copy,
                werewolf_target=self.werewolf_kill_target,
                has_save=self.witch_has_save,
                has_poison=self.witch_has_poison,
            )
            if action:
                if action.get("type") == "save" and self.witch_has_save:
                    saved = True
                    self.witch_has_save = False
                elif action.get("type") == "poison" and self.witch_has_poison:
                    pt = action.get("target")
                    if pt and pt in self.alive_players:
                        poisoned = pt
                        self.witch_has_poison = False

        return saved, poisoned

    def _night_apply_deaths(self, saved: bool, poisoned: int) -> list:
        """应用夜晚死亡并分发信息，返回 dead 列表"""
        dead = []
        if self.werewolf_kill_target is not None and not saved:
            dead.append(self.werewolf_kill_target)
        if poisoned is not None and poisoned in self.alive_players and poisoned not in dead:
            dead.append(poisoned)

        self.last_night_dead = sorted(dead) if dead else []

        if dead:
            self._kill_players(dead)

        if dead:
            dead_names = [f"{p}号" for p in dead]
            self._distribute_info_to_memories(
                "death", f"第{self.phase_controller.day-1}晚{', '.join(dead_names)}死亡",
                visibility="public", day=self.phase_controller.day-1,
            )
            # ★ 触发信念审计：玩家死亡是重要新证据
            # 夜晚死亡不公布身份，但死亡本身说明该玩家不是当晚动手的狼人
            death_evidence = [
                {"type": "player_died", "player_id": d} for d in dead
            ]
            self._trigger_belief_audit(death_evidence, trigger_reason="夜晚死亡")
        else:
            self._distribute_info_to_memories(
                "death", f"第{self.phase_controller.day-1}晚是平安夜，没有人死亡",
                visibility="public", day=self.phase_controller.day-1,
            )
        return dead

    def night_step(self, human_actions: dict = None, pre_set_wolf_target: int = None) -> dict:
        """执行夜晚阶段（CLI / 同步 API）

        Args:
            human_actions: 人类玩家的夜晚行动
            pre_set_wolf_target: 预先设置的狼人击杀目标（跳过AI推理，直接使用）
        Returns:
            夜晚结果 dict
        """
        print("\n" + "=" * 50)
        print(f"🌙 第 {self.phase_controller.day} 天夜晚到来...")
        print("=" * 50)

        self.werewolf_kill_target = None
        self.seer_check_result = None
        game_state = self.get_game_state()
        human_actions = human_actions or {}

        # 狼人
        wolves = self.role_manager.get_alive_by_role("狼人", self.alive_players)
        if wolves:
            print("\n" + "-" * 40)
            print("🐺 狼人请睁眼...")
            print("-" * 40)
            self._night_wolf_phase(game_state, human_actions, pre_set_wolf_target)
            print("\n🐺 确认完毕，狼人请闭眼...")
        else:
            print("\n🐺 狼人已全部出局，无人睁眼")

        # 预言家
        seers = self.role_manager.get_alive_by_role("预言家", self.alive_players)
        print("\n" + "-" * 40)
        print("🔮 预言家请睁眼...")
        print("-" * 40)
        if seers:
            self._night_seer_phase(game_state, human_actions)
            print("\n🔮 预言家请闭眼...")
        else:
            print("   预言家已出局，无人睁眼")

        # 女巫
        witches = self.role_manager.get_alive_by_role("女巫", self.alive_players)
        print("\n" + "-" * 40)
        print("🧪 女巫请睁眼...")
        print("-" * 40)
        if witches:
            saved, poisoned = self._night_witch_phase(game_state, human_actions)
            print("\n🧪 女巫请闭眼...")
        else:
            print("   女巫已出局，无人睁眼")
            saved, poisoned = False, None

        # 应用死亡
        dead = self._night_apply_deaths(saved, poisoned)

        # 切换阶段
        self.phase_controller.next_phase()

        return {
            "killed": self.werewolf_kill_target,
            "saved": saved,
            "poisoned": poisoned,
            "checked": self.seer_check_result[0] if self.seer_check_result else None,
            "checked_role": self.seer_check_result[1] if self.seer_check_result else None,
            "dead": dead,
        }

    def night_step_stream(self, human_actions: dict = None, pre_set_wolf_target: int = None,
                          skip_intro: bool = False, resume_phase: str = None):
        """执行夜晚阶段 — 流式生成器版本
        resume_phase: None=从头开始, "seer"=跳过狼人, "witch"=跳过狼人+预言家
        每个阶段人类玩家未提供操作时暂停 yield awaiting_xxx 事件。
        """
        day = self.phase_controller.day
        # resume 时不重置已由前面阶段设置的值
        if not resume_phase:
            self.werewolf_kill_target = None
        self.seer_check_result = None
        game_state = self.get_game_state()
        human_actions = human_actions or {}
        skip_wolf = resume_phase in ("seer", "witch")
        skip_seer = resume_phase == "witch"

        if not skip_intro and not skip_wolf:
            yield {"type": "system", "content": f"🌙 第 {day} 天夜晚到来..."}
            yield {"type": "system", "content": "☽ 所有人请闭眼"}

        # —— 狼人阶段 ——
        if not skip_wolf:
            wolves = self.role_manager.get_alive_by_role("狼人", self.alive_players)
            if wolves:
                if not skip_intro:
                    yield {"type": "system", "content": "🐺 狼人请睁眼"}

                human_is_wolf = any(isinstance(self.agents[w], HumanAgent) for w in wolves)
                if human_is_wolf and not human_actions.get("werewolf_target") and not pre_set_wolf_target:
                    yield {"type": "awaiting_wolf_target"}
                    return

                self._night_wolf_phase(game_state, human_actions, pre_set_wolf_target)

                yield {"type": "system", "content": "🐺 狼人请闭眼"}
            else:
                if not skip_intro:
                    yield {"type": "system", "content": "🐺 狼人已全部出局，无人睁眼"}

        # —— 预言家阶段 ——
        if not skip_seer:
            seers = self.role_manager.get_alive_by_role("预言家", self.alive_players)
            if seers:
                # 只有完全从头开始(resume_phase=None)或skip_intro才不播"请睁眼"
                # resume_phase='seer' 说明预言家"请睁眼"已播过→跳过
                if resume_phase != 'seer':
                    yield {"type": "system", "content": "🔮 预言家请睁眼"}

                human_is_seer = any(isinstance(self.agents[s], HumanAgent) for s in seers)
                if human_is_seer and not human_actions.get("seer_target"):
                    yield {"type": "awaiting_seer_target"}
                    return

                self._night_seer_phase(game_state, human_actions)

                yield {"type": "system", "content": "🔮 预言家请闭眼"}

                # 查验完成后立刻推送结果
                if self.seer_check_result:
                    yield {"type": "seer_result",
                           "checked": self.seer_check_result[0],
                           "checked_role": self.seer_check_result[1]}
            else:
                if not skip_intro:
                    yield {"type": "system", "content": "🔮 预言家已出局，无人睁眼"}

        # —— 女巫阶段 ——
        witches = self.role_manager.get_alive_by_role("女巫", self.alive_players)
        if witches:
            # resume_phase='witch' 时女巫"请睁眼"已播过→跳过
            if resume_phase != 'witch':
                yield {"type": "system", "content": "🧪 女巫请睁眼"}

            human_is_witch = any(isinstance(self.agents[w], HumanAgent) for w in witches)
            if human_is_witch:
                has_save_action = human_actions.get("witch_save_choice")
                if has_save_action is None:
                    yield {"type": "awaiting_witch_action"}
                    return

            saved, poisoned = self._night_witch_phase(game_state, human_actions)

            yield {"type": "system", "content": "🧪 女巫请闭眼"}
        else:
            yield {"type": "system", "content": "🧪 女巫已出局，无人睁眼"}
            saved, poisoned = False, None

        yield {"type": "system", "content": "☀️ 所有人请睁眼"}

        # —— 死亡结果 ——
        dead = self._night_apply_deaths(saved, poisoned)
        if dead:
            dead_names = [f"{p}号" for p in dead]
            yield {"type": "result", "content": f"💀 昨夜，{'、'.join(dead_names)}玩家死亡",
                   "dead": dead}
        else:
            yield {"type": "result", "content": "🌙 昨夜是平安夜", "dead": []}

        # 切换阶段 + 检查胜负
        self.phase_controller.next_phase()
        winner = self.rule_checker.check_win_condition(self.alive_players)
        game_over = winner is not None
        if game_over:
            self.winner = winner
            self.phase_controller.end_game(winner)
            yield {"type": "system", "content": f"🏆 {winner} 胜利！"}

        yield {
            "type": "done",
            "phase": self.phase_controller.current_phase.value,
            "checked": self.seer_check_result[0] if self.seer_check_result else None,
            "checked_role": self.seer_check_result[1] if self.seer_check_result else None,
            "game_over": game_over,
            "winner": winner if game_over else None,
        }

    def _get_speaking_order(self) -> list:
        """计算发言顺序（带缓存，同一轮内多次调用返回相同顺序）：
        - 从昨晚死亡玩家后面的位置开始发言
        - 若当晚多人死亡则选择位置较前的玩家后面开始发言
        - 当晚无人死亡则随机选择起始玩家

        缓存机制：day_step_stream 在一次完整发言轮次中会被调用多次
        （前端暂停→续播），每次调用 _get_speaking_order 必须返回同一个顺序，
        否则 resume_from 位置会与新顺序错位，导致玩家重复发言或跳过发言。
        """
        day = self.phase_controller.day
        alive = sorted(self.alive_players)
        # 缓存键 = 天数 + 存活玩家组合（死亡改变存活列表时自动刷新）
        cache_key = (day, tuple(alive))
        if self._cached_order is not None and self._cached_order_key == cache_key:
            return self._cached_order

        print(f"[发言顺序调试] 存活玩家: {alive}")
        print(f"[发言顺序调试] 昨晚死亡玩家: {self.last_night_dead}")

        if self.last_night_dead:
            # 选择位置最靠前的死亡玩家
            first_dead = min(self.last_night_dead)
            print(f"[发言顺序调试] 第一个死亡玩家: {first_dead}")
            # 找到该玩家后面的位置开始发言
            start_idx = None
            for i, pid in enumerate(alive):
                if pid > first_dead:
                    start_idx = i
                    break
            # 如果死亡玩家是最大编号，则从第一个存活玩家开始
            if start_idx is None:
                start_idx = 0
        else:
            # 无人死亡，随机选择一个存活玩家作为起始发言者
            # 避免人类玩家（1号）总是第一个发言成为靶子
            import random
            start_idx = random.randrange(0, len(alive))

        print(f"[发言顺序调试] 开始索引: {start_idx}")
        # 生成发言顺序（从start_idx开始，循环整个存活列表）
        order = alive[start_idx:] + alive[:start_idx]
        print(f"[发言顺序调试] 最终发言顺序: {order}")

        # 缓存本轮的发言顺序
        self._cached_order_key = cache_key
        self._cached_order = order
        return order

    def _handle_human_speech(self, pid: int, round_num: int = 1,
                              position: int = 1, total_speakers: int = 6) -> dict:
        """处理人类玩家的发言输入

        Args:
            pid: 玩家ID
            round_num: 当前讨论轮次
            position: 当前发言位置（1-based）
            total_speakers: 本轮总发言人数
        Returns:
            发言信息 dict，包含 player_id, name, content
        """
        agent = self.agents[pid]
        role = self.role_manager.get_player_role(pid)
        name = self.role_manager.player_names.get(pid, f"玩家{pid}")
        
        # 人类玩家显示为"玩家X（你）"
        display_name = f"玩家{pid}（你）" if isinstance(agent, HumanAgent) else name
        print(f"\n[{display_name}] 你是 {role}")
        
        # 优先使用预先设置的发言内容（来自前端API），否则等待控制台输入
        if hasattr(self, 'human_speech') and self.human_speech:
            content = self.human_speech
            # 消费后清空，避免重复使用
            self.human_speech = None
        else:
            content = input("请输入发言: ")

        speech_info = {
            "player_id": pid,
            "name": name,
            "content": content
        }

        # 人类发言加 [真人] 标记，防止 AI 过度解读
        memory_content = f"第{self.phase_controller.day}天{pid}号玩家[真人]: {content}"
        self._distribute_info_to_memories(
            "speak", memory_content,
            target=pid, visibility="public",
            player_id=pid,
            day=self.phase_controller.day,
            round_num=round_num,
            position=position,
            total_speakers=total_speakers,
        )
        self._add_event("speak", pid, content, role=role)

        print(f"\n[{name}] {content}")

        return speech_info

    def day_step(self, human_speech: str = None, round_num: int = 1,
                 previous_speeches: list = None) -> dict:
        """执行白天一轮发言

        Args:
            human_speech: 人类玩家的发言内容
            round_num: 当前讨论轮次
            previous_speeches: 本天之前轮次的发言
        Returns:
            发言结果 dict
        """
        game_state = self.get_game_state()
        speeches = []
        previous_speeches = previous_speeches or []

        speaking_order = self._get_speaking_order()
        total_speakers = len(speaking_order)

        for idx, pid in enumerate(speaking_order):
            position = idx + 1
            agent = self.agents[pid]
            role = self.role_manager.get_player_role(pid)
            name = self.role_manager.player_names.get(pid, f"玩家{pid}")

            if isinstance(agent, HumanAgent):
                speech_info = self._handle_human_speech(
                    pid, round_num=round_num,
                    position=position, total_speakers=total_speakers
                )
                content = speech_info["content"]
                speeches.append({"player_id": pid, "name": name, "content": content})
            else:
                wolf_teammates = []
                if role == "狼人":
                    wolf_teammates = self.role_manager.get_alive_by_role("狼人", self.alive_players)
                try:
                    all_previous_speeches = previous_speeches + speeches
                    content = agent.speak(
                        game_state,
                        wolf_teammates=wolf_teammates,
                        round_num=round_num,
                        previous_speeches=all_previous_speeches,
                    )
                except Exception as e:
                    content = agent.strategy.generate_speech(
                        agent.memory, game_state, agent.personality
                    )

                # 人类玩家显示为"玩家X（你）
                display_name = f"玩家{pid}（你）" if isinstance(agent, HumanAgent) else name
                print(f"\n[{display_name}] {content}")

                memory_content = f"第{self.phase_controller.day}天{pid}号玩家: {content}"
                self._distribute_info_to_memories(
                    "speak", memory_content,
                    target=pid, visibility="public",
                    player_id=pid,
                    day=self.phase_controller.day,
                    round_num=round_num,
                    position=position,
                    total_speakers=total_speakers,
                )
                self._add_event("speak", pid, content, role=role)

                speeches.append({"player_id": pid, "name": name, "content": content})

        return {"speeches": speeches}

    def day_step_stream(self, human_speech: str = None, round_num: int = 1,
                        previous_speeches: list = None, resume_from: int = 0):
        """执行白天一轮发言 - 流式生成器版本

        逐个产出发言，不再等待全部完成。前端可以实时显示。
        当人类玩家未提供发言时，在轮到人类时暂停并 yield awaiting_input，
        等前端二次调用时通过 resume_from 续播。
        """
        game_state = self.get_game_state()
        previous_speeches = previous_speeches or []
        speeches_so_far = []

        speaking_order = self._get_speaking_order()
        total_speakers = len(speaking_order)

        for idx, pid in enumerate(speaking_order):
            position = idx + 1

            # 续播模式：跳过已处理过的发言位置
            if position < resume_from:
                continue
            if position == resume_from and isinstance(self.agents[pid], HumanAgent):
                # 这是人类玩家之前暂停的位置，现在有发言了
                agent = self.agents[pid]
                name = self.role_manager.player_names.get(pid, f"玩家{pid}")
                if human_speech:
                    self.human_speech = human_speech
                speech_info = self._handle_human_speech(
                    pid, round_num=round_num,
                    position=position, total_speakers=total_speakers
                )
                content = speech_info["content"]
                speech = {"player_id": pid, "name": name, "content": content,
                          "position": position, "total_speakers": total_speakers}
                speeches_so_far.append(speech)
                yield speech
                continue

            agent = self.agents[pid]
            role = self.role_manager.get_player_role(pid)
            name = self.role_manager.player_names.get(pid, f"玩家{pid}")

            if isinstance(agent, HumanAgent):
                # 没有预设发言 → 暂停，等前端提供
                if not human_speech and not getattr(self, 'human_speech', None):
                    yield {"player_id": pid, "name": name, "content": None,
                           "awaiting_input": True, "position": position,
                           "total_speakers": total_speakers}
                    return
                # 有发言 → 正常处理
                if human_speech:
                    self.human_speech = human_speech
                speech_info = self._handle_human_speech(
                    pid, round_num=round_num,
                    position=position, total_speakers=total_speakers
                )
                content = speech_info["content"]
            else:
                wolf_teammates = []
                if role == "狼人":
                    wolf_teammates = self.role_manager.get_alive_by_role("狼人", self.alive_players)
                try:
                    all_previous_speeches = previous_speeches + speeches_so_far
                    content = agent.speak(
                        game_state,
                        wolf_teammates=wolf_teammates,
                        round_num=round_num,
                        previous_speeches=all_previous_speeches,
                    )
                except Exception:
                    content = agent.strategy.generate_speech(
                        agent.memory, game_state, agent.personality
                    )

                memory_content = f"第{self.phase_controller.day}天{pid}号玩家: {content}"
                self._distribute_info_to_memories(
                    "speak", memory_content,
                    target=pid, visibility="public",
                    player_id=pid,
                    day=self.phase_controller.day,
                    round_num=round_num,
                    position=position,
                    total_speakers=total_speakers,
                )
                self._add_event("speak", pid, content, role=role)

            speech = {"player_id": pid, "name": name, "content": content,
                      "position": position, "total_speakers": total_speakers}
            speeches_so_far.append(speech)
            yield speech

    def discussion_phase(self) -> list:
        """单轮讨论阶段：玩家和AI轮流发言一轮后直接进入投票

        Returns:
            本轮发言列表
        """
        print("\n" + "=" * 50)
        print(f"☀️ 第 {self.phase_controller.day} 天亮...")
        print("=" * 50)
        
        print("\n" + "-" * 40)
        if self.last_night_dead:
            dead_names = [f"{p}号" for p in self.last_night_dead]
            print(f"昨夜，{', '.join(dead_names)}号玩家死亡...")
        else:
            print("昨夜是平安夜，没有人死亡...")
        print("-" * 40)

        all_speeches = []
        round_num = 1

        # 只进行一轮发言
        print(f"\n🗣️ --- 发言环节 ---")
        result = self.day_step(round_num=round_num,
                               previous_speeches=all_speeches)
        round_speeches = result["speeches"]
        all_speeches.extend(round_speeches)

        self.phase_controller.next_phase()
        return all_speeches

    def _ai_vote_worker(self, pid: int, game_state: dict, valid_targets: list,
                        tie_candidates: list = None) -> dict:
        """单个 AI 玩家的投票任务（线程安全，供并行调用）"""
        agent = self.agents[pid]
        role = self.role_manager.get_player_role(pid)
        name = self.role_manager.player_names.get(pid, f"玩家{pid}")

        wolf_teammates = []
        if role == "狼人":
            wolf_teammates = self.role_manager.get_alive_by_role("狼人", self.alive_players)

        try:
            if tie_candidates:
                target = agent.vote(game_state, wolf_teammates=wolf_teammates, vote_options=tie_candidates)
            else:
                target = agent.vote(game_state, wolf_teammates=wolf_teammates)
        except Exception:
            others = [p for p in valid_targets if p != pid]
            target = random.choice(others) if others else None

        # ★ 最后防线：狼人绝对不能投队友
        if role == "狼人" and target is not None and target in wolf_teammates:
            import random
            safe_targets = [p for p in valid_targets if p != pid and p not in wolf_teammates]
            if safe_targets:
                target = random.choice(safe_targets)
            else:
                target = None  # 没有合法目标则弃权

        return {
            "pid": pid, "target": target, "role": role, "name": name,
        }

    def _record_vote(self, pid: int, target: int, valid_targets: list,
                     votes: dict, vote_details: dict,
                     yield_progress: bool = False, agent=None) -> dict:
        """记录单次投票并分发记忆，可选返回进度事件"""
        name = self.role_manager.player_names.get(pid, f"玩家{pid}")
        is_human = isinstance(agent, HumanAgent) if agent else (pid == self.human_player_id)

        if target is not None and target in valid_targets and target != pid:
            votes[target] = votes.get(target, 0) + 1
            vote_details[pid] = target

            if is_human:
                display_name = f"玩家{pid}（你）"
            else:
                display_name = name
            print(f"   ✓ [{display_name}] 投票给了 {target} 号")

            self._distribute_info_to_memories(
                "vote", f"{pid}号玩家投票给{target}号玩家",
                target=target, visibility="public",
                player_id=pid, day=self.phase_controller.day,
            )

            if yield_progress:
                return {
                    "type": "vote_progress",
                    "player_id": pid,
                    "name": name,
                    "target": target,
                    "is_abstain": False,
                    "is_human": is_human,
                }
        else:
            if is_human:
                display_name = f"玩家{pid}（你）"
            else:
                display_name = name
            print(f"   ○ [{display_name}] 弃权")

            self._distribute_info_to_memories(
                "vote", f"{pid}号玩家弃权",
                visibility="public",
                player_id=pid, day=self.phase_controller.day,
            )

            if yield_progress:
                return {
                    "type": "vote_progress",
                    "player_id": pid,
                    "name": name,
                    "target": None,
                    "is_abstain": True,
                    "is_human": is_human,
                }
        return None

    def _collect_votes(self, game_state: dict, valid_targets: list,
                       human_vote=_VOTE_NOT_PROVIDED, tie_candidates: list = None,
                       yield_progress: bool = False):
        """收集所有存活玩家的投票。

        AI 玩家使用线程池并行投票，人类玩家使用传入的 human_vote。
        返回 (votes, vote_details, progress_events)。
        """
        votes: Dict[int, int] = {}
        vote_details: Dict[int, int] = {}
        progress_events: list = []
        ai_pids = []
        human_pid = None

        for pid in self.alive_players:
            if isinstance(self.agents[pid], HumanAgent):
                human_pid = pid
            else:
                ai_pids.append(pid)

        # 人类玩家先投票（瞬间完成）
        if human_pid is not None:
            target = human_vote
            if target is _VOTE_NOT_PROVIDED:
                # CLI 交互模式（没有从 API 传入投票值）
                print(f"\n👥 存活玩家: {self.alive_players}")
                if tie_candidates:
                    print(f"   └─ ⚠️ 平票重投，仅可投票给: {tie_candidates}")
                while True:
                    try:
                        raw = input("   选择投票目标 (输入数字投票，输入0或回车弃权): ")
                        if raw.strip() in ("", "0", "弃权", "skip", "pass"):
                            target = None
                            break
                        target = int(raw)
                        if target in valid_targets and target != self.human_player_id:
                            break
                        print("   ❌ 无效选择")
                    except ValueError:
                        print("   ❌ 请输入数字或输入0弃权")

            progress = self._record_vote(
                human_pid, target, valid_targets, votes, vote_details,
                yield_progress=yield_progress, agent=self.agents[human_pid],
            )
            if yield_progress and progress:
                progress_events.append(progress)

        # AI 玩家并行投票
        if ai_pids:
            vote_lock = threading.Lock()
            with ThreadPoolExecutor(max_workers=min(len(ai_pids), 8)) as executor:
                futures = {
                    executor.submit(
                        self._ai_vote_worker, pid, game_state,
                        valid_targets, tie_candidates
                    ): pid for pid in ai_pids
                }
                for future in as_completed(futures):
                    result = future.result()
                    pid = result["pid"]
                    target = result["target"]
                    with vote_lock:
                        progress = self._record_vote(
                            pid, target, valid_targets, votes, vote_details,
                            yield_progress=yield_progress, agent=self.agents[pid],
                        )
                    if yield_progress and progress:
                        progress_events.append(progress)

        return votes, vote_details, progress_events

    def vote_step_stream(self, human_vote=_VOTE_NOT_PROVIDED, tie_candidates: list = None, tie_speeches: list = None):
        """流式投票阶段 — 并行 AI 投票，实时 yield 进度事件

        Yields:
            dict: {"type": "vote_progress", "player_id": ..., "name": ..., "target": ..., ...}
            dict: {"type": "vote_tally", "votes": {...}, "eliminated": ..., ...}
            dict: {"type": "done", ...}
        """
        print("\n" + "=" * 45)
        print(f"🗳️ [VOTE] 第 {self.phase_controller.day} 天 - 投票阶段")
        print("=" * 45)

        pending = getattr(self, 'pending_tie_break', None)
        if pending is not None:
            candidates = pending.get('candidates', [])
            tie_count = pending.get('round', 1)
            final_votes = pending.get('votes', {})
            final_vote_details = pending.get('vote_details', {})
            self.pending_tie_break = None

            human_speech_map = {}
            if tie_speeches:
                for s in tie_speeches:
                    pid = s.get('player_id')
                    if pid in candidates and s.get('content'):
                        human_speech_map[pid] = s.get('content')

            _, pk_speeches = self._tie_break_speech(candidates, human_speeches=human_speech_map)
            for s in pk_speeches:
                yield {"type": "tie_speech", "player_id": s["player_id"],
                       "name": s["name"], "content": s["content"], "is_pk": True}
            other_speeches = self._tie_break_others_speech(candidates, allow_human_speech=False)
            for s in other_speeches:
                yield {"type": "tie_speech", "player_id": s["player_id"],
                       "name": s["name"], "content": s["content"], "is_pk": False}

            tie_msg2 = f"🔄 第{tie_count}轮重新投票，仅可投票给平票候选人"
            yield {"type": "system", "content": tie_msg2}
            self._add_event("system", -1, tie_msg2)

            game_state = self.get_game_state()
            print(f"\n🔄 --- 第 {tie_count} 轮重新投票 ---")
            print(f"   ├─ 仅可投票给平票候选人: {candidates}")
            print(f"   └─ 存活玩家: {self.alive_players}")

            while True:
                votes, vote_details, tie_progress = self._collect_votes(
                    game_state, candidates, human_vote=human_vote,
                    tie_candidates=candidates, yield_progress=True,
                )
                for evt in tie_progress:
                    yield evt
                # ★ 投票汇总消息
                if vote_details:
                    data = self._yield_vote_summary(vote_details, votes)
                    yield {"type": "vote_summary", "data": data}

                if not votes:
                    print(f"\n🫱 本轮无人投票，直接跳过投票阶段")
                    yield {"type": "system", "content": "本轮无人投票，直接跳过投票阶段"}
                    self._distribute_info_to_memories(
                        "system", "本轮无人投票，跳过投票阶段",
                        visibility="public", day=self.phase_controller.day,
                    )
                    eliminated = None
                    break

                max_votes_count = max(votes.values())
                new_candidates = [p for p, v in votes.items() if v == max_votes_count]
                if len(new_candidates) == 1:
                    eliminated = new_candidates[0]
                    role = self.role_manager.get_player_role(eliminated)
                    name = self.role_manager.player_names.get(eliminated, f"玩家{eliminated}")
                    print(f"\n⚔️ [淘汰] {name} ({role}) 被投票出局")
                    self.alive_players.remove(eliminated)
                    self._distribute_info_to_memories(
                        "eliminate", f"{name}被投票出局，身份是{role}",
                        target=eliminated, visibility="public",
                        player_id=eliminated,
                    )
                    self._add_event("eliminate", eliminated, f"{name}被投票出局", role=role)
                    # ★ 触发信念审计：投票出局公布身份是关键新证据
                    self._trigger_belief_audit(
                        [{"type": "death_role_reveal", "player_id": eliminated, "role": role}],
                        trigger_reason=f"投票出局({eliminated}号, {role})"
                    )
                    final_votes = votes
                    final_vote_details = vote_details
                    break

                tie_count += 1
                final_votes = votes
                final_vote_details = vote_details

                candidate_names = [f"{c}号" for c in new_candidates]
                yield {
                    "type": "tie_break",
                    "round": tie_count,
                    "candidates": new_candidates,
                }
                tie_msg3 = f"⚖️ 平票！{'、'.join(candidate_names)}进入第{tie_count}轮PK发言"
                yield {"type": "system", "content": tie_msg3}
                self._add_event("system", -1, tie_msg3)

                for candidate in new_candidates:
                    for pid, agent in self.agents.items():
                        if pid in self.alive_players:
                            agent.memory.update_suspicion(candidate, 0.1, "平票嫌疑")

                self.pending_tie_break = {
                    'round': tie_count,
                    'candidates': new_candidates,
                    'votes': dict(votes),
                    'vote_details': dict(vote_details),
                }

                if self.human_player_id in new_candidates and isinstance(self.agents.get(self.human_player_id), HumanAgent):
                    yield {
                        "type": "awaiting_tie_speech",
                        "round": tie_count,
                        "candidates": new_candidates,
                    }
                    return

                candidates = new_candidates
                _, pk_speeches = self._tie_break_speech(candidates)
                for s in pk_speeches:
                    yield {"type": "tie_speech", "player_id": s["player_id"],
                           "name": s["name"], "content": s["content"], "is_pk": True}
                other_speeches = self._tie_break_others_speech(candidates)
                for s in other_speeches:
                    yield {"type": "tie_speech", "player_id": s["player_id"],
                           "name": s["name"], "content": s["content"], "is_pk": False}

                tie_msg2 = f"🔄 第{tie_count}轮重新投票，仅可投票给平票候选人"
                yield {"type": "system", "content": tie_msg2}
                self._add_event("system", -1, tie_msg2)

                print(f"\n🔄 --- 第 {tie_count} 轮重新投票 ---")
                print(f"   ├─ 仅可投票给平票候选人: {candidates}")
                print(f"   └─ 存活玩家: {self.alive_players}")
                continue

            winner = self.rule_checker.check_win_condition(self.alive_players)
            if winner:
                self.winner = winner
                self.phase_controller.end_game(winner)
            else:
                self.phase_controller.next_phase()

            yield {
                "type": "done",
                "votes": final_votes,
                "vote_details": final_vote_details,
                "eliminated": eliminated,
                "game_over": winner is not None,
                "winner": winner,
            }
            return

        game_state = self.get_game_state()
        valid_targets = tie_candidates if tie_candidates else self.alive_players
        eliminated = None
        final_votes = {}
        final_vote_details = {}
        tie_count = 0
        max_tie_rounds = 3

        # 收集投票（AI 并行）
        votes, vote_details, progress_events = self._collect_votes(
            game_state, valid_targets, human_vote=human_vote,
            tie_candidates=tie_candidates, yield_progress=True,
        )
        for evt in progress_events:
            yield evt
        # ★ 投票汇总消息
        if vote_details:
            data = self._yield_vote_summary(vote_details, votes)
            yield {"type": "vote_summary", "data": data}

        # 全员弃权
        if not votes:
            print(f"\n🫱 本轮无人投票，直接跳过投票阶段")
            yield {"type": "system", "content": "本轮无人投票，直接跳过投票阶段"}
            self._distribute_info_to_memories(
                "system", "本轮无人投票，跳过投票阶段",
                visibility="public", day=self.phase_controller.day,
            )

        # 计票循环（含平票处理）
        while tie_count < max_tie_rounds and eliminated is None:
            if votes:
                max_votes_count = max(votes.values())
                candidates = [p for p, v in votes.items() if v == max_votes_count]
                print(f"\n📊 投票结果: {votes}")

                voters_count = len(vote_details)
                threshold = len(self.alive_players) // 3
                if voters_count < threshold:
                    print(f"   ⊘ 仅{voters_count}人投票（需≥{threshold}人），不触发淘汰")
                    yield {"type": "system", "content": f"仅{voters_count}人投票（需≥{threshold}人），不触发淘汰"}
                    break

                if len(candidates) == 1:
                    eliminated = candidates[0]
                    role = self.role_manager.get_player_role(eliminated)
                    name = self.role_manager.player_names.get(eliminated, f"玩家{eliminated}")
                    print(f"\n⚔️ [淘汰] {name} ({role}) 被投票出局")
                    self.alive_players.remove(eliminated)
                    self._distribute_info_to_memories(
                        "eliminate", f"{name}被投票出局，身份是{role}",
                        target=eliminated, visibility="public",
                        player_id=eliminated,
                    )
                    self._add_event("eliminate", eliminated, f"{name}被投票出局", role=role)
                    # ★ 触发信念审计：投票出局公布身份是关键新证据
                    self._trigger_belief_audit(
                        [{"type": "death_role_reveal", "player_id": eliminated, "role": role}],
                        trigger_reason=f"投票出局({eliminated}号, {role})"
                    )
                    final_votes = votes
                    final_vote_details = vote_details
                else:
                    tie_count += 1
                    print(f"\n⚖️ 平票: {candidates}，进入第 {tie_count} 轮PK发言")
                    final_votes = votes
                    final_vote_details = vote_details

                    candidate_names = [f"{c}号" for c in candidates]
                    yield {
                        "type": "tie_break",
                        "round": tie_count,
                        "candidates": candidates,
                    }
                    tie_msg1 = f"⚖️ 平票！{'、'.join(candidate_names)}进入第{tie_count}轮PK发言"
                    yield {"type": "system", "content": tie_msg1}
                    self._add_event("system", -1, tie_msg1)

                    for candidate in candidates:
                        for pid, agent in self.agents.items():
                            if pid in self.alive_players:
                                agent.memory.update_suspicion(candidate, 0.1, "平票嫌疑")

                    self.pending_tie_break = {
                        'round': tie_count,
                        'candidates': candidates,
                        'votes': dict(votes),
                        'vote_details': dict(vote_details),
                    }

                    if self.human_player_id in candidates and isinstance(self.agents.get(self.human_player_id), HumanAgent):
                        yield {
                            "type": "awaiting_tie_speech",
                            "round": tie_count,
                            "candidates": candidates,
                        }
                        return

                    # PK 发言（串行，因为发言有顺序依赖）
                    _, pk_speeches = self._tie_break_speech(candidates)
                    for s in pk_speeches:
                        yield {"type": "tie_speech", "player_id": s["player_id"],
                               "name": s["name"], "content": s["content"], "is_pk": True}
                    other_speeches = self._tie_break_others_speech(candidates)
                    for s in other_speeches:
                        yield {"type": "tie_speech", "player_id": s["player_id"],
                               "name": s["name"], "content": s["content"], "is_pk": False}

                    tie_msg2 = f"🔄 第{tie_count}轮重新投票，仅可投票给平票候选人"
                    yield {"type": "system", "content": tie_msg2}
                    self._add_event("system", -1, tie_msg2)

                    # 重新投票（仅平票候选人，AI 并行）
                    print(f"\n🔄 --- 第 {tie_count} 轮重新投票 ---")
                    print(f"   ├─ 仅可投票给平票候选人: {candidates}")
                    print(f"   └─ 存活玩家: {self.alive_players}")
                    votes.clear()
                    vote_details.clear()

                    # 人类玩家在平票重投中的交互
                    human_pid = None
                    for pid in self.alive_players:
                        if isinstance(self.agents[pid], HumanAgent):
                            human_pid = pid
                            break

                    tie_human_vote = None
                    if human_pid is not None and human_vote is _VOTE_NOT_PROVIDED:
                        agent = self.agents[human_pid]
                        if human_pid in candidates:
                            valid_vote = [c for c in candidates if c != self.human_player_id or c == human_pid]
                            prompt = f"   选择投票目标 (可选: {valid_vote}, 0=弃权): "
                            while True:
                                try:
                                    raw = input(prompt)
                                    if raw.strip() in ("", "0", "弃权", "skip", "pass"):
                                        tie_human_vote = None
                                        break
                                    tie_human_vote = int(raw)
                                    if tie_human_vote in candidates and (tie_human_vote != self.human_player_id or human_pid in candidates):
                                        break
                                    print("   ❌ 无效选择")
                                except ValueError:
                                    print("   ❌ 请输入数字或0弃权")
                        else:
                            while True:
                                try:
                                    raw = input("   选择投票目标 (0=弃权): ")
                                    if raw.strip() in ("", "0", "弃权", "skip", "pass"):
                                        tie_human_vote = None
                                        break
                                    tie_human_vote = int(raw)
                                    if tie_human_vote in candidates and tie_human_vote != self.human_player_id:
                                        break
                                    print("   ❌ 无效选择，只能投票给平票候选人")
                                except ValueError:
                                    print("   ❌ 请输入数字或0弃权")
                    elif human_pid is not None:
                        tie_human_vote = human_vote

                    # 并行收集平票重投
                    votes, vote_details, tie_progress = self._collect_votes(
                        game_state, candidates, human_vote=tie_human_vote,
                        tie_candidates=candidates, yield_progress=True,
                    )
                    for evt in tie_progress:
                        yield evt
                    # ★ 投票汇总消息
                    if vote_details:
                        data = self._yield_vote_summary(vote_details, votes)
                        yield {"type": "vote_summary", "data": data}

        if eliminated is None and tie_count >= 3:
            print(f"\n⚖️ 平票三轮未决，无人被投票出局")
            self._distribute_info_to_memories(
                "system", "平票三轮未决，无人被投票出局",
                visibility="public", day=self.phase_controller.day,
            )

        winner = self.rule_checker.check_win_condition(self.alive_players)
        if winner:
            self.winner = winner
            self.phase_controller.end_game(winner)
        else:
            self.phase_controller.next_phase()

        yield {
            "type": "done",
            "votes": final_votes,
            "vote_details": final_vote_details,
            "eliminated": eliminated,
            "game_over": winner is not None,
            "winner": winner,
        }

    def vote_step(self, human_vote=_VOTE_NOT_PROVIDED, tie_candidates: list = None) -> dict:
        """执行投票阶段（同步版本，兼容旧接口）

        内部调用 vote_step_stream，收集所有事件后返回最终结果。
        """
        result = {}
        for event in self.vote_step_stream(human_vote=human_vote, tie_candidates=tie_candidates):
            if event.get("type") == "done":
                result = {
                    "votes": event.get("votes", {}),
                    "vote_details": event.get("vote_details", {}),
                    "eliminated": event.get("eliminated"),
                    "game_over": event.get("game_over", False),
                    "winner": event.get("winner"),
                }
        return result

    def _tie_break_speech(self, candidates: list, human_speeches: dict = None) -> list:
        """平票PK发言环节

        Args:
            candidates: 平票候选人列表
        Returns:
            (candidate_order, speeches): 平票发言顺序和发言列表
        """
        print("\n--- 平票PK发言环节 ---")
        game_state = self.get_game_state()

        # 按原发言顺序的逆序发言
        speaking_order = self._get_speaking_order()
        # 只保留平票候选人，按原顺序的逆序排列
        candidate_order = [p for p in speaking_order if p in candidates]
        candidate_order.reverse()

        speeches = []
        for pid in candidate_order:
            agent = self.agents[pid]
            name = self.role_manager.player_names.get(pid, f"玩家{pid}")
            role = self.role_manager.get_player_role(pid)

            print(f"\n[{name}] (平票PK)")
            if isinstance(agent, HumanAgent):
                content = None
                if human_speeches:
                    content = human_speeches.get(pid)
                if not content:
                    # CLI 模式：提示人类输入；Web 模式：human_speeches 为空时也走这里
                    try:
                        content = input("   请输入PK发言: ").strip()
                    except (EOFError, OSError):
                        pass
                    if not content:
                        content = "我觉得自己很清白，请相信我。"
            else:
                wolf_teammates = []
                if role == "狼人":
                    wolf_teammates = self.role_manager.get_alive_by_role("狼人", self.alive_players)
                try:
                    content = agent.speak(
                        game_state,
                        wolf_teammates=wolf_teammates,
                        round_num=99,  # 特殊轮次标识PK发言
                        previous_speeches=[],
                    )
                except Exception as e:
                    content = f"我不是狼人！大家相信我！"

            print(f"[{name}] {content}")
            memory_content = f"{pid}号玩家(PK发言): {content}"
            self._distribute_info_to_memories(
                "speak", memory_content,
                target=pid, visibility="public",
                player_id=pid,
                round_num=99,
                position=1,
                total_speakers=len(candidate_order),
            )
            self._add_event("speak", pid, content, role=role)
            speeches.append({"player_id": pid, "name": name, "content": content, "is_pk": True})

        return candidate_order, speeches

    def _tie_break_others_speech(self, candidates: list, allow_human_speech: bool = True) -> list:
        """平票PK后其余玩家发言环节

        Args:
            candidates: 平票候选人列表
        Returns:
            其余玩家的发言列表
        """
        # 获取非候选人玩家
        others = [p for p in self.alive_players if p not in candidates]
        if not others:
            return []

        print("\n--- 其余玩家发言环节 ---")
        game_state = self.get_game_state()

        # 获取平票PK发言顺序（用于确定其余玩家发言顺序）
        speaking_order = self._get_speaking_order()
        candidate_order = [p for p in speaking_order if p in candidates]
        candidate_order.reverse()

        # 找到平票玩家中第一个发言的玩家
        if candidate_order:
            first_candidate = candidate_order[-1]  # 因为PK发言是逆序，所以最后一个是原顺序第一个
        else:
            first_candidate = candidates[0]

        # 计算其余玩家发言顺序：从第一个平票玩家的右手边开始，按倒序发言
        alive_sorted = sorted(self.alive_players)
        first_idx = alive_sorted.index(first_candidate)

        # 从第一个平票玩家的右手边开始
        others_order = []
        n = len(alive_sorted)
        for i in range(n):
            idx = (first_idx + 1 + i) % n
            pid = alive_sorted[idx]
            if pid not in candidates:
                others_order.append(pid)

        # 倒序发言
        others_order.reverse()

        speeches = []
        for pid in others_order:
            agent = self.agents[pid]
            name = self.role_manager.player_names.get(pid, f"玩家{pid}")
            role = self.role_manager.get_player_role(pid)

            print(f"\n[{name}]")

            # 询问是否发言
            want_speak = False
            if isinstance(agent, HumanAgent):
                if not allow_human_speech:
                    want_speak = False
                else:
                    want_speak = False
            else:
                # AI玩家有60%概率发言
                want_speak = random.random() < 0.6

            if not want_speak:
                print(f"[{name}] 选择不发言")
                continue

            if isinstance(agent, HumanAgent):
                if allow_human_speech:
                    content = "我没有更多要说的了。"
                else:
                    content = ""
            else:
                wolf_teammates = []
                if role == "狼人":
                    wolf_teammates = self.role_manager.get_alive_by_role("狼人", self.alive_players)
                try:
                    content = agent.speak(
                        game_state,
                        wolf_teammates=wolf_teammates,
                        round_num=100,  # 特殊轮次标识平票后发言
                        previous_speeches=[],
                    )
                except Exception as e:
                    content = f"我觉得{', '.join([str(c) + '号' for c in candidates])}里面有问题。"

            print(f"[{name}] {content}")
            memory_content = f"{pid}号玩家(评论): {content}"
            self._distribute_info_to_memories(
                "speak", memory_content,
                target=pid, visibility="public",
                player_id=pid,
                round_num=100,
                position=1,
                total_speakers=len(others_order),
            )
            self._add_event("speak", pid, content, role=role)
            speeches.append({"player_id": pid, "name": name, "content": content, "is_pk": False})

        return speeches

    # === CLI 游戏循环 ===

    def run(self) -> str:
        """CLI游戏主循环：夜晚 → 白天多轮讨论 → 投票 → 循环
        
        胜负判定规则：
        1. 夜晚行动后检查：若满足胜负条件，在白天讨论前直接宣布结果
        2. 投票阶段后检查：若满足胜负条件，在投票结果出来后直接宣布结果
        """
        while True:
            phase = self.phase_controller.current_phase

            if phase == Phase.NIGHT:
                self.night_step()
                
                # 夜晚行动后检查胜负，若满足条件则在白天讨论前宣布
                winner = self.rule_checker.check_win_condition(self.alive_players)
                if winner:
                    self.winner = winner
                    self._add_event("system", "game_end", f"游戏结束，{self.winner}获胜")
                    return self.winner
            elif phase == Phase.DAY:
                self.discussion_phase()
            elif phase == Phase.VOTE:
                self.vote_step()
                
                # 投票阶段结束后检查胜负
                winner = self.rule_checker.check_win_condition(self.alive_players)
                if winner:
                    self.winner = winner
                    self._add_event("system", "game_end", f"游戏结束，{self.winner}获胜")
                    return self.winner
            elif phase == Phase.ENDED:
                break

        self.winner = self.rule_checker.check_win_condition(self.alive_players)
        self._add_event("system", "game_end", f"游戏结束，{self.winner}获胜")
        return self.winner

    # === 内部辅助 ===

    def _kill_players(self, dead_list: List[int], show_role: bool = False):
        """处决玩家
        
        Args:
            dead_list: 死亡玩家列表
            show_role: 是否显示身份（投票出局时显示，夜晚死亡不显示）
        """
        for pid in dead_list:
            if pid in self.alive_players:
                self.alive_players.remove(pid)
                role = self.role_manager.get_player_role(pid)
                name = self.role_manager.player_names.get(pid, f"玩家{pid}")
                self._add_event("kill", pid, f"{pid}号玩家死亡", role=role)
                if show_role:
                    print(f"[KILL] {name} 死亡 (身份: {role})")
                else:
                    print(f"[KILL] {name} 死亡")

    def _add_event(self, event_type: str, player_id: int, content: str,
                   role: str = None, target: int = None):
        """添加事件到历史"""
        event = {
            "type": event_type,
            "player_id": player_id,
            "content": content,
        }
        if role:
            event["role"] = role
        if target is not None:
            event["target"] = target
        self.history.append(event)

    def _build_vote_summary_data(self, vote_details: dict, votes: dict) -> dict:
        """构建投票汇总结构化数据（供前端渲染可视化面板）

        Returns:
            {
                "voters": [{"id": 1, "name": "玩家1", "target": 3, "target_name": "玩家3", "is_abstain": false}, ...],
                "results": [{"id": 3, "name": "玩家3", "count": 2}, ...],
                "total_voters": 6
            }
        """
        alive = sorted(self.alive_players)
        voters = []
        for pid in alive:
            name = self.role_manager.player_names.get(pid, f"玩家{pid}")
            target = vote_details.get(pid)  # None = 弃权
            if target is not None:
                tname = self.role_manager.player_names.get(target, f"玩家{target}")
                voters.append({
                    "id": pid, "name": name,
                    "target": target, "target_name": tname,
                    "is_abstain": False,
                })
            else:
                voters.append({
                    "id": pid, "name": name,
                    "target": None, "target_name": None,
                    "is_abstain": True,
                })

        results = []
        if votes:
            for target, count in sorted(votes.items(), key=lambda x: -x[1]):
                tname = self.role_manager.player_names.get(target, f"玩家{target}")
                results.append({"id": target, "name": tname, "count": count})

        return {
            "voters": voters,
            "results": results,
            "total_voters": len(alive),
        }

    def _yield_vote_summary(self, vote_details: dict, votes: dict) -> dict:
        """生成投票汇总数据，分发到记忆和历史，返回结构化数据"""
        data = self._build_vote_summary_data(vote_details, votes)
        # 构建纯文本版本用于记忆和历史记录
        text_parts = []
        for v in data["voters"]:
            if v["is_abstain"]:
                text_parts.append(f"{v['name']}({v['id']}号)→弃权")
            else:
                text_parts.append(f"{v['name']}({v['id']}号)→{v['target_name']}({v['target']}号)")
        text_msg = "📊 投票: " + " | ".join(text_parts)
        if data["results"]:
            rp = [f"{r['name']}({r['id']}号){r['count']}票" for r in data["results"]]
            text_msg += "  |  结果: " + " | ".join(rp)
        else:
            text_msg += "  |  结果: 无人投票"

        self._distribute_info_to_memories(
            "vote_summary", text_msg,
            visibility="public", day=self.phase_controller.day,
        )
        self._add_event("vote_summary", -1, text_msg)
        return data

    def _trigger_belief_audit(self, new_evidence: List[dict], trigger_reason: str = ""):
        """新证据出现时，触发所有 AI Agent 的信念审计

        信念审计会：
        1. 基于新角色揭示重新评估旧判断
        2. 衰减过时的信念置信度
        3. 标记低置信度的极端判断

        Args:
            new_evidence: [{"type": "death_role_reveal", "player_id": 3, "role": "预言家"}, ...]
            trigger_reason: 触发原因（用于日志）
        """
        from agents.react_agent import ReActWerewolfAgent

        for pid, agent in self.agents.items():
            if pid not in self.alive_players:
                continue
            if not isinstance(agent, ReActWerewolfAgent):
                continue

            try:
                revisions = agent.memory.belief_tracker.audit_beliefs(
                    new_evidence=new_evidence,
                    current_day=self.phase_controller.day,
                    alive_players=self.alive_players,
                )
                if revisions:
                    # 将修正记录注入 Agent 私有记忆（作为内部反思）
                    for rev in revisions:
                        agent.memory.add_memory(
                            "system",
                            f"[内部反思] {rev}",
                            {"day": self.phase_controller.day,
                             "phase": "belief_audit",
                             "trigger": trigger_reason}
                        )
            except Exception as e:
                # 信念审计失败不应阻断游戏
                pass

    def get_winner(self) -> Optional[str]:
        return self.winner

    def is_game_over(self) -> bool:
        return self.rule_checker.check_win_condition(self.alive_players) is not None

    def get_state_for_llm(self) -> Dict:
        return self.get_game_state()
