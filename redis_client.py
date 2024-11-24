from typing import Dict, Any
import redis.asyncio as redis
import json

# read from environment variables
port = 17149

class RedisClient:
		def __init__(self, settings):
				self.client = redis.Redis(
						host=settings.redis_host,
						port=port,
						password=settings.redis_password,
				)
		
		async def publish(self, channel: str, message: Dict[str, Any]):
				print('pub', channel, message)
				await self.client.publish(channel, json.dumps(message))

		async def subscribe(self, channel: str, callback):
				pubsub = self.client.pubsub()
				await pubsub.subscribe(channel)
				print('subscribed to', channel)
				async for message in pubsub.listen():
						print('sub', message)
						if message["type"] == "message":
								await callback(json.loads(message['data'].decode('utf-8')))

		async def unsubscribe(self, channel: str):
				self.client.unsubscribe(channel)