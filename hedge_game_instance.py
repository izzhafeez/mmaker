from typing import Any, Dict
from abc import abstractmethod
import numpy as np
import asyncio
from game_instance import GameInstance, GamePlayer

class HedgeGamePlayer(GamePlayer):
		played: Any
		added_score: float
		points: float
		acknowledged: bool

		def __init__(self):
				super().__init__()
				self.played = None
				self.added_score = 0
				self.points = 0
				self.acknowledged = False

class HedgeGameInstance(GameInstance):
		players: Dict[str, HedgeGamePlayer]

		def get_player_data(self):
				return {
						player_name: {
								"points": self.players[player_name].points,
								"played": self.players[player_name].played if self.players[player_name].played is not None else None,
								"added_score": self.players[player_name].added_score,
								"acknowledged": self.players[player_name].acknowledged
						} for player_name in self.players
				}
		
		async def handle_redis_message(self, data: Dict[str, Any]):
				print(data)
				method = data["method"]
				if method == "join":
						await self.handle_join(data["name"])

				elif method == "leave":
						await self.handle_leave(data["name"])

				elif method == "start":
						await self.handle_start(data["seed"])

				elif method == "play":
						await self.handle_play(data["name"], data["played"])

				elif method == "acknowledge":
						print("acknowledged")

						player_name = data["name"]
						self.players[player_name].acknowledged = True
						await self.notify_all_players("acknowledge", {})

						if all(self.players[player_name].acknowledged for player_name in self.get_live_players()):
								await self.handle_next()

		async def handle_play(self, name: str, played: Any):
				self.players[name].played = played
				await self.notify_all_players("play", {})

				if all(self.players[player_name].played is not None for player_name in self.get_live_players()):
						await self.handle_evaluate()

		@abstractmethod
		async def handle_evaluate(self):
				pass

		@abstractmethod
		async def handle_next(self):
				pass

		async def handle_join(self, player_name: str):
				self.players[player_name] = HedgeGamePlayer()
				await self.notify_all_players("join", {
						"name": player_name
				})

		async def handle_start(self, seed: float):
				self.is_active = True
				self.round_id = 1
				np.random.seed(seed)

				# reset all player points
				for player_name in self.players:
						self.players[player_name].points = 0
						self.players[player_name].is_alive = True

				# wait a while before handle next
				await asyncio.sleep(1)
				await self.handle_next()

		async def handle_leave(self, player_name: str):
				if player_name not in self.players:
						return

				self.players.pop(player_name)
				print(f"player {player_name} left")
				await self.notify_all_players("leave", {
						"name": player_name,
				})

				live_players = self.get_live_players()

				if self.game_state == "start":
						if all(self.players[player_name].played is not None for player_name in self.get_live_players()):
								await self.handle_evaluate()

				elif self.game_state == "evaluate":
						if all(self.players[player_name].acknowledged for player_name in self.get_live_players()):
								await self.handle_next()

				if self.is_active and len(live_players) < 2:
						if len(live_players) == 1:
								await self.notify_all_players("end", {
										"winner": live_players[0]
								})
						else:
								await self.notify_all_players("end", {
										"winner": "No one"
								})
						self.is_active = False

				if len(self.players) == 0:
						self.__init__(self.instance_id, self.redis_client)