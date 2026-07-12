"""Game state summarization utilities for AI soccer agents."""

import math


# ---------------------------------------------------------------------------
# Format-agnostic helpers — handle both new (agentId/teamCode/possessionAgentId)
# and old (playerId/teamId/possessionPlayerId) game server formats.
# ---------------------------------------------------------------------------

def _player_idx(p: dict) -> int:
    """Numeric index (0-4) from a player dict — new agentId or old playerId."""
    if "agentId" in p:
        try:
            return int(p["agentId"].rsplit("_", 1)[-1])
        except (ValueError, IndexError):
            return 0
    return p.get("playerId", 0)


def _is_my_team(p: dict, team_id: int) -> bool:
    """True if player belongs to team_id — new teamCode or old teamId."""
    if "teamCode" in p:
        return p["teamCode"] == ("home" if team_id == 0 else "away")
    return p.get("teamId") == team_id


def _possession_idx(ball: dict):
    """Numeric possession player index from ball dict — new possessionAgentId or old possessionPlayerId.
    Returns int or None."""
    agent_id = ball.get("possessionAgentId")
    if agent_id is not None:
        try:
            return int(agent_id.rsplit("_", 1)[-1])
        except (ValueError, IndexError):
            return None
    return ball.get("possessionPlayerId")


def get_goal_positions(team_id: int) -> tuple[float, float]:
    """Return (my_goal_x, opp_goal_x) based on team."""
    if team_id == 0:
        return -55.0, 55.0
    return 55.0, -55.0


def get_possession_info(ball: dict, players: list, team_id: int) -> tuple:
    """Return (possession_id, ball_status_str, we_have_ball)."""
    possession_id = _possession_idx(ball)
    if possession_id is not None:
        holder = next((p for p in players if _player_idx(p) == possession_id), None)
        if holder:
            is_mine = _is_my_team(holder, team_id)
            side = "MY" if is_mine else "OPP"
            return possession_id, f"{side} player {possession_id}", is_mine
        return possession_id, "unknown", False
    return None, "free", False


def dist(pos1: dict, pos2: dict) -> float:
    """Euclidean distance between two position dicts with x,y keys."""
    return math.sqrt(
        (pos1.get("x", 0) - pos2.get("x", 0)) ** 2
        + (pos1.get("y", 0) - pos2.get("y", 0)) ** 2
    )


def resolve_holder(ball: dict, players: list):
    """Return the player dict that holds the ball, or None."""
    poss_idx = _possession_idx(ball)
    if poss_idx is None:
        return None
    return next((p for p in players if _player_idx(p) == poss_idx), None)


def count_opponents_in_our_half(players: list, team_id: int) -> int:
    """Count opponents in our defensive half."""
    my_goal_x, _ = get_goal_positions(team_id)
    count = 0
    for p in players:
        if _is_my_team(p, team_id):
            continue
        pos = p.get("position", {})
        if my_goal_x < 0:  # HOME: our half is x < 0
            if pos.get("x", 0) < 0:
                count += 1
        else:  # AWAY: our half is x > 0
            if pos.get("x", 0) > 0:
                count += 1
    return count


def summarize_state(
    game_state: dict,
    team_id: int,
    my_player_id: int,
    position_label: str,
) -> str:
    """Build a concise text summary of the game state for a single-player agent."""
    ball = game_state.get("ball", {})
    ball_pos = ball.get("position", {"x": 0, "y": 0})
    score = game_state.get("score", {})
    game_time = game_state.get("gameTime", 0)
    play_mode = game_state.get("playMode", 0)
    players = game_state.get("players", [])

    my_team = sorted(
        [p for p in players if _is_my_team(p, team_id)],
        key=lambda p: _player_idx(p),
    )
    opponents = sorted(
        [p for p in players if not _is_my_team(p, team_id)],
        key=lambda p: _player_idx(p),
    )

    me = next((p for p in my_team if _player_idx(p) == my_player_id), None)
    possession_id, ball_status, _ = get_possession_info(ball, players, team_id)

    my_goal_x, opp_goal_x = get_goal_positions(team_id)

    lines = [
        f"Time: {game_time:.0f}s | Score: {score.get('home',0)}-{score.get('away',0)} | "
        f"Team: {team_id} ({'HOME' if team_id == 0 else 'AWAY'}) | PlayMode: {play_mode}",
        f"Ball: ({ball_pos.get('x',0):.1f}, {ball_pos.get('y',0):.1f}) held by {ball_status}",
        f"Your goal at x={my_goal_x:.0f} | Opponent goal at x={opp_goal_x:.0f}",
        "",
    ]

    # My player info
    if me:
        pos = me.get("position", {})
        stam = me.get("stamina", 100)
        dist_ball = dist(pos, ball_pos)
        has_ball = possession_id == my_player_id
        extra = f" distOppGoal={abs(pos.get('x', 0) - opp_goal_x):.1f}" if position_label in ("MID", "FWD1", "FWD2") else ""
        lines.append(
            f">>> YOUR PLAYER ({position_label}, id={my_player_id}): "
            f"pos=({pos.get('x',0):.1f},{pos.get('y',0):.1f}) "
            f"stam={stam:.0f} distBall={dist_ball:.1f}{extra} hasBall={has_ball}"
        )
    lines.append("")

    # Teammates
    lines.append("Teammates:")
    for p in my_team:
        if _player_idx(p) == my_player_id:
            continue
        pos = p.get("position", {})
        pid = _player_idx(p)
        role = "GK" if pid == 0 else f"P{pid}"
        extra = ""
        if position_label == "MID":
            extra = f" distOppGoal={abs(pos.get('x', 0) - opp_goal_x):.1f}"
        lines.append(f"  {role}(id={pid}): ({pos.get('x',0):.1f},{pos.get('y',0):.1f}){extra}")

    lines.append("")

    # Opponents
    opp_header = "Opponents (defenders to watch):" if position_label in ("FWD1", "FWD2") else "Opponents:"
    lines.append(opp_header)
    for p in opponents:
        pos = p.get("position", {})
        pid = _player_idx(p)
        d_goal = abs(pos.get("x", 0) - my_goal_x)
        d_me = dist(pos, me.get("position", {})) if me else 0
        lines.append(f"  P{pid}: ({pos.get('x',0):.1f},{pos.get('y',0):.1f}) distToMyGoal={d_goal:.1f} distToMe={d_me:.1f}")

    # Time remaining (match is 300s)
    time_remaining = max(0, 300 - game_time)
    if time_remaining < 60:
        lines.append(f"\n⚠️ TIME CRITICAL: {time_remaining:.0f}s remaining!")
    else:
        lines.append(f"\nTime remaining: {time_remaining:.0f}s")

    # Coach instructions (teamChat) — real-time messages from the human coach
    team_chat = game_state.get("teamChat", [])
    if team_chat:
        lines.append("")
        lines.append("🗣️ COACH SAYS:")
        for msg in team_chat[-3:]:  # Show last 3 messages max
            if isinstance(msg, dict):
                lines.append(f"  \"{msg.get('message', msg.get('content', str(msg)))}\"")
            elif isinstance(msg, str):
                lines.append(f"  \"{msg}\"")

    return "\n".join(lines)
