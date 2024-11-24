from typing import Any, Dict
import numpy as np
import math
from redis_client import RedisClient
from hedge_game_instance import HedgeGameInstance

LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

class MidpointMasterGameInstance(HedgeGameInstance):
    player_letters: Dict[str, str]

    def __init__(self, instance_id: str, redis_client: RedisClient):
        super().__init__(instance_id, redis_client)
        self.board = [[[] for _ in range(10)] for _ in range(10)]
        self.player_letters = {}

    def get_player_data(self):
        print(self.players)
        return {
            player_name: {
                "points": self.players[player_name].points,
                "played": self.players[player_name].played if self.players[player_name].played is not None else None,
                "added_score": self.players[player_name].added_score if self.players[player_name].added_score is not None else None,
                "acknowledged": self.players[player_name].acknowledged,
                "letter": self.player_letters.get(player_name, "")
            } for player_name in self.players
        }
    
    async def handle_next(self):
        for player_name in self.get_live_players():
            self.players[player_name].played = None
            self.players[player_name].acknowledged = False

        def replace_cell_with_AA(cell):
            if len(cell) != 0:
                return ["AA"]
            else:
                return cell
        # apply on each cell in the board
        self.board = [[replace_cell_with_AA(cell) for cell in row] for row in self.board]

        await self.notify_all_players("next", { "round_id": self.round_id })

    async def handle_evaluate(self):
        print("evaluating")
        self.game_state = "evaluate"
        # evaluate the points of each player
        # calculate the midpoint
        # award points based on distance to midpoint
        # subtract points if two players choose the same cell
        # notify players of their points
        # wait a while before handle next

        # calculate midpoint
        coordinates = [self.players[player_name].played for player_name in self.get_live_players()]

        # played_grid is a 10x10 grid which captures who played each cell
        for player_name in self.get_live_players():
            played_coordinate = self.players[player_name].played
            player_letter = LETTERS[list(self.players.keys()).index(player_name)]
            self.player_letters[player_name] = player_letter
            self.board[played_coordinate[0]][played_coordinate[1]].append(player_letter)

        x = np.array([coordinate[0] for coordinate in coordinates])
        y = np.array([coordinate[1] for coordinate in coordinates])

        self.midpoint = round(np.mean(x), 4), round(np.mean(y), 4)
        failed_players = []
        
        for player_name in self.get_live_players():
            player = self.players[player_name]
            player.played = tuple(player.played)
            player_distance = np.linalg.norm(np.array(player.played) - np.array(self.midpoint))
            player.added_score = int(100 * math.exp(-player_distance / 10))

            # check if two players chose the same cell
            if len(self.board[player.played[0]][player.played[1]]) > 1:
                failed_players.append(player_name)
                player.added_score -= 50
            
            player.points += player.added_score

        self.failed_players = failed_players

        await self.notify_all_players("evaluate", { 'midpoint': self.midpoint, 'failed_players': failed_players })

        self.round_id += 1
        print("finished evaluating")

    async def notify_player(self, player_name: str, method: str, data: Dict[str, Any]):
        await super().notify_player(player_name, method, { 'board': self.board, **data })