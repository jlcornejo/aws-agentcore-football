"""Inline tactical computations injected into the agent prompt each tick."""
import math
from state import _player_idx, _is_my_team, get_goal_positions, dist

GOAL_HALF_WIDTH = 5.0

def shot_power(d_goal: float) -> float:
    """Power scales with distance. Close=0.7, Medium=0.85, Far=1.0"""
    return round(min(1.0, 0.6 + d_goal / 80.0), 2)

def lane_clear(me_pos: dict, opp_goal_x: float, opponents: list, radius: float = 2.5) -> bool:
    """Check if CENTER shot lane is clear of opponents."""
    dx = opp_goal_x - me_pos.get("x", 0)
    dy = 0 - me_pos.get("y", 0)  # aiming center
    length = math.hypot(dx, dy) or 1.0
    for o in opponents:
        p = o.get("position", {}) or {}
        rx = p.get("x", 0) - me_pos.get("x", 0)
        ry = p.get("y", 0) - me_pos.get("y", 0)
        t = (rx * dx + ry * dy) / (length ** 2)
        if not (0.05 < t < 0.95):
            continue
        perp = abs((ry * dx - rx * dy) / length)
        if perp < radius:
            return False
    return True

def best_pass_target(me_pos: dict, my_player_id: int, players: list, team_id: int, opp_goal_x: float, opponents: list) -> tuple:
    """Find best pass target. Returns (player_id, success_pct, pass_type) or (None, 0, None)."""
    my_team = [p for p in players if _is_my_team(p, team_id) and _player_idx(p) != my_player_id and _player_idx(p) != 0]
    if not my_team:
        return None, 0, None
    
    best_id, best_score, best_type = None, -1, None
    goal = {"x": opp_goal_x, "y": 0}
    
    for tm in my_team:
        tid = _player_idx(tm)
        tm_pos = tm.get("position", {})
        pass_dist = dist(me_pos, tm_pos)
        
        # Risk: opponents near the pass lane
        risk = 0.0
        if pass_dist > 1:
            dx = tm_pos.get("x", 0) - me_pos.get("x", 0)
            dy = tm_pos.get("y", 0) - me_pos.get("y", 0)
            for o in opponents:
                op = o.get("position", {})
                ox = op.get("x", 0) - me_pos.get("x", 0)
                oy = op.get("y", 0) - me_pos.get("y", 0)
                t = max(0, min(1, (ox*dx + oy*dy) / (pass_dist**2)))
                lane_d = math.sqrt((op.get("x",0) - (me_pos.get("x",0) + t*dx))**2 + (op.get("y",0) - (me_pos.get("y",0) + t*dy))**2)
                if lane_d < 8:
                    risk = max(risk, 1.0 - lane_d / 8.0)
        
        success = max(0.05, 1.0 - risk - pass_dist / 120.0)
        # Bonus for being closer to goal
        tm_d_goal = dist(tm_pos, goal)
        my_d_goal = dist(me_pos, goal)
        if tm_d_goal < my_d_goal:
            success += 0.1
        
        ptype = "GROUND" if pass_dist < 20 else ("THROUGH" if success > 0.5 else "AERIAL")
        
        if success > best_score:
            best_id, best_score, best_type = tid, success, ptype
    
    return best_id, round(best_score * 100), best_type

def find_open_space(me_pos: dict, opponents: list, team_id: int) -> tuple:
    """Find best open space to run to in attacking third. Returns (x, y, min_opp_dist)."""
    x_min, x_max = (15, 48) if team_id == 0 else (-48, -15)
    best_point, best_score = None, -999
    
    for x in range(x_min, x_max + 1, 8):
        for y in range(-25, 26, 8):
            pt = {"x": x, "y": y}
            min_opp = min((dist(pt, o.get("position", {})) for o in opponents), default=99)
            score = min_opp - dist(pt, me_pos) * 0.15
            if score > best_score:
                best_score = score
                best_point = (x, y, min_opp)
    
    return best_point or (25, 0, 10)

def tactics_report(game_state: dict, team_id: int, my_player_id: int, position_label: str) -> str:
    """Build a TACTICS block to inject into the prompt. Max 3 lines."""
    ball = game_state.get("ball", {}) or {}
    players = game_state.get("players", []) or []
    
    my_team = [p for p in players if _is_my_team(p, team_id)]
    opponents = [p for p in players if not _is_my_team(p, team_id)]
    me = next((p for p in my_team if _player_idx(p) == my_player_id), None)
    if me is None:
        return ""
    me_pos = me.get("position", {}) or {}
    
    my_goal_x, opp_goal_x = get_goal_positions(team_id)
    
    # Determine who has ball
    from state import _possession_idx
    poss_idx = _possession_idx(ball)
    i_have_ball = poss_idx == my_player_id
    # Check if holder is on my team
    holder_on_my_team = False
    if poss_idx is not None:
        holder_p = next((p for p in players if _player_idx(p) == poss_idx), None)
        if holder_p and _is_my_team(holder_p, team_id):
            holder_on_my_team = True
    
    lines = []
    
    if i_have_ball:
        d_goal = dist(me_pos, {"x": opp_goal_x, "y": 0})
        is_clear = lane_clear(me_pos, opp_goal_x, opponents)
        pwr = shot_power(d_goal)
        
        if d_goal < 25:
            status = "LANE CLEAR" if is_clear else "LANE BLOCKED"
            lines.append(f"- Shot: dist={d_goal:.0f} {status} -> SHOOT CENTER power {pwr}")
        elif d_goal < 45:
            lines.append(f"- Shot: dist={d_goal:.0f} medium range -> advance or pass forward")
        else:
            lines.append(f"- Shot: dist={d_goal:.0f} too far -> PASS forward or MOVE_TO toward goal")
        
        # Best pass
        tid, pct, ptype = best_pass_target(me_pos, my_player_id, players, team_id, opp_goal_x, opponents)
        if tid is not None:
            lines.append(f"- Best pass: P{tid} ({pct}% {ptype})")
    
    elif holder_on_my_team:
        # Teammate has ball — where to run
        sx, sy, sd = find_open_space(me_pos, opponents, team_id)
        lines.append(f"- Open space: ({sx},{sy}) nearest opp {sd:.0f}m -> MOVE_TO there")
    
    else:
        # Opponent has ball or ball loose
        ball_pos = ball.get("position", {}) or {}
        d_ball = dist(me_pos, ball_pos)
        if d_ball < 15:
            lines.append(f"- Ball nearby ({d_ball:.0f}m): PRESS_BALL or INTERCEPT")
        elif position_label in ("DEF", "GK"):
            lines.append(f"- Defend: position between ball and goal")
        else:
            lines.append(f"- Ball far ({d_ball:.0f}m): hold position or track back")
    
    if not lines:
        return ""
    return "\nTACTICS (computed for you):\n" + "\n".join(lines)
