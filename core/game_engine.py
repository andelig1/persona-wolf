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
from utils.logger import reset_logger


class GameEngine:
    """游戏引擎 - 裁判模式"""

    def __init__(self, num_players: int = 4, human_player_id: int = 1):
        self.num_players = num_players
        self.human_player_id = 1

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

    def night_step(self, human_actions: dict = None) -> dict:
        """执行夜晚阶段

        Args:
            human_actions: 人类玩家的夜晚行动，如
                {"werewolf_target": int, "seer_target": int,
                 "witch_save": bool, "witch_poison": int}
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
        saved = False
        poisoned = None

        # ==================== 狼人睁眼阶段 ====================
        wolves = self.role_manager.get_alive_by_role("狼人", self.alive_players)
        if wolves:
            wolf_agent = self.agents[wolves[0]]
            
            print("\n" + "-" * 40)
            print("🐺 狼人请睁眼...")
            print("-" * 40)
            
            if isinstance(wolf_agent, HumanAgent):
                teammates = [f"{p}号" for p in wolves if p != self.human_player_id]
                if teammates:
                    print(f"   狼人请确定你的同伴: {', '.join(teammates)}")
                print(f"   存活玩家: {[p for p in self.alive_players if p != self.human_player_id]}")
                
                target = human_actions.get("werewolf_target")
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
                print(f"\n   狼人确定要刀的对象: {target} 号玩家")
            else:
                action = wolf_agent.night_action(game_state, wolf_teammates=wolves)
                if action and action.get("type") == "kill":
                    self.werewolf_kill_target = action.get("target")
                    print(f"\n   狼人确定要刀的对象: {self.werewolf_kill_target} 号玩家")
            
            if self.werewolf_kill_target is not None:
                self._distribute_info_to_memories(
                    "kill", f"狼人选择击杀{self.werewolf_kill_target}号",
                    target=self.werewolf_kill_target, visibility="werewolf",
                    player_id=wolves[0],
                )
            
            print("\n🐺 确认完毕，狼人请闭眼...")
        else:
            print("\n🐺 狼人已全部出局，无人睁眼")

        # ==================== 预言家睁眼阶段 ====================
        seers = self.role_manager.get_alive_by_role("预言家", self.alive_players)
        print("\n" + "-" * 40)
        print("🔮 预言家请睁眼...")
        print("-" * 40)
        
        if seers:
            seer_agent = self.agents[seers[0]]

            if isinstance(seer_agent, HumanAgent):
                print(f"   存活玩家: {[p for p in self.alive_players if p != self.human_player_id]}")
                
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
            
            print("\n🔮 预言家请闭眼...")
        else:
            print("   预言家已出局，无人睁眼")

        # ==================== 女巫睁眼阶段 ====================
        witches = self.role_manager.get_alive_by_role("女巫", self.alive_players)
        print("\n" + "-" * 40)
        print("🧪 女巫请睁眼...")
        print("-" * 40)
        
        if witches:
            witch_agent = self.agents[witches[0]]
            saved_this_night = False
            
            if isinstance(witch_agent, HumanAgent):
                save_status = "有" if self.witch_has_save else "无"
                poison_status = "有" if self.witch_has_poison else "无"
                print(f"   你的药水: 解药[{save_status}] 毒药[{poison_status}]")
                
                if self.werewolf_kill_target is not None:
                    print(f"\n   夜里，{self.werewolf_kill_target} 号玩家被狼人袭击了...")
                    
                    if self.witch_has_save:
                        choice = human_actions.get("witch_save_choice")
                        if choice is None:
                            choice = input("\n   请问你是否要使用解药救人？(y/n): ").lower()
                        if choice == 'y':
                            saved = True
                            saved_this_night = True
                            self.witch_has_save = False
                            print(f"\n   ✓ 女巫使用解药，救活了 {self.werewolf_kill_target} 号玩家")
                            print("   ⚠️ 已使用解药，本晚无法再使用毒药")
                    else:
                        print("\n   ⚠️ 解药已使用，无法救人")
                
                if not saved_this_night and self.witch_has_poison:
                    choice = human_actions.get("witch_poison")
                    if choice is None:
                        choice = input("\n   请问你是否需要使用毒药？(y/n): ").lower()
                    if choice == 'y':
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
                            print(f"\n   ✓ 女巫使用毒药，毒杀了 {poisoned} 号玩家")
                
                if not saved_this_night and not poisoned:
                    if not self.witch_has_save and not self.witch_has_poison:
                        pass
                    elif self.werewolf_kill_target is None:
                        print("\n   今晚是平安夜，女巫无需行动")
                    else:
                        print("\n   女巫选择不使用药水")
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
                        print(f"\n   ✓ 女巫使用解药，救活了 {self.werewolf_kill_target} 号玩家")
                    elif action.get("type") == "poison" and self.witch_has_poison:
                        pt = action.get("target")
                        if pt and pt in self.alive_players:
                            poisoned = pt
                            self.witch_has_poison = False
                            print(f"\n   ✓ 女巫使用毒药，毒杀了 {pt} 号玩家")
                else:
                    if not self.witch_has_save and not self.witch_has_poison:
                        pass
                    elif self.werewolf_kill_target is None:
                        print("\n   今晚是平安夜，女巫无需行动")
                    else:
                        print("\n   女巫选择不使用药水")
            
            print("\n🧪 女巫请闭眼...")
        else:
            print("   女巫已出局，无人睁眼")

        # 应用死亡
        dead = []
        if self.werewolf_kill_target is not None and not saved:
            dead.append(self.werewolf_kill_target)
        if poisoned is not None and poisoned in self.alive_players and poisoned not in dead:
            dead.append(poisoned)

        # 记录昨晚死亡的玩家，用于计算发言顺序
        self.last_night_dead = sorted(dead) if dead else []

        if dead:
            self._kill_players(dead)

        # 夜晚结果分发给所有存活Agent（标准规则：不公开身份）
        if dead:
            dead_names = [f"{p}号" for p in dead]
            self._distribute_info_to_memories(
                "death", f"第{self.phase_controller.day-1}晚{', '.join(dead_names)}死亡",
                visibility="public",
                day=self.phase_controller.day-1,
            )
        else:
            self._distribute_info_to_memories(
                "death", f"第{self.phase_controller.day-1}晚是平安夜，没有人死亡",
                visibility="public",
                day=self.phase_controller.day-1,
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

    def _get_speaking_order(self) -> list:
        """计算发言顺序：
        - 从昨晚死亡玩家后面的位置开始发言
        - 若当晚多人死亡则选择位置较前的玩家后面开始发言
        - 当晚无人死亡则从玩家1开始发言
        """
        alive = sorted(self.alive_players)
        
        if self.last_night_dead:
            # 选择位置最靠前的死亡玩家
            first_dead = min(self.last_night_dead)
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
            # 无人死亡，从玩家1开始
            if 1 in alive:
                start_idx = alive.index(1)
            else:
                start_idx = 0

        # 生成发言顺序（从start_idx开始，循环整个存活列表）
        order = alive[start_idx:] + alive[:start_idx]
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

    def vote_step(self, human_vote: int = None, tie_candidates: list = None) -> dict:
        """执行投票阶段

        Args:
            human_vote: 人类玩家的投票目标
            tie_candidates: 平票候选人（用于平票重投）
        Returns:
            投票结果 dict
        """
        print("\n" + "=" * 45)
        print(f"🗳️ [VOTE] 第 {self.phase_controller.day} 天 - 投票阶段")
        print("=" * 45)

        game_state = self.get_game_state()
        votes: Dict[int, int] = {}       # target -> count
        vote_details: Dict[int, int] = {} # voter -> target

        # 确定可投票目标（平票重投时只能投平票候选人）
        valid_targets = tie_candidates if tie_candidates else self.alive_players

        for pid in self.alive_players:
            agent = self.agents[pid]
            name = self.role_manager.player_names.get(pid, f"玩家{pid}")
            role = self.role_manager.get_player_role(pid)

            if isinstance(agent, HumanAgent):
                target = human_vote
                if target is None:
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
            else:
                wolf_teammates = []
                if role == "狼人":
                    wolf_teammates = self.role_manager.get_alive_by_role("狼人", self.alive_players)
                try:
                    # 平票重投时限制AI只能投平票候选人
                    if tie_candidates:
                        target = agent.vote(game_state, wolf_teammates=wolf_teammates, vote_options=tie_candidates)
                    else:
                        target = agent.vote(game_state, wolf_teammates=wolf_teammates)
                except Exception:
                    others = [p for p in valid_targets if p != pid]
                    target = random.choice(others) if others else None

            if target is not None and target in valid_targets and target != pid:
                votes[target] = votes.get(target, 0) + 1
                vote_details[pid] = target

                # 显示投票（人类玩家显示为"玩家X（你）"）
                if isinstance(agent, HumanAgent):
                    display_name = f"玩家{pid}（你）"
                else:
                    display_name = name
                print(f"   ✓ [{display_name}] 投票给了 {target} 号")

                # 分发投票信息
                self._distribute_info_to_memories(
                    "vote", f"{pid}号玩家投票给{target}号玩家",
                    target=target, visibility="public",
                    player_id=pid,
                    day=self.phase_controller.day,
                )
            else:
                # 弃权
                if isinstance(agent, HumanAgent):
                    display_name = f"玩家{pid}（你）"
                else:
                    display_name = name
                print(f"   ○ [{display_name}] 弃权")

                self._distribute_info_to_memories(
                    "vote", f"{pid}号玩家弃权",
                    visibility="public",
                    player_id=pid,
                    day=self.phase_controller.day,
                )

        # 计票
        eliminated = None
        tie_count = 0
        max_tie_rounds = 3  # 最多平票3轮

        # 全员弃权 → 直接跳过
        if not votes:
            print(f"\n🫱 本轮无人投票，直接跳过投票阶段")
            self._distribute_info_to_memories(
                "system", "本轮无人投票，跳过投票阶段",
                visibility="public",
                day=self.phase_controller.day,
            )

        while tie_count < max_tie_rounds and eliminated is None:
            if votes:
                max_votes = max(votes.values())
                candidates = [p for p, v in votes.items() if v == max_votes]
                print(f"\n📊 投票结果: {votes}")

                # 参与投票人数 < 存活人数/3 → 不触发淘汰
                voters_count = len(vote_details)
                threshold = len(self.alive_players) // 3
                if voters_count < threshold:
                    print(f"   ⊘ 仅{voters_count}人投票（需≥{threshold}人），不触发淘汰")
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
                else:
                    tie_count += 1
                    print(f"\n⚖️ 平票: {candidates}，进入第 {tie_count} 轮PK发言")
                    
                    # 增加平票玩家嫌疑度
                    for candidate in candidates:
                        for pid, agent in self.agents.items():
                            if pid in self.alive_players:
                                agent.memory.update_suspicion(candidate, 0.1, "平票嫌疑")
                    
                    # 平票PK发言（逆序）
                    self._tie_break_speech(candidates)
                    
                    # 其余玩家发言环节（按原发言顺序的倒序）
                    self._tie_break_others_speech(candidates)
                    
                    # 重新投票（仅平票候选人）
                    print(f"\n🔄 --- 第 {tie_count} 轮重新投票 ---")
                    print(f"   ├─ 仅可投票给平票候选人: {candidates}")
                    print(f"   └─ 存活玩家: {self.alive_players}")
                    votes.clear()
                    vote_details.clear()
                    
                    # 确保遍历所有存活玩家，包括平票候选人
                    for pid in self.alive_players:
                        agent = self.agents[pid]
                        name = self.role_manager.player_names.get(pid, f"玩家{pid}")
                        role = self.role_manager.get_player_role(pid)

                        if isinstance(agent, HumanAgent):
                            # 人类玩家投票
                            # 如果是人类玩家是平票候选人，可以投自己或其他人
                            # 如果不是平票候选人，只能投其他人
                            if pid in candidates:
                                valid_vote = [c for c in candidates if c != self.human_player_id or c == pid]
                                prompt = f"   选择投票目标 (可选: {valid_vote}, 0=弃权): "
                                while True:
                                    try:
                                        raw = input(prompt)
                                        if raw.strip() in ("", "0", "弃权", "skip", "pass"):
                                            target = None
                                            break
                                        target = int(raw)
                                        if target in candidates and (target != self.human_player_id or pid in candidates):
                                            break
                                        print("   ❌ 无效选择")
                                    except ValueError:
                                        print("   ❌ 请输入数字或0弃权")
                            else:
                                # 非平票候选人只能投平票候选人（不包括自己）
                                while True:
                                    try:
                                        raw = input("   选择投票目标 (0=弃权): ")
                                        if raw.strip() in ("", "0", "弃权", "skip", "pass"):
                                            target = None
                                            break
                                        target = int(raw)
                                        if target in candidates and target != self.human_player_id:
                                            break
                                        print("   ❌ 无效选择，只能投票给平票候选人")
                                    except ValueError:
                                        print("   ❌ 请输入数字或0弃权")
                        else:
                            # AI玩家投票
                            wolf_teammates = []
                            if role == "狼人":
                                wolf_teammates = self.role_manager.get_alive_by_role("狼人", self.alive_players)
                            try:
                                target = agent.vote(game_state, wolf_teammates=wolf_teammates, vote_options=candidates)
                            except Exception:
                                others = [p for p in candidates if p != pid]
                                target = random.choice(others) if others else None

                        if target is not None and target in candidates:
                            votes[target] = votes.get(target, 0) + 1
                            vote_details[pid] = target
                            
                            # 显示投票（人类玩家显示为"玩家X（你）"）
                            if isinstance(agent, HumanAgent):
                                display_name = f"玩家{pid}（你）"
                            else:
                                display_name = name
                            print(f"   ✓ [{display_name}] 投票给了 {target} 号")
                            
                            # 分发投票信息
                            self._distribute_info_to_memories(
                                "vote", f"{pid}号玩家投票给{target}号玩家",
                                target=target, visibility="public",
                                player_id=pid,
                                day=self.phase_controller.day,
                            )

        # 平票三轮未决 → 无人出局
        if eliminated is None and tie_count >= 3:
            print(f"\n⚖️ 平票三轮未决，无人被投票出局")
            self._distribute_info_to_memories(
                "system", "平票三轮未决，无人被投票出局",
                visibility="public",
                day=self.phase_controller.day,
            )

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

    def _tie_break_speech(self, candidates: list) -> list:
        """平票PK发言环节
        
        Args:
            candidates: 平票候选人列表
        Returns:
            平票玩家的发言顺序（用于确定其余玩家发言顺序）
        """
        print("\n--- 平票PK发言环节 ---")
        game_state = self.get_game_state()

        # 按原发言顺序的逆序发言
        speaking_order = self._get_speaking_order()
        # 只保留平票候选人，按原顺序的逆序排列
        candidate_order = [p for p in speaking_order if p in candidates]
        candidate_order.reverse()

        for pid in candidate_order:
            agent = self.agents[pid]
            name = self.role_manager.player_names.get(pid, f"玩家{pid}")
            role = self.role_manager.get_player_role(pid)

            print(f"\n[{name}] (平票PK)")
            if isinstance(agent, HumanAgent):
                content = input("请输入PK发言: ")
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
        
        return candidate_order

    def _tie_break_others_speech(self, candidates: list):
        """平票PK后其余玩家发言环节
        
        Args:
            candidates: 平票候选人列表
        """
        # 获取非候选人玩家
        others = [p for p in self.alive_players if p not in candidates]
        if not others:
            return
        
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
        
        for pid in others_order:
            agent = self.agents[pid]
            name = self.role_manager.player_names.get(pid, f"玩家{pid}")
            role = self.role_manager.get_player_role(pid)

            print(f"\n[{name}]")
            
            # 询问是否发言
            want_speak = False
            if isinstance(agent, HumanAgent):
                choice = input("是否发言？(y/n): ").lower()
                want_speak = (choice == 'y')
            else:
                # AI玩家有60%概率发言
                want_speak = random.random() < 0.6
            
            if not want_speak:
                print(f"[{name}] 选择不发言")
                continue
            
            if isinstance(agent, HumanAgent):
                content = input("请输入发言: ")
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

    def get_winner(self) -> Optional[str]:
        return self.winner

    def is_game_over(self) -> bool:
        return self.rule_checker.check_win_condition(self.alive_players) is not None

    def get_state_for_llm(self) -> Dict:
        return self.get_game_state()
