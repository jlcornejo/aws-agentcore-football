"""Local Match Simulator — visualiza tu equipo LLM vs un equipo rule-based.

Usage:
    python simulate.py                # Partido completo (20 ticks)
    python simulate.py --ticks 5      # Solo 5 ticks
    python simulate.py --fast         # Sin pausa entre ticks
    python simulate.py --llm          # Usa LLM real (requiere AWS)
    python simulate.py --fallback     # Solo usa fallback (sin AWS, rápido)
"""

import sys
import os
import time
import math
import json
import random

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "lib"))

from test_helpers import mock_agentcore, GAME_STATE, TEAM_ID
mock_agentcore()

from state import summarize_state
from parsing import parse_commands
from fallback import (
    build_fallback, build_last_resort,
    GK_CONFIG, DEF_CONFIG, MID_CONFIG, FWD1_CONFIG, FWD2_CONFIG,
)

# ═══════════════════════════════════════════════════════════════
# FIELD & DISPLAY
# ═══════════════════════════════════════════════════════════════
DISPLAY_W = 66
DISPLAY_H = 27
GOAL_HALF = 7

# Colors (ANSI)
C_RESET = "\033[0m"
C_GREEN = "\033[32m"
C_YELLOW = "\033[33m"
C_CYAN = "\033[36m"
C_RED = "\033[31m"
C_BOLD = "\033[1m"
C_DIM = "\033[2m"
C_WHITE_BG = "\033[47m\033[30m"
C_BLUE = "\033[34m"
C_MAGENTA = "\033[35m"


# ═══════════════════════════════════════════════════════════════
# GAME OBJECTS
# ═══════════════════════════════════════════════════════════════
class Ball:
    def __init__(self):
        self.x = 0.0
        self.y = 0.0
        self.vx = 0.0
        self.vy = 0.0
        self.possessor = None  # (team, player_idx)

    def update(self):
        if self.possessor is None:
            self.x += self.vx
            self.y += self.vy
            self.vx *= 0.88
            self.vy *= 0.88
            if abs(self.vx) < 0.2:
                self.vx = 0
            if abs(self.vy) < 0.2:
                self.vy = 0
            self.x = max(-55, min(55, self.x))
            self.y = max(-35, min(35, self.y))


class Player:
    def __init__(self, team, idx, x, y, role):
        self.team = team  # 0=home(LLM), 1=away(rule)
        self.idx = idx
        self.x = x
        self.y = y
        self.stamina = 0.95
        self.has_ball = False
        self.role = role
        self.last_cmd = ""
        self.last_params = {}

    def move_toward(self, tx, ty, speed=2.0):
        dx, dy = tx - self.x, ty - self.y
        d = math.sqrt(dx * dx + dy * dy)
        if d > 0.5:
            step = min(speed, d)
            self.x += (dx / d) * step
            self.y += (dy / d) * step
            self.stamina = max(0, self.stamina - (0.005 if speed > 3 else 0.002))
        self.x = max(-55, min(55, self.x))
        self.y = max(-35, min(35, self.y))


