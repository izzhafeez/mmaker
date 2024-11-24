from typing import List, Any
import numpy as np
from hedge_game_instance import HedgeGameInstance
from redis_client import RedisClient

ROUNDS = 10
OPTIONS_SIZE = 10

class DataHedgerGameInstance(HedgeGameInstance):
		options: List[Any]

		def __init__(self, instance_id: str, redis_client: RedisClient, deck_size: int=100):
				super().__init__(instance_id, redis_client)
				self.options = []
				self.deck_size = deck_size
				self.is_higher = True

		async def handle_next(self):
				print("handling next")
				# end game if round_id > ROUNDS
				# send end message with winner, based on points
				if self.round_id > ROUNDS:
						winner = max(self.players, key=lambda x: self.players[x].points)
						await self.notify_all_players("end", {
								"winner": winner
						})
						self.is_active = False
						self.game_state = "lobby"
						return

				self.is_higher = not self.is_higher
				self.game_state = "start"

				for player_name in self.get_live_players():
						self.players[player_name].played = None
						self.players[player_name].acknowledged = False

				live_players = self.get_live_players()

				if len(live_players) < 2:
						winner = "No one"
						if len(live_players) == 1:
								winner = live_players[0]
						await self.notify_all_players("end", {
								"winner": winner
						})
						self.is_active = False
						self.game_state = "lobby"
						return

				# let all the calculations happen before notifying
				self.options = np.random.permutation(self.deck_size).tolist()[:OPTIONS_SIZE]
				await self.notify_all_players("next", {
						"options": self.options,
						"is_higher": self.is_higher,
						"round_id": self.round_id,
				})
				print("finished next")

		async def handle_evaluate(self):
				print("evaluating")
				self.game_state = "evaluate"
				# subtract score if a player has played the most popular card
				card_ids = [player.played['card_id'] for player in self.players.values()]
				card_id_counts = {card_id: card_ids.count(card_id) for card_id in card_ids}

				most_popular_card = None
				highest_count = max(card_id_counts.values())
				number_of_cards_with_highest_count = len([card_id for card_id in card_id_counts if card_id_counts[card_id] == highest_count])

				# if there is a single card that is most popular
				if number_of_cards_with_highest_count == 1:
						most_popular_card = max(card_id_counts, key=card_id_counts.get)


				# if a player played the most popular card, subtract score
				failed_players = []
				for player_name in self.players:
						if self.players[player_name].played['card_id'] == most_popular_card:
								self.players[player_name].points -= 3
								failed_players.append(player_name)

				# add score if player played the highest card
				num_of_data_fields = len(self.players[list(self.players.keys())[0]].played['data'])

				# for each field, add score to the player with the highest value
				winners = []
				for i in range(num_of_data_fields):
						field_winners = {
								"best_value": None,
								"winners": []
						}
						value_list = [player.played['data'][i] for player in self.players.values()]
						if self.is_higher:
								best_value = max(value_list, default=float('-inf'))
								field_winners["best_value"] = best_value
						else:  
								best_value = min(value_list, default=float('inf'))
								field_winners["best_value"] = best_value
						for player_name in self.players:
								if self.players[player_name].played['data'][i] == best_value:
										self.players[player_name].points += 1
										field_winners["winners"].append(player_name)
						winners.append(field_winners)

				self.winners = winners
				self.failed_players = failed_players
				self.most_popular_card = most_popular_card

				await self.notify_all_players("evaluate", {
								"players": self.get_player_data(),
								"winners": self.winners,
								"failed_players": self.failed_players,
								"most_popular_card": self.most_popular_card if self.most_popular_card is not None else -1,
				})

				self.round_id += 1
				print("finished evaluating")