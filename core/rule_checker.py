"""游戏规则校验"""
from typing import List, Optional, Dict, Tuple
from .role_manager import RoleManager


class RuleChecker:
    """规则检查器 - 判定胜负、游戏状态"""

    def __init__(self, role_manager: RoleManager):
        self.role_manager = role_manager

    def check_win_condition(self, alive_players: List[int]) -> Optional[str]:
        """检查胜负条件

        Args:
            alive_players: 存活玩家ID列表

        Returns:
            Optional[str]: '好人' / '狼人' / None（游戏继续）
        """
        wolf_count = self.role_manager.get_wolf_count(alive_players)
        good_count = len(alive_players) - wolf_count

        # 狼人全部死亡 -> 好人胜利
        if wolf_count == 0:
            return "好人"

        # 狼人数量 >= 好人数量 -> 狼人胜利
        if wolf_count >= good_count:
            return "狼人"

        # 游戏继续
        return None

    def can_eliminate(self, target: int, alive_players: List[int]) -> bool:
        """检查是否可以放逐指定玩家"""
        return target in alive_players

    def can_night_action(self, player_id: int, role: str, alive_players: List[int]) -> bool:
        """检查玩家是否可以执行夜晚操作"""
        return player_id in alive_players

    def is_valid_vote(self, voter: int, target: int, alive_players: List[int]) -> bool:
        """检查投票是否有效"""
        return target in alive_players and voter != target

    def get_night_action_result(
        self,
        werewolf_target: Optional[int],
        witch_save: bool,
        witch_poison: Optional[int],
        alive_players: List[int]
    ) -> Tuple[List[int], List[int]]:
        """计算夜晚死亡结果

        Args:
            werewolf_target: 狼人击杀目标
            witch_save: 女巫是否救人
            witch_poison: 女巫毒人目标
            alive_players: 存活玩家列表

        Returns:
            Tuple[List[int], List[int]]: (死亡列表, 救人列表)
        """
        killed = []
        saved = []

        # 处理狼人击杀
        if werewolf_target is not None and werewolf_target in alive_players:
            if witch_save:
                saved.append(werewolf_target)
            else:
                killed.append(werewolf_target)

        # 处理女巫毒人
        if witch_poison is not None and witch_poison in alive_players:
            if witch_poison not in killed:
                killed.append(witch_poison)

        return killed, saved

    def eliminate_players(self, to_kill: List[int], alive_players: List[int]) -> List[int]:
        """执行玩家死亡

        Args:
            to_kill: 待处死的玩家ID列表
            alive_players: 当前存活玩家列表

        Returns:
            List[int]: 新的存活玩家列表
        """
        return [p for p in alive_players if p not in to_kill]

    def is_night_phase_over(
        self,
        werewolf_done: bool,
        seer_done: bool,
        witch_done: bool
    ) -> bool:
        """检查夜晚阶段是否结束"""
        # 所有角色都完成夜晚行动后结束
        return werewolf_done and seer_done and witch_done

    def get_valid_targets(self, player_id: int, role: str, alive_players: List[int]) -> List[int]:
        """获取有效目标列表"""
        return [p for p in alive_players if p != player_id]

    def check_double_werewolf_win(self, alive_players: List[int]) -> bool:
        """检查狼人双杀获胜（狼人数量>=好人数量时）"""
        wolf_count = self.role_manager.get_wolf_count(alive_players)
        good_count = len(alive_players) - wolf_count
        return wolf_count >= good_count

    def can_continue_game(self, alive_players: List[int]) -> bool:
        """检查游戏是否可以继续"""
        return len(alive_players) >= 2

    def get_game_summary(self, alive_players: List[int]) -> Dict[str, int]:
        """获取游戏状态摘要"""
        wolf_count = self.role_manager.get_wolf_count(alive_players)
        good_count = len(alive_players) - wolf_count
        return {
            "total": len(alive_players),
            "wolves": wolf_count,
            "good": good_count,
        }