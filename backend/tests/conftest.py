import os
# Tests never write to or open the user's real saved games.
os.environ['WARCHEST_DB'] = ':memory:'
