"""游戏引擎 - 裁判模式

负责：分配角色、分发信息到Agent记忆、调用Agent、验证结果、判定胜负
不再直接控制Agent行为，每个AI Agent通过ReAct推理自主决策
"""
import random
from typing import List, Dict, Optional, Tuple

from .phase_controller import Phase, PhaseController
from .role_manager import RoleManager
from .rule_checker import RuleChecker
from agents.react_agent import ReActWerewolfAgent
from agents.human_agent import HumanAgent
from agents.base_agent import BaseAgent
from memory.event_recorder import EventRecorder


class GameEngine:
    """游戏引擎 - 裁判模式"""

    def __init__(self, num_players: int = 4, human_player_id: int = 0):
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
        self._create_agents()
        self.alive_players = list(range(self.num_players))
        self.phase_controller.start_game()
        self.history = []
        self.event_recorder.clear()

        # 给每个Agent记录初始信息
        for pid in range(self.num_players):
            role = self.role_manager.get_player_role(pid)
            agent = self.agents[pid]
            agent.memory.add_memory(
                "phase_change",
                f"游戏开始，你是{pid}号玩家，身份是{role}",
                {"day": 0, "phase": "start", "player_id": pid}
            )

    def _create_agents(self):
        """创建Agent：AI用ReActWerewolfAgent，人类用HumanAgent"""
        # 加权随机：理性/煽动型更常见，划水型较少
        personality_weights = {
            "rational": 4,
            "agitative": 3,
            "conservative": 2,
            "impulsive": 2,
            "slacker": 1,
        }
        pool = []
        for p, w in personality_weights.items():
            pool.extend([p] * w)

        for pid in range(self.num_players):
            role = self.role_manager.get_player_role(pid)
            name = self.role_manager.player_names.get(pid, f"玩家{pid}")

            if pid == self.human_player_id:
                self.agents[pid] = HumanAgent(pid, role, name)
            else:
                personality = random.choice(pool)
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
                                      player_id: int = -1):
        """推送游戏事件到相关Agent的记忆"""
        day = day or self.phase_controller.day

        # 记录到全局事件日志
        self.event_recorder.record(
            event_type, player_id, content,
            target=target, day=day,
            phase=self.phase_controller.current_phase.value,
            visibility=visibility,
        )

        # 分发到相关Agent的记忆
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
                agent.memory.add_memory(
                    event_type, content,
                    {"day": day, "target": target, "player_id": player_id}
                )

    # === 阶段方法（供CLI run()和API层调用）===

    def night_step(self, human_actions: dict = None) -> dict:
        """执行夜晚阶段

        Args:
            human_actions: 人类玩家的夜晚行动，如
                {"werewolf_target": int, "seer_target": int,
                 "witch_save": bool, "witch_poison": int}
        Returns:
            夜晚结果 dict
        """
        print("\n" + "=" * 40)
        print("[NIGHT] 第 {0} 天 - 夜晚".format(self.phase_controller.day))
        print("=" * 40)

        self.werewolf_kill_target = None
        self.seer_check_result = None
        game_state = self.get_game_state()
        human_actions = human_actions or {}
        saved = False
        poisoned = None

        # 1. 狼人杀人
        wolves = self.role_manager.get_alive_by_role("狼人", self.alive_players)
        if wolves:
            wolf_agent = self.agents[wolves[0]]

            if isinstance(wolf_agent, HumanAgent):
                # CLI模式：人类狼人输入
                target = human_actions.get("werewolf_target")
                if target is None:
                    # 显示队友信息
                    teammates = [f"{p}号" for p in wolves if p != self.human_player_id]
                    if teammates:
                        print(f"\n你是狼人！你的队友: {', '.join(teammates)}")
                    print(f"存活玩家: {[p for p in self.alive_players if p != self.human_player_id]}")
                    while True:
                        try:
                            target = int(input("选择击杀目标: "))
                            if target in self.alive_players and target not in wolves:
                                break
                            print("无效选择（不能杀自己或队友）")
                        except ValueError:
                            print("请输入数字")
                self.werewolf_kill_target = target
            else:
                # AI狼人 ReAct推理
                action = wolf_agent.night_action(game_state, wolf_teammates=wolves)
                if action and action.get("type") == "kill":
                    self.werewolf_kill_target = action.get("target")

            if self.werewolf_kill_target is not None:
                print(f"狼人选择了击杀: {self.werewolf_kill_target} 号玩家")
                self._distribute_info_to_memories(
                    "kill", f"狼人选择击杀{self.werewolf_kill_target}号",
                    target=self.werewolf_kill_target, visibility="werewolf",
                    player_id=wolves[0],
                )

        # 2. 预言家查验
        seers = self.role_manager.get_alive_by_role("预言家", self.alive_players)
        if seers:
            seer_agent = self.agents[seers[0]]

            if isinstance(seer_agent, HumanAgent):
                target = human_actions.get("seer_target")
                if target is None:
                    print(f"\n你是预言家！存活玩家: {[p for p in self.alive_players if p != self.human_player_id]}")
                    while True:
                        try:
                            target = int(input("选择查验目标: "))
                            if target in self.alive_players and target != seers[0]:
                                break
                            print("无效选择")
                        except ValueError:
                            print("请输入数字")
                role = self.role_manager.get_player_role(target)
                self.seer_check_result = (target, role)
                seer_agent.memory.set_role_knowledge(target, role)
                seer_agent.memory.add_memory(
                    "check_result", f"你查验了{target}号，身份是{role}",
                    {"day": self.phase_controller.day, "target": target}
                )
                print(f"[SEER] 查验结果: {target} 号玩家是 {role}")
            else:
                # AI预言家 ReAct推理
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
                        print(f"[SEER] 预言家查验了 {target} 号，身份是 {role}")

        # 3. 女巫救人/毒人
        witches = self.role_manager.get_alive_by_role("女巫", self.alive_players)
        if witches:
            witch_agent = self.agents[witches[0]]

            if isinstance(witch_agent, HumanAgent):
                # CLI模式
                if self.werewolf_kill_target is not None and self.witch_has_save:
                    print(f"\n{self.werewolf_kill_target}号被狼人袭击了！是否救人？(y/n)")
                    choice = human_actions.get("witch_save_choice")
                    if choice is None:
                        choice = input().lower()
                    if choice == 'y':
                        saved = True
                        self.witch_has_save = False
                        print(f"女巫救活了 {self.werewolf_kill_target} 号玩家")

                if self.witch_has_poison:
                    poison_choice = human_actions.get("witch_poison")
                    if poison_choice is None:
                        choice = input("是否使用毒药？(y/n): ").lower()
                        if choice == 'y':
                            poison_choice = int(input("毒杀目标: "))
                    if poison_choice and poison_choice in self.alive_players:
                        poisoned = poison_choice
                        self.witch_has_poison = False
                        print(f"女巫毒杀了 {poisoned} 号玩家")
            else:
                # AI女巫 ReAct推理
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
                        print(f"女巫救活了 {self.werewolf_kill_target} 号玩家")
                    elif action.get("type") == "poison" and self.witch_has_poison:
                        pt = action.get("target")
                        if pt and pt in self.alive_players:
                            poisoned = pt
                            self.witch_has_poison = False
                            print(f"女巫毒杀了 {pt} 号玩家")

        # 4. 应用死亡
        dead = []
        if self.werewolf_kill_target is not None and not saved:
            dead.append(self.werewolf_kill_target)
        if poisoned is not None and poisoned in self.alive_players and poisoned not in dead:
            dead.append(poisoned)

        if dead:
            self._kill_players(dead)

        # 夜晚结果分发给所有存活Agent
        if dead:
            dead_names = [f"{p}号" for p in dead]
            self._distribute_info_to_memories(
                "death", f"昨晚{', '.join(dead_names)}死亡",
                visibility="public",
            )
        else:
            self._distribute_info_to_memories(
                "death", "昨晚是平安夜，没有人死亡",
                visibility="public",
            )

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

    def day_step(self, human_speech: str = None, round_num: int = 1,
                 previous_speeches: list = None) -> dict:
        """执行白天一轮发言（支持多轮讨论）

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

        for pid in self.alive_players:
            agent = self.agents[pid]
            role = self.role_manager.get_player_role(pid)
            name = self.role_manager.player_names.get(pid, f"玩家{pid}")

            if isinstance(agent, HumanAgent):
                content = human_speech
                if content is None:
                    print(f"\n[{name}] 你是 {role}")
                    content = input("请输入发言（输入 vote 进入投票）: ")
            else:
                wolf_teammates = []
                if role == "狼人":
                    wolf_teammates = self.role_manager.get_alive_by_role("狼人", self.alive_players)
                try:
                    content = agent.speak(
                        game_state,
                        wolf_teammates=wolf_teammates,
                        round_num=round_num,
                        previous_speeches=previous_speeches,
                    )
                except Exception as e:
                    content = agent.strategy.generate_speech(
                        agent.memory, game_state, agent.personality
                    )

            # 统一输出
            print(f"\n[{name}] {content}")

            speeches.append({"player_id": pid, "name": name, "content": content})

            # 分发发言到所有Agent记忆
            self._distribute_info_to_memories(
                "speak", f"{name}: {content}",
                target=pid, visibility="public",
                player_id=pid,
            )
            self._add_event("speak", pid, content, role=role)

        return {"speeches": speeches}

    def discussion_phase(self) -> list:
        """多轮讨论阶段：玩家和AI轮流发言，直到人类玩家决定进入投票

        Returns:
            所有轮次的发言列表
        """
        print("\n" + "=" * 40)
        print("[DAY] 第 {0} 天 - 白天讨论".format(self.phase_controller.day))
        print("=" * 40)

        # 第一轮：播报夜晚结果
        dead = [pid for pid in range(self.num_players)
                if pid not in self.alive_players]
        if dead:
            dead_info = [f"{pid}号({self.role_manager.get_player_role(pid)})"
                         for pid in dead]
            print(f"\n昨晚死亡: {', '.join(dead_info)}")
        else:
            print("\n昨晚是平安夜。")

        all_speeches = []
        round_num = 1

        while True:
            print(f"\n--- 第 {round_num} 轮发言 ---")
            result = self.day_step(round_num=round_num,
                                   previous_speeches=all_speeches)
            round_speeches = result["speeches"]
            all_speeches.extend(round_speeches)

            # 检查人类玩家是否想投票
            human_speech = ""
            for s in round_speeches:
                if s["player_id"] == self.human_player_id:
                    human_speech = s["content"].lower()
                    break

            if "vote" in human_speech or "投票" in human_speech:
                print("\n进入投票阶段！")
                break

            # 询问是否继续讨论
            print(f"\n--- 继续讨论还是投票？ ---")
            choice = input("输入发言继续讨论，输入 vote 进入投票: ").strip()
            if choice.lower() in ("vote", "投票"):
                print("\n进入投票阶段！")
                break
            elif choice:
                # 人类玩家追加发言
                name = self.role_manager.player_names.get(self.human_player_id, "你")
                print(f"[{name}] {choice}")
                self._distribute_info_to_memories(
                    "speak", f"{name}: {choice}",
                    target=self.human_player_id, visibility="public",
                    player_id=self.human_player_id,
                )
                self._add_event("speak", self.human_player_id, choice,
                                role=self.role_manager.get_player_role(self.human_player_id))
                all_speeches.append({
                    "player_id": self.human_player_id,
                    "name": name,
                    "content": choice,
                })

            round_num += 1
            # 防止无限循环
            if round_num > 5:
                print("\n讨论轮次已满，进入投票！")
                break

        self.phase_controller.next_phase()
        return all_speeches

    def vote_step(self, human_vote: int = None) -> dict:
        """执行投票阶段

        Args:
            human_vote: 人类玩家的投票目标
        Returns:
            投票结果 dict
        """
        print("\n" + "=" * 40)
        print("[VOTE] 第 {0} 天 - 投票阶段".format(self.phase_controller.day))
        print("=" * 40)

        game_state = self.get_game_state()
        votes: Dict[int, int] = {}       # target -> count
        vote_details: Dict[int, int] = {} # voter -> target

        for pid in self.alive_players:
            agent = self.agents[pid]
            name = self.role_manager.player_names.get(pid, f"玩家{pid}")
            role = self.role_manager.get_player_role(pid)

            if isinstance(agent, HumanAgent):
                target = human_vote
                if target is None:
                    print("\n存活玩家: {0}".format(self.alive_players))
                    while True:
                        try:
                            target = int(input("投票给: "))
                            if target in self.alive_players and target != self.human_player_id:
                                break
                            print("无效选择")
                        except ValueError:
                            print("请输入数字")
            else:
                wolf_teammates = []
                if role == "狼人":
                    wolf_teammates = self.role_manager.get_alive_by_role("狼人", self.alive_players)
                try:
                    target = agent.vote(game_state, wolf_teammates=wolf_teammates)
                except Exception:
                    others = [p for p in self.alive_players if p != pid]
                    target = random.choice(others) if others else None

            if target is not None and target in self.alive_players and target != pid:
                votes[target] = votes.get(target, 0) + 1
                vote_details[pid] = target
                print(f"[VOTE] {name} 投票给了 {target} 号")

                # 分发投票信息
                self._distribute_info_to_memories(
                    "vote", f"{name}投票给{target}号",
                    target=target, visibility="public",
                    player_id=pid,
                )

        # 计票
        eliminated = None
        if votes:
            max_votes = max(votes.values())
            candidates = [p for p, v in votes.items() if v == max_votes]
            print(f"\n投票结果: {votes}")

            if len(candidates) == 1:
                eliminated = candidates[0]
                role = self.role_manager.get_player_role(eliminated)
                name = self.role_manager.player_names.get(eliminated, f"玩家{eliminated}")
                print(f"\n[KILL] {name} ({role}) 被投票出局")
                self.alive_players.remove(eliminated)
                self._distribute_info_to_memories(
                    "eliminate", f"{name}被投票出局，身份是{role}",
                    target=eliminated, visibility="public",
                    player_id=eliminated,
                )
                self._add_event("eliminate", eliminated, f"{name}被投票出局", role=role)
            else:
                print(f"\n平票: {candidates}，无人出局")
                self._add_event("vote_tie", -1, f"平票: {candidates}")

        # 检查胜负
        winner = self.rule_checker.check_win_condition(self.alive_players)
        if winner:
            self.winner = winner
            self.phase_controller.end_game(winner)
        else:
            self.phase_controller.next_phase()

        return {
            "votes": votes,
            "vote_details": vote_details,
            "eliminated": eliminated,
            "game_over": winner is not None,
            "winner": winner,
        }

    # === CLI 游戏循环 ===

    def run(self) -> str:
        """CLI游戏主循环：夜晚 → 白天多轮讨论 → 投票 → 循环"""
        while not self.rule_checker.check_win_condition(self.alive_players):
            phase = self.phase_controller.current_phase

            if phase == Phase.NIGHT:
                self.night_step()
            elif phase == Phase.DAY:
                self.discussion_phase()
            elif phase == Phase.VOTE:
                self.vote_step()
            elif phase == Phase.ENDED:
                break

        self.winner = self.rule_checker.check_win_condition(self.alive_players)
        self._add_event("system", "game_end", f"游戏结束，{self.winner}获胜")
        return self.winner

    # === 内部辅助 ===

    def _kill_players(self, dead_list: List[int]):
        """处决玩家"""
        for pid in dead_list:
            if pid in self.alive_players:
                self.alive_players.remove(pid)
                role = self.role_manager.get_player_role(pid)
                name = self.role_manager.player_names.get(pid, f"玩家{pid}")
                self._add_event("kill", pid, f"{pid}号玩家死亡", role=role)
                print(f"[KILL] {name} 死亡 (身份: {role})")

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

    def get_winner(self) -> Optional[str]:
        return self.winner

    def is_game_over(self) -> bool:
        return self.rule_checker.check_win_condition(self.alive_players) is not None

    def get_state_for_llm(self) -> Dict:
        return self.get_game_state()