# ═══════════════════════════════════════════════════════════════
# MATCH
# ═══════════════════════════════════════════════════════════════
class Match:
    def __init__(self):
        self.score = [0, 0]
        self.tick = 0
        self.max_ticks = 20
        self.ball = Ball()
        self.goal_event = None

        # HOME team (yours) — attacks toward +x
        self.home = [
            Player(0, 0, -48, 0, "GK"),
            Player(0, 1, -22, 0, "DEF"),
            Player(0, 2, 0, 0, "MID"),
            Player(0, 3, 18, -8, "FWD1"),
            Player(0, 4, 18, 8, "FWD2"),
        ]
        # AWAY team (rule-based) — attacks toward -x
        self.away = [
            Player(1, 0, 48, 0, "GK"),
            Player(1, 1, 22, 8, "DEF"),
            Player(1, 2, 5, -3, "MID"),
            Player(1, 3, -12, -10, "FWD"),
            Player(1, 4, -12, 10, "FWD"),
        ]

        # Kickoff: home MID has ball
        self._give_ball(0, 2)

    def _give_ball(self, team, pid):
        for p in self.home + self.away:
            p.has_ball = False
        if team == 0:
            self.home[pid].has_ball = True
        else:
            self.away[pid].has_ball = True
        self.ball.possessor = (team, pid)
        owner = self.home[pid] if team == 0 else self.away[pid]
        self.ball.x = owner.x
        self.ball.y = owner.y
        self.ball.vx = 0
        self.ball.vy = 0

    def build_state(self):
        """Build game state in the official server format."""
        players = []
        for p in self.home:
            players.append({
                "agentId": f"agentId_{p.idx}", "teamCode": "home",
                "position": {"x": p.x, "y": p.y},
                "velocity": {"x": 0, "y": 0},
                "stamina": p.stamina, "speed": 0, "isSprinting": False,
                "orientation": 0, "currentAction": 0, "lastAction": p.last_cmd,
            })
        for p in self.away:
            players.append({
                "agentId": f"agentId_{p.idx}", "teamCode": "away",
                "position": {"x": p.x, "y": p.y},
                "velocity": {"x": 0, "y": 0},
                "stamina": p.stamina, "speed": 0, "isSprinting": False,
                "orientation": 0, "currentAction": 0, "lastAction": p.last_cmd,
            })

        poss = None
        if self.ball.possessor:
            t, pid = self.ball.possessor
            team_players = self.home if t == 0 else self.away
            poss = f"agentId_{pid}"

        return {
            "tick": self.tick, "gameTime": self.tick * 2.0,
            "playMode": "OPEN_PLAY", "modeTeamId": None,
            "score": {"home": self.score[0], "away": self.score[1]},
            "ball": {
                "position": {"x": self.ball.x, "y": self.ball.y, "z": 0},
                "velocity": {"x": self.ball.vx, "y": self.ball.vy, "z": 0},
                "isFree": self.ball.possessor is None,
                "possessionAgentId": poss,
                "rotation": {}, "angularVelocity": {},
            },
            "players": players,
            "teamChat": [],
        }

    def apply_home_cmd(self, player, cmd):
        """Apply a parsed command to a home player."""
        ct = cmd.get("commandType", "SET_STANCE")
        params = cmd.get("parameters", {})
        player.last_cmd = ct
        player.last_params = params

        if ct == "SHOOT" and player.has_ball:
            power = params.get("power", 0.8)
            player.has_ball = False
            self.ball.possessor = None
            self.ball.x, self.ball.y = player.x, player.y

            # Aim toward the GOAL (x=55, y=target based on aim_location)
            goal_x = 55.0
            aim = params.get("aim_location", "CENTER")
            aim_y = {"TL": -5, "TR": -5, "BL": 5, "BR": 5, "CENTER": 0}.get(aim, 0)

            dx = goal_x - player.x
            dy = aim_y - player.y
            dist_to_goal = math.sqrt(dx*dx + dy*dy) or 1

            speed = power * 14
            self.ball.vx = (dx / dist_to_goal) * speed
            self.ball.vy = (dy / dist_to_goal) * speed

        elif ct == "PASS" and player.has_ball:
            tid = params.get("target_player_id", 2)
            target = next((p for p in self.home if p.idx == tid), None)
            if target:
                player.has_ball = False
                self.ball.possessor = None
                self.ball.x, self.ball.y = player.x, player.y
                dx, dy = target.x - player.x, target.y - player.y
                d = math.sqrt(dx*dx + dy*dy) or 1
                spd = 9 if params.get("type") == "AERIAL" else 6
                self.ball.vx, self.ball.vy = (dx/d)*spd, (dy/d)*spd

        elif ct == "GK_DISTRIBUTE" and player.has_ball:
            tid = params.get("target_player_id", 1)
            target = next((p for p in self.home if p.idx == tid), None)
            if target:
                player.has_ball = False
                self.ball.possessor = None
                self.ball.x, self.ball.y = player.x, player.y
                dx, dy = target.x - player.x, target.y - player.y
                d = math.sqrt(dx*dx + dy*dy) or 1
                self.ball.vx, self.ball.vy = (dx/d)*8, (dy/d)*8

        elif ct == "MOVE_TO":
            tx = params.get("target_x", player.x)
            ty = params.get("target_y", player.y)
            sprint = params.get("sprint", False)
            player.move_toward(tx, ty, speed=4.5 if sprint else 2.5)

        elif ct in ("PRESS_BALL", "INTERCEPT"):
            player.move_toward(self.ball.x, self.ball.y, speed=3.5)

        elif ct == "MARK":
            tid = params.get("target_player_id", 0)
            target = next((p for p in self.away if p.idx == tid), None)
            if target:
                player.move_toward(target.x, target.y, speed=2.5)

        elif ct == "FOLLOW_PLAYER":
            tid = params.get("target_player_id", 0)
            target = next((p for p in self.away if p.idx == tid), None)
            if target:
                player.move_toward(target.x, target.y, speed=2.0)

        elif ct == "SLIDE_TACKLE":
            player.move_toward(self.ball.x, self.ball.y, speed=5.0)
            if self.ball.possessor and self.ball.possessor[0] == 1:
                carrier = self.away[self.ball.possessor[1]]
                d = math.sqrt((player.x-carrier.x)**2 + (player.y-carrier.y)**2)
                if d < 4 and random.random() < 0.5:
                    carrier.has_ball = False
                    self._give_ball(0, player.idx)

    def run_away_ai(self):
        """Simple rule-based AI for away team."""
        for p in self.away:
            if p.has_ball:
                if p.x < -30:
                    p.has_ball = False
                    self.ball.possessor = None
                    self.ball.x, self.ball.y = p.x, p.y
                    self.ball.vx = -12
                    self.ball.vy = random.uniform(-4, 4)
                    p.last_cmd = "SHOOT"
                else:
                    p.move_toward(p.x - 5, p.y + random.uniform(-2, 2), speed=2.5)
                    self.ball.x, self.ball.y = p.x, p.y
                    p.last_cmd = "DRIBBLE"
            else:
                d_ball = math.sqrt((p.x - self.ball.x)**2 + (p.y - self.ball.y)**2)
                if d_ball < 12 and self.ball.possessor and self.ball.possessor[0] == 0:
                    p.move_toward(self.ball.x, self.ball.y, speed=3.0)
                    p.last_cmd = "PRESS"
                elif p.role == "GK":
                    p.move_toward(48, max(-7, min(7, self.ball.y * 0.3)), speed=1.5)
                    p.last_cmd = "POSITION"
                else:
                    defaults = {1: (18, 6), 2: (3, -3), 3: (-14, -10), 4: (-14, 10)}
                    dx, dy = defaults.get(p.idx, (0, 0))
                    p.move_toward(dx, dy, speed=1.5)
                    p.last_cmd = "POSITION"

    def check_possession(self):
        if self.ball.possessor is not None:
            return
        for p in self.home + self.away:
            d = math.sqrt((p.x - self.ball.x)**2 + (p.y - self.ball.y)**2)
            if d < 3.5:
                self._give_ball(p.team, p.idx)
                return

    def check_goals(self):
        self.goal_event = None
        if self.ball.x >= 54 and abs(self.ball.y) < GOAL_HALF:
            self.score[0] += 1
            self.goal_event = "HOME"
            self._reset_kickoff(1)
        elif self.ball.x <= -54 and abs(self.ball.y) < GOAL_HALF:
            self.score[1] += 1
            self.goal_event = "AWAY"
            self._reset_kickoff(0)
        # Out of bounds
        if abs(self.ball.x) > 55:
            self.ball.x = max(-54, min(54, self.ball.x))
            self.ball.vx = 0
            self.ball.vy = 0
        if abs(self.ball.y) > 35:
            self.ball.y = max(-34, min(34, self.ball.y))
            self.ball.vy = 0

    def _reset_kickoff(self, team_with_ball):
        for p in self.home:
            p.x, p.y = [(-48, 0), (-22, 0), (-2, 0), (-5, -8), (-5, 8)][p.idx]
        for p in self.away:
            p.x, p.y = [(48, 0), (22, 0), (2, 0), (5, -8), (5, 8)][p.idx]
        self.ball.x, self.ball.y = 0, 0
        self._give_ball(team_with_ball, 2)  # MID gets kickoff

    # ═══════════════════════════════════════════════════════════
    # RENDER
    # ═══════════════════════════════════════════════════════════
    def render(self):
        grid = [[' '] * DISPLAY_W for _ in range(DISPLAY_H)]

        # Field borders
        for x in range(DISPLAY_W):
            grid[0][x] = '━'
            grid[DISPLAY_H-1][x] = '━'
        for y in range(DISPLAY_H):
            grid[y][0] = '┃'
            grid[y][DISPLAY_W-1] = '┃'
        grid[0][0] = '┏'; grid[0][DISPLAY_W-1] = '┓'
        grid[DISPLAY_H-1][0] = '┗'; grid[DISPLAY_H-1][DISPLAY_W-1] = '┛'

        # Center line + circle
        cx = DISPLAY_W // 2
        for y in range(1, DISPLAY_H-1):
            grid[y][cx] = '│'
        cy = DISPLAY_H // 2
        grid[cy][cx] = '┼'

        # Goals
        g_top = DISPLAY_H // 2 - 3
        g_bot = DISPLAY_H // 2 + 3
        for y in range(g_top, g_bot + 1):
            grid[y][1] = '▎'
            grid[y][DISPLAY_W-2] = '▕'

        def to_screen(px, py):
            sx = int((px + 55) / 110 * (DISPLAY_W - 4)) + 2
            sy = int((py + 35) / 70 * (DISPLAY_H - 2)) + 1
            return max(2, min(DISPLAY_W-3, sx)), max(1, min(DISPLAY_H-2, sy))

        # Ball (if free)
        if self.ball.possessor is None:
            bx, by = to_screen(self.ball.x, self.ball.y)
            grid[by][bx] = '●'

        # Away team (red letters)
        for p in self.away:
            sx, sy = to_screen(p.x, p.y)
            ch = chr(ord('A') + p.idx)
            if p.has_ball:
                ch = '◉'
            grid[sy][sx] = ch

        # Home team (numbers)
        for p in self.home:
            sx, sy = to_screen(p.x, p.y)
            ch = str(p.idx)
            if p.has_ball:
                ch = '◈'
            grid[sy][sx] = ch

        # Build output with colors
        time_left = max(0, (self.max_ticks - self.tick) * 2)
        header = (
            f" {C_BOLD}Tick {self.tick:2}/{self.max_ticks}{C_RESET}"
            f" │ {C_CYAN}HOME {self.score[0]}{C_RESET}"
            f" - {C_RED}{self.score[1]} AWAY{C_RESET}"
            f" │ ⏱ {time_left}s"
        )

        field_lines = []
        for row in grid:
            line = ''.join(row)
            # Colorize home players (digits)
            for i in range(5):
                line = line.replace(str(i), f"{C_CYAN}{C_BOLD}{i}{C_RESET}", 1)
            # Colorize home with ball
            line = line.replace('◈', f"{C_CYAN}{C_BOLD}◈{C_RESET}")
            # Colorize away players
            for ch in 'ABCDE':
                line = line.replace(ch, f"{C_RED}{ch}{C_RESET}", 1)
            line = line.replace('◉', f"{C_RED}{C_BOLD}◉{C_RESET}")
            # Ball
            line = line.replace('●', f"{C_YELLOW}{C_BOLD}●{C_RESET}")
            field_lines.append(line)

        output = [header, *field_lines]

        # Legend
        output.append(f"  {C_CYAN}HOME (LLM):{C_RESET} 0=GK 1=DEF 2=MID 3=FWD1 4=FWD2  ◈=has ball")
        output.append(f"  {C_RED}AWAY (bot):{C_RESET} A=GK B=DEF C=MID D=FWD  E=FWD    ◉=has ball")

        return '\n'.join(output)

    def _format_params(self, cmd, params):
        """Format params into a short human-readable string."""
        if not params:
            return ""
        ct = cmd
        parts = []
        if ct == "SHOOT":
            aim = params.get("aim_location", "?")
            pwr = params.get("power", "?")
            parts.append(f"aim={aim} pwr={pwr}")
        elif ct == "PASS":
            tid = params.get("target_player_id", "?")
            ptype = params.get("type", "GROUND")
            parts.append(f"→P{tid} ({ptype})")
        elif ct == "GK_DISTRIBUTE":
            tid = params.get("target_player_id", "?")
            method = params.get("method", "THROW")
            parts.append(f"→P{tid} ({method})")
        elif ct == "MOVE_TO":
            tx = params.get("target_x", 0)
            ty = params.get("target_y", 0)
            sprint = "🏃" if params.get("sprint") else ""
            parts.append(f"({tx:.0f},{ty:.0f}){sprint}")
        elif ct == "MARK":
            tid = params.get("target_player_id", "?")
            tight = params.get("tightness", "")
            parts.append(f"opp P{tid} {tight}")
        elif ct == "PRESS_BALL":
            inten = params.get("intensity", "?")
            parts.append(f"int={inten}")
        elif ct == "INTERCEPT":
            aggr = "aggr" if params.get("aggressive") else "safe"
            parts.append(aggr)
        elif ct == "FOLLOW_PLAYER":
            tid = params.get("target_player_id", "?")
            parts.append(f"follow P{tid}")
        elif ct == "SET_STANCE":
            stances = {0: "BAL", 1: "ATK", 2: "DEF"}
            parts.append(stances.get(params.get("stance", 0), "?"))
        else:
            # Generic: show first 2 params
            for k, v in list(params.items())[:2]:
                if k != "duration" and v is not None:
                    parts.append(f"{k}={v}")
        return " ".join(parts)

    def render_actions(self):
        """Render a compact, readable action log for both teams."""
        lines = []

        # Header separator
        lines.append("")
        lines.append(f"  {C_CYAN}┌─ TU EQUIPO (HOME) ────────────────────────────────────┐{C_RESET}")

        roles = {0: "GK ", 1: "DEF", 2: "MID", 3: "FW1", 4: "FW2"}
        for p in self.home:
            ball_icon = f"{C_YELLOW}⚽{C_RESET}" if p.has_ball else "  "
            cmd = p.last_cmd or "IDLE"
            params_desc = self._format_params(cmd, p.last_params)
            stam_bar = "█" * int(p.stamina * 5) + "░" * (5 - int(p.stamina * 5))
            stam_color = C_GREEN if p.stamina > 0.6 else (C_YELLOW if p.stamina > 0.3 else C_RED)

            lines.append(
                f"  {C_CYAN}│{C_RESET} {ball_icon} "
                f"{C_BOLD}{roles[p.idx]}{C_RESET} "
                f"{C_DIM}({p.x:5.1f},{p.y:5.1f}){C_RESET} "
                f"{stam_color}{stam_bar}{C_RESET} "
                f"→ {C_BOLD}{cmd:14}{C_RESET} "
                f"{C_DIM}{params_desc}{C_RESET}"
            )

        lines.append(f"  {C_CYAN}└───────────────────────────────────────────────────────┘{C_RESET}")
        lines.append(f"  {C_RED}┌─ RIVAL (AWAY) ────────────────────────────────────────┐{C_RESET}")

        away_roles = {0: "GK ", 1: "DEF", 2: "MID", 3: "FWD", 4: "FWD"}
        for p in self.away:
            ball_icon = f"{C_YELLOW}⚽{C_RESET}" if p.has_ball else "  "
            cmd = p.last_cmd or "IDLE"

            lines.append(
                f"  {C_RED}│{C_RESET} {ball_icon} "
                f"{away_roles[p.idx]} "
                f"{C_DIM}({p.x:5.1f},{p.y:5.1f}){C_RESET} "
                f"→ {cmd}"
            )

        lines.append(f"  {C_RED}└───────────────────────────────────────────────────────┘{C_RESET}")

        # Ball info
        if self.ball.possessor:
            team_name = f"{C_CYAN}HOME{C_RESET}" if self.ball.possessor[0] == 0 else f"{C_RED}AWAY{C_RESET}"
            lines.append(f"  ⚽ Balón: {team_name} P{self.ball.possessor[1]}")
        else:
            speed = math.sqrt(self.ball.vx**2 + self.ball.vy**2)
            if speed > 0.5:
                lines.append(f"  ⚽ Balón: libre, moviéndose ({self.ball.x:.0f},{self.ball.y:.0f}) vel={speed:.1f}")
            else:
                lines.append(f"  ⚽ Balón: libre en ({self.ball.x:.0f},{self.ball.y:.0f})")

        return '\n'.join(lines)


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════
def run(max_ticks=20, fast=False, use_llm=False):
    print(f"\n{C_BOLD}🏟️  AGENTIC FOOTBALL CUP — Simulador Local{C_RESET}")
    print("═" * 60)

    # Setup fallbacks (always available)
    configs = {0: GK_CONFIG, 1: DEF_CONFIG, 2: MID_CONFIG, 3: FWD1_CONFIG, 4: FWD2_CONFIG}
    fallbacks = {pid: build_fallback(cfg) for pid, cfg in configs.items()}
    labels = {0: "GK", 1: "DEF", 2: "MID", 3: "FWD1", 4: "FWD2"}

    # LLM agents (optional)
    agents = {}
    if use_llm:
        print("  Creando agentes LLM (Nova Micro)...")
        from strands import Agent
        from strands.models import BedrockModel
        model = BedrockModel(model_id="us.amazon.nova-micro-v1:0")

        # Import prompts from each agent
        for pid in range(5):
            agent_dir = ["ai-gk", "ai-def", "ai-mid", "ai-fwd1", "ai-fwd2"][pid]
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), agent_dir, "src"))

        # Re-import to get fresh SYSTEM_PROMPTs
        import importlib
        for pid, agent_dir in enumerate(["ai-gk", "ai-def", "ai-mid", "ai-fwd1", "ai-fwd2"]):
            spec = importlib.util.spec_from_file_location(
                f"agent_{pid}",
                os.path.join(os.path.dirname(__file__), agent_dir, "src", "main.py")
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            agents[pid] = Agent(model=model, system_prompt=mod.SYSTEM_PROMPT)
        print(f"  ✅ 5 agentes listos")
    else:
        print(f"  Modo: {C_BOLD}FALLBACK{C_RESET} (sin LLM, solo reglas)")
        print(f"  Usa --llm para probar con Amazon Bedrock")

    print(f"  {C_CYAN}HOME{C_RESET} (tu equipo) vs {C_RED}AWAY{C_RESET} (bot)")
    print("═" * 60)
    if not fast:
        time.sleep(1)

    match = Match()
    match.max_ticks = max_ticks

    for tick in range(max_ticks):
        match.tick = tick
        game_state = match.build_state()

        # Home team decisions
        for player in match.home:
            if use_llm and player.idx in agents:
                try:
                    summary = summarize_state(game_state, 0, player.idx, labels[player.idx])
                    response = agents[player.idx](summary)
                    cmds = parse_commands(str(response), 0, player.idx)
                    if cmds:
                        match.apply_home_cmd(player, cmds[0])
                        continue
                except Exception:
                    pass
            # Fallback
            cmds = fallbacks[player.idx](game_state, 0, player.idx)
            if cmds:
                match.apply_home_cmd(player, cmds[0])

        # Away team
        match.run_away_ai()

        # Physics
        match.ball.update()
        match.check_possession()
        match.check_goals()

        # Render
        if not fast:
            os.system('clear' if os.name != 'nt' else 'cls')
        print(match.render())
        print(match.render_actions())

        if match.goal_event:
            team_name = f"{C_CYAN}HOME{C_RESET}" if match.goal_event == "HOME" else f"{C_RED}AWAY{C_RESET}"
            print(f"\n  🎉 {C_BOLD}¡¡¡GOOOL!!! {team_name} anota!{C_RESET}")
            if not fast:
                time.sleep(2)
        if not fast:
            time.sleep(0.8)

    # Final
    print(f"\n{'═' * 60}")
    print(f"  {C_BOLD}🏁 RESULTADO FINAL: HOME {match.score[0]} - {match.score[1]} AWAY{C_RESET}")
    if match.score[0] > match.score[1]:
        print(f"  {C_CYAN}{C_BOLD}🏆 ¡TU EQUIPO GANA!{C_RESET}")
    elif match.score[0] < match.score[1]:
        print(f"  {C_RED}😤 Perdiste. ¡Ajusta los prompts!{C_RESET}")
    else:
        print(f"  🤝 Empate.")
    print("═" * 60)


if __name__ == "__main__":
    ticks = 20
    fast = "--fast" in sys.argv
    use_llm = "--llm" in sys.argv

    for i, arg in enumerate(sys.argv):
        if arg == "--ticks" and i + 1 < len(sys.argv):
            try:
                ticks = int(sys.argv[i + 1])
            except ValueError:
                pass

    run(max_ticks=ticks, fast=fast, use_llm=use_llm)
