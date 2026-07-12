"""In-process cross-tick pattern tracker — compact scouting memory.

Accumulates counters over game-state snapshots in the warm AgentCore runtime
(zero network calls, microsecond cost) and distills them into a short
SCOUTING REPORT block for the LLM prompt.

A new match is detected when gameTime jumps backwards; counters reset.
"""

from collections import Counter, deque
from state import _player_idx, _is_my_team, _possession_idx, get_goal_positions, resolve_holder

DEF_THIRD_DEPTH = 36.7  # field half-length 55 * 2/3


class PatternTracker:
    """Tracks opponent tendencies across ticks for one agent runtime."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.ticks = 0
        self.last_game_time = None
        self.opp_hold = Counter()       # opponent idx -> ticks with ball
        self.opp_hold_total = 0
        self.opp_side_y = Counter()     # "left"/"right" when opponents possess
        self.gk_feed = Counter()        # who receives from their GK
        self.gk_feed_total = 0
        self.prev_holder = None         # (is_opponent, idx)
        self.def_third = deque(maxlen=30)  # 1 if ball in our defensive third
        self.shots_taken = Counter()    # our player idx -> shots taken
        self.shots_on_target = Counter()  # shots that were in range

    def update(self, game_state: dict, team_id: int) -> None:
        """Ingest one game-state snapshot. Call once per tick."""
        game_time = game_state.get("gameTime", 0) or 0

        # Detect new match (time jumps backward)
        if self.last_game_time is not None and game_time + 5 < self.last_game_time:
            self.reset()
        self.last_game_time = game_time
        self.ticks += 1

        ball = game_state.get("ball", {}) or {}
        players = game_state.get("players", []) or []
        ball_pos = ball.get("position", {}) or {}

        holder_p = resolve_holder(ball, players)
        holder = None
        if holder_p is not None:
            is_opp = not _is_my_team(holder_p, team_id)
            holder = (is_opp, _player_idx(holder_p))

        # Track opponent possession
        if holder and holder[0]:  # opponent has ball
            self.opp_hold[holder[1]] += 1
            self.opp_hold_total += 1
            y = ball_pos.get("y", 0) or 0
            self.opp_side_y["left (y<0)" if y < 0 else "right (y>0)"] += 1

        # Track GK outlet patterns
        if holder and self.prev_holder and self.prev_holder != holder:
            prev_is_opp, prev_idx = self.prev_holder
            cur_is_opp, cur_idx = holder
            if prev_is_opp and cur_is_opp and prev_idx == 0 and cur_idx != 0:
                self.gk_feed[cur_idx] += 1
                self.gk_feed_total += 1
        if holder:
            self.prev_holder = holder

        # Track ball in our defensive third
        my_goal_x, _ = get_goal_positions(team_id)
        ball_x = ball_pos.get("x", 0) or 0
        self.def_third.append(1 if abs(ball_x - my_goal_x) < DEF_THIRD_DEPTH else 0)

    def report(self, game_state: dict, team_id: int, position_label: str) -> str:
        """Distill counters into <=4 prompt lines. Empty until enough data."""
        if self.ticks < 6:
            return ""

        lines = []

        # Main threat identification
        if self.opp_hold_total >= 5:
            idx, n = self.opp_hold.most_common(1)[0]
            pct = round(100 * n / self.opp_hold_total)
            if pct >= 35:
                lines.append(
                    f"- Opp P{idx} carries ball most ({pct}%): MARK/PRESS P{idx} first"
                )

            # Attack side tendency
            side, side_n = self.opp_side_y.most_common(1)[0]
            side_pct = round(100 * side_n / self.opp_hold_total)
            if side_pct >= 60:
                lines.append(
                    f"- Opp attacks mostly {side} ({side_pct}%): shade that side"
                )

        # GK outlet pattern (for MID/FWDs to intercept)
        if position_label in ("MID", "FWD1", "FWD2") and self.gk_feed_total >= 3:
            feed_idx, feed_n = self.gk_feed.most_common(1)[0]
            lines.append(
                f"- Their GK feeds P{feed_idx} ({feed_n}/{self.gk_feed_total}): intercept that outlet"
            )

        # Defensive pressure indicator (for GK/DEF)
        if position_label in ("GK", "DEF") and len(self.def_third) >= 10:
            press_pct = round(100 * sum(self.def_third) / len(self.def_third))
            if press_pct >= 50:
                lines.append(
                    f"- Ball in OUR third {press_pct}% recently: HIGH DANGER, prioritize defense"
                )

        # Score awareness
        score = game_state.get("score", {}) or {}
        home, away = score.get("home", 0), score.get("away", 0)
        mine = home if team_id == 0 else away
        theirs = away if team_id == 0 else home
        if mine < theirs:
            lines.append(f"- LOSING {mine}-{theirs}: take more risks, push for goals")
        elif mine > theirs:
            lines.append(f"- WINNING {mine}-{theirs}: protect lead, no cheap counters")

        if not lines:
            return ""
        return "\nSCOUTING (match patterns):\n" + "\n".join(lines[:4])
