from typing import Dict
from hedge_game_instance import HedgeGameInstance
from redis_client import RedisClient
from pymongo import MongoClient
import numpy as np

ROUNDS = 10

class CityHedgerGameInstance(HedgeGameInstance):
	player_distances: Dict[str, float]
	lat: float
	lng: float

	def __init__(self,
		instance_id: str,
		redis_client: RedisClient,
		mongo_client: MongoClient=None,
		country: str="US",
		min_lat: float=0,
		max_lat: float=0,
		min_lng: float=0,
		max_lng: float=0):

		super().__init__(instance_id, redis_client)
		self.mongo_client = mongo_client
		self.country = country
		self.min_lat = min_lat
		self.max_lat = max_lat
		self.min_lng = min_lng
		self.max_lng = max_lng
		self.player_distances = {}
		self.max_distance = CityHedgerGameInstance.calculate_distance_in_km(min_lat, min_lng, max_lat, max_lng)

	def calculate_distance_in_km(x1: float, y1: float, x2: float, y2: float):
		R = 6371
		x1 = np.radians(x1)
		y1 = np.radians(y1)
		x2 = np.radians(x2)
		y2 = np.radians(y2)
		delta_x = x2 - x1
		delta_y = y2 - y1
		a = np.sin(delta_x/2) * np.sin(delta_x/2) + np.cos(x1) * np.cos(x2) * np.sin(delta_y/2) * np.sin(delta_y/2)
		c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))
		return R * c
	
	def get_player_data(self):
		return {
			player_name: {
				"points": self.players[player_name].points,
				"played": self.players[player_name].played,
				"added_score": self.players[player_name].added_score,
				"distance": self.player_distances.get(player_name, 0),
				"acknowledged": self.players[player_name].acknowledged
			} for player_name in self.players
		}
	
	def randomise_lat_lng(self):
		self.lat = np.random.uniform(self.min_lat, self.max_lat)
		self.lng = np.random.uniform(self.min_lng, self.max_lng)
	
	async def handle_next(self):
		print("handling next")

		for player_name in self.players:
			self.players[player_name].is_alive = True

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

		self.game_state = "start"

		for player_name in self.get_live_players():
			self.players[player_name].played = None
			self.players[player_name].acknowledged = False
			self.player_distances[player_name] = None

		self.lat = None
		self.lng = None
		
		# let all the calculations happen before notifying
		self.randomise_lat_lng()
		await self.notify_all_players("next", {
			"round_id": self.round_id,
			"lat": self.lat,
			"lng": self.lng
		})
		print("finished next")

	async def handle_play(self, name: str, played: str): 
		print(f"{name} played {played}")

		city_name = f'^{played}$' or ''
		code = f'^{self.country}$' or ''
		print('city_name, code', city_name, code)
		city_results = []
		for city in self.mongo_client.place_names.cities.find({'name': {'$regex': city_name, '$options': 'i'}, 'code': {'$regex': code, '$options': 'i'}}):
			city_results.append({
				'name': city['name'],
				'lat': city['lat'],
				'lng': city['lng']
			})
		print('city_results', city_results)
		if len(city_results) == 0:
			await self.notify_player(name, "play_error", {})
			return
		
		# find the closest city
		best_distance = float('inf')
		best_city = None
		for city in city_results:
			distance = CityHedgerGameInstance.calculate_distance_in_km(self.lat, self.lng, city['lat'], city['lng'])
			if distance < best_distance:
				best_distance = distance
				best_city = city

		self.player_distances[name] = best_distance
		self.players[name].played = best_city
		
		await self.notify_all_players("play", {})
		print(self.get_live_players())
		if all(self.players[player_name].played is not None for player_name in self.get_live_players()):
			await self.handle_evaluate()

	async def handle_evaluate(self):
		print("evaluating")
		self.game_state = "evaluate"
		gained = {}

		# players get points based on their distance of their guess to the actual location
		for player_name in self.get_live_players():
			player = self.players[player_name]
			distance = CityHedgerGameInstance.calculate_distance_in_km(player.played['lat'], player.played['lng'], self.lat, self.lng)
			self.player_distances[player_name] = distance
			
			# points should be max 100
			gained[player_name] = {
				"points": int(100 - ((distance / self.max_distance) * 100)),
				"city": player.played['name'],
			}
			player.points += gained[player_name]["points"]

		# most popular city
		city_counts = {}
		for player_name in self.get_live_players():
			player = self.players[player_name]
			played_city_name = player.played['name']
			if played_city_name not in city_counts:
				city_counts[played_city_name] = 0
			city_counts[played_city_name] += 1
		
		print(self.players, city_counts)
		
		max_count = max(city_counts.values())
		most_popular_cities = [city for city in city_counts if city_counts[city] == max_count]
		failed_players = set()
		if len(most_popular_cities) == 1 and len(self.get_live_players()) > 1:
			# players lose 50 points if they guess the most popular city
			for player_name in self.get_live_players():
				player = self.players[player_name]
				if player.city == most_popular_cities[0]:
					failed_players.add(player_name)

		for player_name in failed_players:
			self.players[player_name].points -= 50
			gained[player_name]["points"] -= 50

		await self.notify_all_players("evaluate", {
			"players": self.get_player_data(),
			"gained": gained,
			"most_popular_city": most_popular_cities[0] if len(most_popular_cities) == 1 and len(self.get_live_players()) > 1 else -1,
			"failed": list(failed_players)
		})

		self.round_id += 1
		print("finished evaluating")