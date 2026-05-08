"""投票管理器

管理投票流程和计票
"""
from typing import Dict, Tuple, List, Optional


class VoteManager:
    """投票管理器"""

    def collect_votes(self, agents: dict, alive_players: list,
                      human_player_id: int = 0,
                      human_vote: int = None) -> Dict[int, int]:
        """收集投票，返回 {voter_id: target_id}"""
        votes = {}
        for pid in alive_players:
            if pid == human_player_id:
                if human_vote is not None:
                    votes[pid] = human_vote
            else:
                agent = agents[pid]
                target = agent.vote({})
                if target is not None and target in alive_players and target != pid:
                    votes[pid] = target
        return votes

    def tally_votes(self, votes: Dict[int, int]) -> Tuple[Optional[int], Dict[int, int], bool]:
        """计票

        Returns:
            (eliminated_player_id, vote_counts, is_tie)
        """
        if not votes:
            return None, {}, False

        counts: Dict[int, int] = {}
        for target in votes.values():
            counts[target] = counts.get(target, 0) + 1

        max_votes = max(counts.values())
        top = [p for p, v in counts.items() if v == max_votes]

        if len(top) == 1:
            return top[0], counts, False
        return None, counts, True
