import json
from typing import List, Dict

user_example = """
The participants in the ice-breaker session are Strangers.
Purpose: school of computing orientation.
Other information: they are fun loving people.
Quantity: 3.
"""

assistant_example = """
[
    "What is your favorite programming language?",
    "If you could choose one programming langauge for the rest of your life, what would it be?",
    "What was your favourite experience in a hackathon like?"
]
"""

def get_prompt(purpose, information, quantity):
  return f"""
  Purpose: {purpose}.
  Other information: the participants are {information}.
  Quantity: {quantity}.
  """

def get_messages(prompt):
  return [
        {"role": "user", "content": user_example},
        {"role": "assistant", "content": assistant_example},
        {"role": "user", "content": prompt}
  ]

async def generate_questions(client, purpose, information, quantity):
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

class ConvoStarterData():
  games: Dict[str, List[str]]
  total_count: int
  
  def __init__(self):
    self.games = {}
    self.total_count = 0
  
  def has_reached_limit(self):
    return self.total_count >= 100000