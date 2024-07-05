import json
from typing import List, Dict

user_example = """
Purpose: school of computing orientation.
Other information: they are fun loving people.
Quantity: 3.
"""

assistant_example = """
{
  "truths": [
    "What is the most useless programming language?",
    "What is the best programming language?",
    "Who do you think is the worst programmer in the room?"
  ],
  "dares": [
    "Add a random tech influencer on LinkedIn.",
    "Post something, anything, on LinkedIn.",
    "Let the others roast your codebase for 5 minutes."
  ]
}
"""

def get_prompt(purpose, information, quantity):
  return f"""
  Purpose: {purpose}.
  Other information: the participants are {information}.
  Quantity: {quantity}.
  Generate a list of truth or dare questions that give the most fun experience.
  Do not suggest illegal dares.
  The more bizarre the prompts, the better.
  """

def get_messages(prompt):
  return [
        {"role": "user", "content": user_example},
        {"role": "assistant", "content": assistant_example},
        {"role": "user", "content": prompt}
  ]

async def generate_tod_questions(client, purpose, information, quantity):
  prompt = get_prompt(purpose, information, quantity)
  messages = get_messages(prompt)
  response = client.chat.completions.create(
    model="gpt-3.5-turbo",
    messages=messages,
    temperature=0.9,
  )
  questions = json.loads(response.choices[0].message.content)
  truths = questions["truths"]
  dares = questions["dares"]
  total_tokens = response.usage.total_tokens
  return truths, dares, total_tokens

class TruthDareData():
  games: Dict[str, List[str]]
  total_count: int
  
  def __init__(self):
    self.games = {}
    self.total_count = 0
  
  def has_reached_limit(self):
    return self.total_count >= 100000