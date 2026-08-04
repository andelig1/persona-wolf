"""角色管理 - 分配角色给玩家"""
import random
from typing import List, Dict, Optional


class RoleManager:
    """角色管理器 - 负责角色分配和查询"""

    # 标准角色配置（4人局）
    DEFAULT_ROLES = ["狼人", "预言家", "女巫", "村民"]

    # 角色人数映射（根据总人数动态调整）
    ROLE_SCALES = {
        6: ["狼人", "狼人", "预言家", "女巫", "村民", "村民"],
        7: ["狼人", "狼人", "预言家", "女巫", "村民", "村民", "村民"],
        8: ["狼人", "狼人", "预言家", "女巫", "女巫", "村民", "村民", "村民"],
        9: ["狼人", "狼人", "狼人", "预言家", "女巫", "村民", "村民", "村民", "村民"],
        10: ["狼人", "狼人", "狼人", "预言家", "女巫", "女巫", "村民", "村民", "村民", "村民"],
    }

    def __init__(self):
        self.player_roles: Dict[int, str] = {}
        self.player_names: Dict[int, str] = {}
        self.role_agents: Dict[str, List[int]] = {}  # 角色 -> 玩家ID列表

    def assign_roles(self, num_players: int, human_player_id: int = 0) -> Dict[int, str]:
        """分配角色（随机）

        Args:
            num_players: 玩家数量
            human_player_id: 人类玩家ID

        Returns:
            Dict[int, str]: 玩家ID -> 角色
        """
        # 获取角色配置
        if num_players in self.ROLE_SCALES:
            roles = self.ROLE_SCALES[num_players].copy()
        else:
            roles = self._generate_roles(num_players)

        # 打乱角色顺序
        random.shuffle(roles)

        # 分配给玩家（从1开始编号）
        self.player_roles = {i + 1: roles[i] for i in range(num_players)}

        # 设置玩家名称（从1开始编号）
        self.player_names = {i + 1: f"玩家{i + 1}" for i in range(num_players)}
        if 1 <= human_player_id <= num_players:
            self.player_names[human_player_id] = "你"

        # 构建角色->玩家映射
        self._build_role_agents()

        return self.player_roles

    def assign_roles_with_human_choice(self, num_players: int, human_player_id: int = 1, human_role: str = None) -> Dict[int, str]:
        """分配角色（人类玩家可选身份）

        Args:
            num_players: 玩家数量
            human_player_id: 人类玩家ID
            human_role: 人类玩家选择的角色，为None则随机

        Returns:
            Dict[int, str]: 玩家ID -> 角色
        """
        # 获取角色配置
        if num_players in self.ROLE_SCALES:
            base_roles = self.ROLE_SCALES[num_players].copy()
        else:
            base_roles = self._generate_roles(num_players)

        # 如果玩家选择了身份，确保该身份在列表中
        if human_role and human_role in base_roles:
            base_roles.remove(human_role)
            random.shuffle(base_roles)
            # 人类玩家固定是1号
            final_roles = [human_role] + base_roles
        else:
            # 随机分配：确保每个角色类型概率均等
            role_counts = {}
            for r in base_roles:
                role_counts[r] = role_counts.get(r, 0) + 1
            
            unique_roles = list(role_counts.keys())
            min_count_per_role = 1
            fixed_count = len(unique_roles) * min_count_per_role
            
            if num_players >= fixed_count:
                # 每个角色类型先分配1个
                equal分配 = []
                for r in unique_roles:
                    equal分配.append(r)
                
                # 剩余名额从所有角色中随机补充
                remaining_slots = num_players - fixed_count
                extra_roles = random.sample(base_roles, min(remaining_slots, len(base_roles)))
                
                # 合并并打乱
                final_roles = equal分配 + extra_roles
                random.shuffle(final_roles)
            else:
                # 人数不足，只保留部分角色
                final_roles = random.sample(unique_roles, num_players)

        # 分配给玩家（从1开始编号）
        self.player_roles = {i + 1: final_roles[i] for i in range(num_players)}

        # 设置玩家名称（从1开始编号）
        self.player_names = {i + 1: f"玩家{i + 1}" for i in range(num_players)}
        if 1 <= human_player_id <= num_players:
            self.player_names[human_player_id] = "你"

        # 构建角色->玩家映射
        self._build_role_agents()

        return self.player_roles

    def _generate_roles(self, num_players: int) -> list:
        """根据人数动态生成角色配置"""
        roles = []
        # 狼人：大约1/4的比例
        wolves = max(1, num_players // 4)
        roles.extend(["狼人"] * wolves)

        # 预言家：1个
        roles.append("预言家")

        # 女巫：5人以上才有
        if num_players >= 5:
            roles.append("女巫")

        # 村民：填满剩余位置
        while len(roles) < num_players:
            roles.append("村民")

        return roles

    def _build_role_agents(self):
        """构建角色到玩家的映射"""
        self.role_agents = {}
        for pid, role in self.player_roles.items():
            if role not in self.role_agents:
                self.role_agents[role] = []
            self.role_agents[role].append(pid)

    def get_player_role(self, player_id: int) -> Optional[str]:
        """获取玩家角色"""
        return self.player_roles.get(player_id)

    def get_players_by_role(self, role: str) -> List[int]:
        """获取指定角色的所有玩家"""
        return self.role_agents.get(role, [])

    def get_alive_by_role(self, role: str, alive_players: List[int]) -> List[int]:
        """获取指定角色中存活的玩家"""
        all_players = self.get_players_by_role(role)
        return [p for p in all_players if p in alive_players]

    def get_wolf_count(self, alive_players: List[int] = None) -> int:
        """获取狼人数量"""
        wolves = self.get_players_by_role("狼人")
        if alive_players is None:
            return len(wolves)
        return len([w for w in wolves if w in alive_players])

    def get_good_count(self, alive_players: List[int] = None) -> int:
        """获取好人数量（不含狼人）"""
        if alive_players is None:
            alive_players = list(self.player_roles.keys())
        return len([p for p in alive_players if self.player_roles.get(p) != "狼人"])

    def get_all_roles(self) -> List[str]:
        """获取所有角色类型"""
        return list(self.role_agents.keys())

    def is_valid_role_config(self, num_players: int) -> bool:
        """检查角色配置是否有效"""
        return num_players >= 3  # 至少需要3人（1狼人+2好人）