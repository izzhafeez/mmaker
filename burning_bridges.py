import json
from typing import List, Dict

user_example = """
Purpose: school of computing orientation.
Other information: they are fun loving people.
Quantity: 3.
"""

assistant_example = """
[
    "In a hackathon, who would you least want as your coding partner?",
    "If we had to rely on someone to fix a critical server issue, who would probably make things worse instead of better?",
    "Who do you think would be the most likely to accidentally commit confidential information into a public code repository?"
]
"""

def get_prompt(purpose, information, quantity):
  return f"""
  Purpose: {purpose}.
  Other information: the participants are {information}.
  Quantity: {quantity}.
  I want you to generate questions where the answer must be one of the players and players would not want to be chosen.
  The more bizarre the questions, the better.
  """

def get_messages(prompt):
  return [
        {"role": "user", "content": user_example},
        {"role": "assistant", "content": assistant_example},
        {"role": "user", "content": prompt}
  ]

async def generate_bb_questions(client, purpose, information, quantity):
  prompt = get_prompt(purpose, information, quantity)
  messages = get_messages(prompt)
  response = client.chat.completions.create(
    model="gpt-3.5-turbo",
    messages=messages,
    temperature=0.9,
  )
  questions = json.loads(response.choices[0].message.content)
  total_tokens = response.usage.total_tokens
  return questions, total_tokens

class BurningBridgesData():
  games: Dict[str, List[str]]
  total_count: int
  
  def __init__(self):
    self.games = {}
    self.total_count = 0
  
  def has_reached_limit(self):
    return self.total_count >= 100000