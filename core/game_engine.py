"""极简版游戏引擎 - MVP"""
import random

class GameEngine:
    def __init__(self, agents):
        self.agents = {a.id: a for a in agents}
        self.alive_players = [a.id for a in agents]
        self.day = 1

    def get_state(self):
        return {"alive_players": self.alive_players, "day": self.day}

    def run(self):
        while not self.is_game_over():
            print(f"\n{'='*40}\n第 {self.day} 天\n{'='*40}")

            # 夜晚
            self.night_phase()
            if self.is_game_over(): break

            # 白天发言
            self.day_phase()
            if self.is_game_over(): break

            # 投票
            self.vote_phase()
            self.day += 1

        print(f"\n游戏结束！{self.get_winner()} 获胜！")
        return self.get_winner()

    def night_phase(self):
        print("\n🌙 夜晚阶段")

        # 狼人杀人
        wolves = [a for a in self.agents.values() if a.role == "狼人" and a.alive]
        werewolf_target = None

        if wolves:
            werewolf_target = wolves[0].night_action(self.get_state())
            if werewolf_target and werewolf_target in self.alive_players:
                print(f"狼人选择了 {werewolf_target} 号玩家")

                # 女巫救人
                witches = [a for a in self.agents.values() if a.role == "女巫" and a.alive]
                saved = False

                if witches:
                    saved = witches[0].night_action(self.get_state(), werewolf_target)
                    if saved:
                        print(f"女巫使用了解药，救活了 {werewolf_target} 号玩家")

                if not saved and werewolf_target in self.alive_players:
                    self.kill_player(werewolf_target)
                    print(f"💀 {werewolf_target} 号玩家死亡")
            else:
                print("狼人没有选择目标")

        # 预言家查验（简化版，只打印信息）
        seers = [a for a in self.agents.values() if a.role == "预言家" and a.alive]
        if seers:
            check_target = seers[0].night_action(self.get_state())
            if check_target and check_target in self.alive_players:
                target_role = self.agents[check_target].role
                print(f"🔮 预言家查验了 {check_target} 号，身份是 {target_role}")

    def day_phase(self):
        print("\n☀️ 白天阶段")
        for pid in self.alive_players:
            content = self.agents[pid].speak(self.get_state())
            print(f"玩家{pid}({self.agents[pid].role}): {content}")

    def vote_phase(self):
        print("\n🗳️ 投票阶段")
        votes = {}
        for pid in self.alive_players:
            target = self.agents[pid].vote(self.get_state())
            if target and target in self.alive_players:
                votes[target] = votes.get(target, 0) + 1
                print(f"玩家{pid} 投票给 {target}")

        if votes:
            max_votes = max(votes.values())
            candidates = [p for p, v in votes.items() if v == max_votes]

            if len(candidates) == 1:
                eliminated = candidates[0]
                print(f"\n💀 {eliminated} 号玩家被投票出局")
                self.kill_player(eliminated)
            else:
                print(f"\n平票: {candidates}，无人出局")

    def kill_player(self, pid):
        if pid in self.alive_players:
            self.alive_players.remove(pid)
            self.agents[pid].alive = False
            print(f"💀 {pid} 号玩家已死亡")

    def is_game_over(self):
        wolves = sum(1 for a in self.agents.values() if a.role == "狼人" and a.alive)
        goods = sum(1 for a in self.agents.values() if a.role != "狼人" and a.alive)

        print(f"\n[状态] 存活: {self.alive_players}, 狼人存活: {wolves}, 好人存活: {goods}")

        if wolves == 0:
            print("所有狼人已死亡！")
            return True
        if wolves >= goods:
            print("狼人数量 >= 好人数量！")
            return True
        return False

    def get_winner(self):
        wolves = sum(1 for a in self.agents.values() if a.role == "狼人" and a.alive)
        return "好人" if wolves == 0 else "狼人"